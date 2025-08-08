#include "NanoTree.h"
#include "Helper.h"
#include <TError.h>

#include <iostream>
#include <stdexcept>

NanoTree::NanoTree(GlobalFlag& globalFlags) : globalFlags_(globalFlags) {}

NanoTree::~NanoTree() {
    delete fChain;
    //delete fChainRuns;
}

void NanoTree::setInput(const std::string& outputName) {
    outputName_ = outputName;
    std::cout << "+ setInput() = " << outputName_ << '\n';
}

void NanoTree::loadInput() {
    std::cout << "==> loadInput()" << '\n';
    try {
        std::vector<std::string> nameParts = Helper::splitString(outputName_, "_Skim_");
        loadedSampleKey_ = nameParts.at(0);
        std::cout << "Loaded sample key: " << loadedSampleKey_ << '\n';

        std::vector<std::string> jobParts = Helper::splitString(nameParts.at(1), ".root");
        std::string jobInfo = jobParts.at(0);
        std::vector<std::string> jobSplit = Helper::splitString(jobInfo, "of");

        loadedNthJob_ = std::stoul(jobSplit.at(0));
        loadedTotalJobs_ = std::stoul(jobSplit.at(1));
    } catch (const std::exception& e) {
        std::cerr << "\nEXCEPTION: Invalid output name format: " << outputName_ << '\n';
        std::cerr << "Expected format: DataOrMC_Year_Channel_Sample_Skim_nofN.root\n";
        std::cerr << "Run ./runMain -h for more details\n";
        std::cerr << e.what() << '\n';
        std::abort();
    }
}

void NanoTree::loadInputJson(const std::string& searchDir) {
    std::cout << "==> loadInputJson()\n";
    std::vector<std::filesystem::path> jsonFiles;

    try {
        for (const auto& entry : std::filesystem::directory_iterator(searchDir)) {
            if (entry.path().extension() == ".json" &&
                entry.path().filename().string().rfind("FilesNano_", 0) == 0) {
                jsonFiles.push_back(entry.path());
            }
        }
    } catch (const std::exception& e) {
        std::cerr << "Error scanning directory " << searchDir << ": " << e.what() << "\n";
        std::abort();
    }

    if (jsonFiles.empty()) {
        std::cerr << "No JSON files found in directory: " << searchDir << "\n";
        std::abort();
    }

    // We expect exactly one JSON file to contain our key.
    // Reset any previously loaded list.
    loadedAllFileNames_.clear();

    int foundCount = 0;
    nlohmann::json jsonContent;

    // Loop over each JSON file and look for the loadedSampleKey_
    for (const auto& jsonFile : jsonFiles) {
        std::ifstream inputFile(jsonFile);
        if (!inputFile.is_open()) {
            std::cerr << "Could not open JSON file: " << jsonFile << "\n";
            continue;
        }
        
        try {
            jsonContent = nlohmann::json::parse(inputFile);
        } catch (const std::exception& e) {
            std::cerr << "\nEXCEPTION: Error parsing JSON at " << jsonFile << "\n";
            std::cerr << e.what() << "\n";
            continue;
        }

        std::string channel;
        try {
            channel = Helper::splitString(loadedSampleKey_, "_").at(2);
        } catch (const std::exception& e) {
            std::cerr << "Error parsing loadedSampleKey_: " << loadedSampleKey_ << "\n";
            std::cerr << e.what() << "\n";
            std::abort();
        }

        if (jsonContent.contains(loadedSampleKey_)) {
            foundCount++;
            // Check that the value corresponding to loadedSampleKey_ is an array.
            const auto& value = jsonContent.at(loadedSampleKey_).at(1);
            if (!value.is_array()) {
                std::cerr << "Error: JSON key '" << loadedSampleKey_ 
                          << "' in file " << jsonFile
                          << " is not an array. Aborting.\n";
                std::abort();
            }
            // Extract the vector of strings
            try {
                loadedAllFileNames_ = value.get<std::vector<std::string>>();
            } catch (const std::exception& e) {
                std::cerr << "\nEXCEPTION: Error extracting key '" << loadedSampleKey_
                          << "' from file " << jsonFile << "\n";
                std::cerr << e.what() << "\n";
                std::abort();
            }
        }
    }  // end for

    if (foundCount == 0) {
        std::cerr << "\nEXCEPTION: Key '" << loadedSampleKey_ 
                  << "' was not found in any JSON file in " << searchDir << "\n";
        std::abort();
    }

    if (foundCount > 1) {
        std::cerr << "\nEXCEPTION: Key '" << loadedSampleKey_ 
                  << "' found in multiple JSON files. Please ensure uniqueness.\n";
        std::abort();
    }
}

