#include "RunWqqm.h"
#include <vector>
#include "HistCutflow.h"
#include "Helper.h"
   
// Constructor implementation
RunWqqm::RunWqqm(GlobalFlag& globalFlags)
    :globalFlags_(globalFlags) {
}


auto RunWqqm::Run(std::shared_ptr<NanoTree>& nanoT, TFile *fout) -> int{
   fout->cd();

	//----------------------------------
	// Add channel specific branches 
	//----------------------------------
    nanoT->fChain->SetBranchStatus("Muon_charge", 1);
    nanoT->fChain->SetBranchStatus("Muon_pt", 1);
    nanoT->fChain->SetBranchStatus("Muon_eta", 1);
    nanoT->fChain->SetBranchStatus("Muon_phi", 1);
    nanoT->fChain->SetBranchStatus("Muon_mass", 1);

    nanoT->fChain->SetBranchStatus("Muon_highPurity", 1);
    nanoT->fChain->SetBranchStatus("Muon_pfRelIso04_all", 1);
    nanoT->fChain->SetBranchStatus("Muon_tkRelIso", 1); 
    nanoT->fChain->SetBranchStatus("Muon_dxy", 1); 
    nanoT->fChain->SetBranchStatus("Muon_dz", 1); 
    nanoT->fChain->SetBranchStatus("nMuon",1);

   nanoT->fChain->SetBranchStatus("Muon_looseId", 1);
   nanoT->fChain->SetBranchStatus("Muon_mediumId", 1);
   nanoT->fChain->SetBranchStatus("Muon_tightId", 1);

   nanoT->fChain->SetBranchStatus("Muon_pfIsoId", 1);
   nanoT->fChain->SetBranchStatus("Muon_puppiIsoId", 1);
   nanoT->fChain->SetBranchStatus("Muon_softId", 1);

   nanoT->fChain->SetBranchStatus("Jet_pt", 1);
   nanoT->fChain->SetBranchStatus("Jet_eta", 1);
   nanoT->fChain->SetBranchStatus("Jet_phi", 1);
   nanoT->fChain->SetBranchStatus("Jet_btagUParTAK4B", 1);
   nanoT->fChain->SetBranchStatus("nJet", 1);


  	if (globalFlags_.isMC){
      nanoT->fChain->SetBranchStatus("GenDressedLepton_*",true);
      nanoT->fChain->SetBranchStatus("nGenDressedLepton",true);
    }

	//----------------------------------
	// Set trigger list
	//----------------------------------
    trigList_  =  {
        "HLT_IsoMu24",
    }; 

    if (trigList_.empty()) {
        std::cerr << "No triggers found for channel: ZeeJet" << '\n';
        exit(EXIT_FAILURE);
    }
	for (const auto& trigN : trigList_) {
		nanoT->fChain->SetBranchStatus(trigN.c_str(), true);
	    nanoT->fChain->SetBranchAddress(trigN.c_str(), &trigVals_[trigN], &trigTBranches_[trigN]);
	} 
    TTree* newTree = nanoT->fChain->CloneTree(0);
    newTree->SetCacheSize(Helper::tTreeCatchSize);
    Long64_t nentries = nanoT->getEntries();
    std::cout << "Sample has "<<nentries << " entries" << '\n';

    //------------------------------------
    // Cutflow histograms
    //------------------------------------
    std::vector<std::string> cuts = { "NanoAOD", "Filter", "Trigger", "Jet" };
    auto h1EventInCutflow = std::make_unique<HistCutflow>("h1EventInCutflow", cuts, fout->mkdir("Cutflow"));

    // --------- Move Jet branch address setup here ---------
    Int_t nJet = 0;
    static const int MAXJETS = 200;
    Float_t Jet_pt[MAXJETS] = {0};
    Float_t Jet_eta[MAXJETS] = {0};
    Float_t Jet_btagUParTAK4B[MAXJETS] = {0};

    nanoT->fChain->SetBranchAddress("nJet",                      &nJet);
    nanoT->fChain->SetBranchAddress("Jet_pt",                    Jet_pt);
    nanoT->fChain->SetBranchAddress("Jet_eta",                   Jet_eta);
    nanoT->fChain->SetBranchAddress("Jet_btagUParTAK4B",         Jet_btagUParTAK4B);
    // ------------------------------------------------------

    
    //--------------------------------
    //Event loop
    //--------------------------------
    double totalTime = 0.0;
	auto startClock = std::chrono::high_resolution_clock::now();
    Helper::initProgress();
	for(Long64_t i= 0; i < nentries; i++){
        //if(i>100000) break;
        Helper::printProgress(i, nentries, startClock, totalTime);
        
        Long64_t entry = nanoT->loadEntry(i);
        h1EventInCutflow->fill("NanoAOD");

        bool passFilter = true;
		for (const auto& filterN : nanoT->filterList) {
            if (!nanoT->filterTBranches[filterN]) continue;
		    nanoT->filterTBranches[filterN]->GetEntry(entry);//Read only content of MET Filter branches from NanoTree
		    if (!nanoT->filterVals[filterN]) {
                passFilter = false;
		        break; 
		    }
		}
        if(!passFilter) continue;
        h1EventInCutflow->fill("Filter");

        bool passTrigger = false;
		for (const auto& trigN : trigList_) {
            if (!trigTBranches_[trigN]) continue;
		    trigTBranches_[trigN]->GetEntry(entry);//Read only content of HLT branches from NanoTree
		    if (trigVals_[trigN]) {
                passTrigger = true;
		        break; 
		    }
		}
        
        if(!passTrigger) continue;
        h1EventInCutflow->fill("Trigger");

        // Load all active branches (including jets) via the chain
        nanoT->getEntry(i);

        const float btagThreshold = 0.0849; // btagUParT loose WP for Run 3, adjust if needed
        int nJets = 0;
        int nBTaggedJets = 0;

        for (int j = 0; j < nJet; ++j) {
            float btag = Jet_btagUParTAK4B[j];
            ++nJets;
            if (btag > btagThreshold) {
                ++nBTaggedJets;
            }
            
        }

        // Combined jet multiplicity and b‑tag cut
        if (nJets < 3 || nBTaggedJets < 1) continue;
        h1EventInCutflow->fill("Jet");
        
        //Now read all of the branches and fill the tree
        //nanoT->fChain->GetTree()->GetEntry(entry);
        newTree->Fill();
    }

    TTree* newTreeRuns = nanoT->fChainRuns->CloneTree(0);
    newTreeRuns->SetDirectory(fout);
    Long64_t nentriesRuns = nanoT->getEntriesRuns();
    for (Long64_t i = 0; i < nentriesRuns; i++) {
       Long64_t entry = nanoT->loadEntryRuns(i);
       nanoT->fChainRuns->GetTree()->GetEntry(entry);
       newTreeRuns->Fill();      
    }
    Helper::printCutflow(h1EventInCutflow->getHistogram());
    std::cout<<"nEvents_Skim = "<<newTree->GetEntries()<<'\n';
    std::cout<<"nRuns_Skim = "<<newTreeRuns->GetEntries()<<'\n';
    std::cout << "Output file path = "<<fout->GetName()<<'\n';
    fout->Write();

    return EXIT_SUCCESS; 
}