void NanoTree::loadJobFileNames() {
    std::cout << "==> loadJobFileNames()" << '\n';
    std::size_t totalFiles = loadedAllFileNames_.size();
    std::cout << "Total files: " << totalFiles << '\n';

    if (loadedTotalJobs_ > totalFiles) {
        std::cerr << "Warning: loadedTotalJobs exceeds total files; adjusting to " << totalFiles << '\n';
        loadedTotalJobs_ = totalFiles;
    }

    if (loadedNthJob_ > loadedTotalJobs_) {
        std::cerr << "Error: loadedNthJob exceeds loadedTotalJobs\n";
        std::abort();
    }

    if (loadedNthJob_ > 0 && loadedTotalJobs_ > 0) {
        std::cout << "Processing job " << loadedNthJob_ << " of " << loadedTotalJobs_ << '\n';
        std::cout << "Approximately " << totalFiles / loadedTotalJobs_ << " files per job" << '\n';
    } else {
        std::cerr << "Error: loadedNthJob and loadedTotalJobs must be greater than zero\n";
        std::abort();
    }

    loadedJobFileNames_ = Helper::splitVector(loadedAllFileNames_, loadedTotalJobs_).at(loadedNthJob_ - 1);
}

    void NanoTree::loadTree() {
    std::cout << "==> loadTree()" << '\n';
    fChain->SetCacheSize(Helper::tTreeCatchSize);
    fChainRuns->SetCacheSize(Helper::tTreeCatchSize);
    bool isCopy = false;  // Set to true if you want to copy files locally
    std::string dir = "root://cms-xrd-global.cern.ch/";  // Default remote directory

    int totalFiles = 0;
    int addedFiles = 0;
    int failedFiles = 0;

    // Optimization parameters for xrdcp
    const int streams = 15;              // Number of parallel data streams
    const int tcpBufSize = 1048576;        // TCP buffer size (1MB)

    for (const auto& fileName : loadedJobFileNames_) {
        totalFiles++;
        std::string fullPath;

        if (isCopy) {
            // Extract the local file name from the remote path
            std::string localFile = fileName.substr(fileName.find_last_of('/') + 1);
            std::string cmd = "xrdcp ";

            // Append optimization options to the xrdcp command
            cmd += "--streams " + std::to_string(streams) + " ";

            // Construct the full remote path
            std::string remoteFile = dir + fileName;

            // Build the final command
            cmd += remoteFile + " " + localFile;

            std::cout << "Executing command: " << cmd << '\n';
            int ret = system(cmd.c_str());

            if (ret != 0) {
                std::cerr << "Error: Failed to copy " << remoteFile << " to local file " << localFile << '\n';
                failedFiles++;
                continue;  // Skip adding this file
            }

            // Check if the file was successfully copied
            if (!std::filesystem::exists(localFile)) {
                std::cerr << "Error: Local file " << localFile << " does not exist after copying.\n";
                failedFiles++;
                continue;  // Skip adding this file
            }

            fullPath = localFile;  // Use the local file path
        } else {
            // Remote file handling
            std::filesystem::path filePath = "/eos/cms/" + fileName;
            if (std::filesystem::exists(filePath)) {
                dir = "/eos/cms/";  // Use local EOS path
                fullPath = dir + fileName;
            } else {
                dir = "root://cms-xrd-global.cern.ch/";  // Fallback to remote
                fullPath = dir + fileName;
            }
        }

        // Attempt to open the file to verify its validity
        TFile* f = TFile::Open(fullPath.c_str(), "READ");
        if (!f || f->IsZombie()) {
            std::cerr << "Error: Failed to open or corrupted file " << fullPath << '\n';
            if (f) f->Close();
            failedFiles++;
            continue;  // Skip adding this file
        }

        // Additional check: if file size is 0, skip the file.
        std::cout<<f->GetSize()<<'\n';
        if (f->GetSize() < 3000) {
            std::cerr << "Warning: file " << fullPath << " has less than 3000, skipping." << std::endl;
            f->Close();
            failedFiles++;
            continue;  // Skip adding this file
        }

        // Check if "Events" tree exists
        if (!f->GetListOfKeys()->Contains("Events")) {
            std::cerr << "Error: 'Events' not found in " << fullPath << '\n';
            f->Close();
            failedFiles++;
            continue;  // Skip adding this file
        }

        // Check the entries in the newly added TTree
        TTree* tree = f->Get<TTree>("Events");
        Long64_t fileEntries = tree->GetEntries();
        if (fileEntries == 0) {
            std::cerr << "\nWarning: 'Events' TTree in file " << fullPath << " has 0 entries. Skipping file.\n\n";
            f->Close();
            failedFiles++;
            continue;  // Skip adding this file to the final count
        }

        // File is valid, add it to the TChain
        int added = fChain->Add(fullPath.c_str());
        fChainRuns->Add(fullPath.c_str());
        if (added == 0) {
            std::cerr << "Warning: TChain::Add failed for " << fullPath << '\n';
            f->Close();
            failedFiles++;
            continue;  // Skip adding this file
        }

        std::cout << fullPath << "  Entries: " << fChain->GetEntries() << '\n';
        std::cout << fullPath << "  EntriesRuns: " << fChainRuns->GetEntries() << '\n';
        addedFiles++;
        f->Close();
    }

    // Final summary
    std::cout << "==> Finished loading files.\n";
    std::cout << "Total files processed: " << totalFiles << '\n';
    std::cout << "Successfully added files: " << addedFiles << '\n';
    std::cout << "Failed to add files: " << failedFiles << '\n';

    // Check if the chain has any trees
    if (fChain->GetNtrees() == 0) {
        std::cerr << "Error: No valid ROOT files were added to the TChain. Exiting.\n";
        return;
    }
    fChainRuns->SetBranchStatus("*", true);

    fChain->SetBranchStatus("*", false);
    fChain->SetBranchStatus("run", true);
    fChain->SetBranchStatus("event", true);
    fChain->SetBranchStatus("luminosityBlock", true);

	//--------------------------------------- 
    // Jet branches for all channels 
    //--------------------------------------- 
    fChain->SetBranchStatus("Jet_btagDeep*",1);
    fChain->SetBranchStatus("Jet_btagPNetQvG",1);
    fChain->SetBranchStatus("Jet_btagUParTAK4QvG",1);
    fChain->SetBranchStatus("Jet_chEmEF",1);
    fChain->SetBranchStatus("Jet_chHEF" ,1);
    fChain->SetBranchStatus("Jet_eta"   ,1);
    fChain->SetBranchStatus("Jet_mass"  ,1);
    fChain->SetBranchStatus("Jet_muEF"  ,1);
    fChain->SetBranchStatus("Jet_neEmEF",1);
    fChain->SetBranchStatus("Jet_hfEmEF",1);
    fChain->SetBranchStatus("Jet_hfHEF",1);
    fChain->SetBranchStatus("Jet_neHEF" ,1);
    fChain->SetBranchStatus("Jet_phi"   ,1);
    fChain->SetBranchStatus("Jet_pt"    ,1);
    fChain->SetBranchStatus("Jet_rawFactor",1);
    fChain->SetBranchStatus("Jet_jetId",1);
    fChain->SetBranchStatus("Jet_area",1);
    fChain->SetBranchStatus("nJet",1);

    //common branches
	fChain->SetBranchStatus("PV_z");
	fChain->SetBranchStatus("GenVtx_z");
    fChain->SetBranchStatus("PV_npvs",1);
    fChain->SetBranchStatus("PV_npvsGood",1);
    if(globalFlags_.is2024 && globalFlags_.isData){
      fChain->SetBranchStatus("PFMET_pt",1);
      fChain->SetBranchStatus("PFMET_phi",1);
      fChain->SetBranchStatus("PuppiMET_pt",1);
      fChain->SetBranchStatus("PuppiMET_phi",1);
      fChain->SetBranchStatus("RawPuppiMET_phi",1);
      fChain->SetBranchStatus("RawPuppiMET_pt",1);
      fChain->SetBranchStatus("RawPuppiMET_sumEt",1);
    }
    else{
      fChain->SetBranchStatus("MET_pt",1);
      fChain->SetBranchStatus("MET_phi",1);
      fChain->SetBranchStatus("ChsMET_pt",1);
      fChain->SetBranchStatus("ChsMET_phi",1);
      fChain->SetBranchStatus("RawPuppiMET_phi",1);
      fChain->SetBranchStatus("RawPuppiMET_pt",1);
      fChain->SetBranchStatus("RawPuppiMET_sumEt",1);
    }

	fChain->SetBranchStatus("Rho_fixed*", 1);
 
    if (globalFlags_.isMC) {
        fChain->SetBranchStatus("Jet_genJetIdx",1);
		fChain->SetBranchStatus("genWeight");
		fChain->SetBranchStatus("nPSWeight");
		fChain->SetBranchStatus("PSWeight");
		fChain->SetBranchStatus("LHE_HT");
	    fChain->SetBranchStatus("Pileup_*",1);
        fChain->SetBranchStatus("GenJet_*",1);
        fChain->SetBranchStatus("nGenJet",1);

        fChain->SetBranchStatus("Generator_weight",1);
        fChain->SetBranchStatus("nLHEScaleWeight",1);
        fChain->SetBranchStatus("LHEScaleWeight",1);
        fChain->SetBranchStatus("nLHEPdfWeight",1);
        fChain->SetBranchStatus("nLHEPart",1);
        fChain->SetBranchStatus("LHEPart_*",1);
        fChain->SetBranchStatus("PSWeight",1);
        fChain->SetBranchStatus("nPSWeight",1);
        fChain->SetBranchStatus("genWeight",1);
		/*
        fChain->SetBranchStatus("GenPart_*",1);
        fChain->SetBranchStatus("nGenPart",1);
        fChain->SetBranchStatus("GenJetAK8_*",1);
        fChain->SetBranchStatus("nGenJetAK8",1);
        fChain->SetBranchStatus("LHEPdfWeight",1);
        // weight
		*/
    }//MC

    filterList = { 
        "Flag_goodVertices",
        "Flag_globalSuperTightHalo2016Filter",
        "Flag_EcalDeadCellTriggerPrimitiveFilter",
        "Flag_BadPFMuonFilter",
        "Flag_BadPFMuonDzFilter",
        "Flag_hfNoisyHitsFilter",
        "Flag_eeBadScFilter",
        "Flag_ecalBadCalibFilter"
    };
	for (const auto& filterN : filterList) {
		fChain->SetBranchStatus(filterN.c_str(), true);
	    fChain->SetBranchAddress(filterN.c_str(), &filterVals[filterN], &filterTBranches[filterN]);
	} 
}

auto NanoTree::getEntries() const -> Long64_t {
    return fChain->GetEntries();
}

auto NanoTree::getEntriesRuns() const -> Long64_t {
    return fChainRuns->GetEntries();
}
auto NanoTree::getEntry(Long64_t entry) -> Int_t {
    return fChain->GetEntry(entry);
}

auto NanoTree::loadEntry(Long64_t entry) -> Long64_t {
    if (!fChain) return EXIT_FAILURE;
    Long64_t centry = fChain->LoadTree(entry);
    if (centry < 0) return centry;
    if (fChain->GetTreeNumber() != fCurrent_) {
        fCurrent_ = fChain->GetTreeNumber();
    }
    return centry;
}

auto NanoTree::loadEntryRuns(Long64_t entry) -> Long64_t {
    if (!fChainRuns) return EXIT_FAILURE;
    Long64_t centry = fChainRuns->LoadTree(entry);
    if (centry < 0) return centry;
    if (fChainRuns->GetTreeNumber() != fCurrentRuns_) {
        fCurrentRuns_ = fChainRuns->GetTreeNumber();
    }
    return centry;
}