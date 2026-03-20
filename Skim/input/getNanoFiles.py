#!/usr/bin/env python3
import os
import sys
import subprocess
import json
from pathlib import Path
import ROOT
ROOT.gROOT.SetBatch(True)

# ------------------------------------------------------------------
# Import configuration from Inputs.py
# ------------------------------------------------------------------
currentDir = Path(__file__).resolve().parent
parentDir = currentDir.parent
sys.path.insert(0, str(parentDir))
from Inputs import Years, Channels

def check_duplicate_leaf_keys(json_data, seen=None, path=""):
    """
    Checks for duplicate leaf keys in a nested JSON-like dictionary.

    Args:
        json_data (dict): The JSON-like dictionary to check.
        seen (set): A set to track seen leaf keys.
        path (str): The current path in the JSON structure (used for reporting duplicates).

    Returns:
        bool: True if duplicates are found, False otherwise.
    """
    if seen is None:
        seen = set()

    duplicate_found = False

    for key, value in json_data.items():
        if isinstance(value, dict):  # Recur for nested dictionaries
            duplicate_found |= check_duplicate_leaf_keys(value, seen, path)
        else:  # Leaf key
            if key in seen:
                print(f"Duplicate leaf key found: {key}")
                duplicate_found = True
            else:
                seen.add(key)

    return duplicate_found

# ------------------------------------------------------------------
# Functions to query DAS and format numbers
# ------------------------------------------------------------------
def getFiles(dataset):
    """
    Fetches the list of files for a given dataset using dasgoclient.
    """
    try:
        dasquery = ["dasgoclient", "-query=file dataset=%s" % dataset]
        output = subprocess.check_output(dasquery, stderr=subprocess.STDOUT)
        files = output.decode('utf-8').strip().splitlines()
        return files
    except subprocess.CalledProcessError as e:
        print(f"Error fetching files for dataset '{dataset}': {e.output.decode('utf-8')}")
        return []

def getEvents(dataset):
    """
    Fetches the number of events for a given dataset using dasgoclient.
    """
    try:
        dasquery = ["dasgoclient", "-query=summary dataset=%s" % dataset]
        output = subprocess.check_output(dasquery, stderr=subprocess.STDOUT)
        summary = json.loads(output.decode('utf-8').strip())
        nEvents = summary[0].get('nevents', 0)
        return nEvents
    except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError) as e:
        print(f"Error fetching event count for dataset '{dataset}': {e}")
        return 0

def getFilesFromEOS(eos_dir):
    """
    List ROOT files under an EOS directory and return them as /store/... paths
    (to match the format returned by dasgoclient).
    """
    try:
        # Ensure no trailing slash
        eos_dir = eos_dir.rstrip('/')

        # xrdfs needs the full EOS path, e.g. /eos/cms/store/...
        cmd = ["xrdfs", "root://eoscms.cern.ch", "ls", eos_dir]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        lines = output.decode('utf-8').strip().splitlines()

        files = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # If this is a directory, recurse
            if not line.endswith(".root"):
                # optional: recurse into subdirs (Winter25 layout has subdirs)
                sub_cmd = ["xrdfs", "root://eoscms.cern.ch", "ls", line]
                sub_out = subprocess.check_output(sub_cmd, stderr=subprocess.STDOUT)
                for sub_line in sub_out.decode('utf-8').strip().splitlines():
                    sub_line = sub_line.strip()
                    if sub_line.endswith(".root"):
                        # strip the /eos/cms prefix to get /store/...
                        if sub_line.startswith("/eos/cms"):
                            sub_line = sub_line[len("/eos/cms"):]
                        files.append(sub_line)
            else:
                # direct .root file
                if line.startswith("/eos/cms"):
                    line = line[len("/eos/cms"):]
                files.append(line)

        print(f"[EOS getFiles] Found {len(files)} files under {eos_dir}")
        return files

    except subprocess.CalledProcessError as e:
        print(f"[EOS getFiles] Error listing EOS dir '{eos_dir}': {e.output.decode('utf-8')}")
        return []

def getEventsFromFiles(files):
    """
    Count events by opening the ROOT files via xrootd and summing
    Entries in the 'Events' tree.
    'files' should be a list of paths like /store/mc/...
    """
    import ROOT
    ROOT.gROOT.SetBatch(True)

    total = 0
    for path in files:
        # path is like "/store/mc/Run3Winter25NanoAOD/..."
        # Use the CMS global redirector and make sure the path is absolute.
        url = "root://xrootd-cms.infn.it//" + path.lstrip('/')
        print(f"[getEventsFromFiles] Opening {url}")
        try:
            tf = ROOT.TFile.Open(url)
        except OSError as e:
            print(f"[getEventsFromFiles] ERROR: could not open {url}: {e}")
            continue

        if not tf or tf.IsZombie():
            print(f"[getEventsFromFiles] WARNING: zombie or null file {url}")
            continue

        tree = tf.Get("Events")
        if not tree:
            print(f"[getEventsFromFiles] WARNING: no 'Events' tree in {url}")
            tf.Close()
            continue

        n = tree.GetEntries()
        total += n
        tf.Close()

    print(f"[getEventsFromFiles] Total events from files = {total}")
    return total               

def formatNum(num):
    """
    Formats a number into a human-readable string with suffixes.
    """
    suffixes = ['', 'K', 'M', 'B', 'T']
    magnitude = 0
    while abs(num) >= 1000 and magnitude < len(suffixes) - 1:
        magnitude += 1
        num /= 1000.0
    return f"{round(num, 1)}{suffixes[magnitude]}"

# ------------------------------------------------------------------
# Main Script
# ------------------------------------------------------------------
def main():
    allEvents = 0
    jsonDir = currentDir / "nano_files"
    jsonDir.mkdir(exist_ok=True)

    # Iterate over each channel (e.g. GamJet)
    for channel in Channels:
        allEventsChannel = 0
        print(f"\n===========: Channel = {channel} :============\n")
        
        # Open the channel-based samples JSON file (e.g. SamplesNano_GamJet.json)
        samplesJsonPath = currentDir / f"SamplesNano_{channel}.json"
        try:
            with open(samplesJsonPath, 'r') as f:
                samplesData = json.load(f)
        except Exception as e:
            print(f"Error opening {samplesJsonPath}: {e}")
            continue 

        has_duplicates = check_duplicate_leaf_keys(samplesData)
        if  has_duplicates:
            print(f"{samplesJsonPath} has duplicate keys")
            continue
            
        # Process each year defined in Inputs.py
        for year, yinfo in Years.items():
            allEventsYear = 0
            print(f"========> {year}")

            # ---------------------------
            # Process MC samples: one output per sub-category
            #mcName = "MC"
            mcName = "MCSummer24"
            #mcName  = "MCWinter25"
            # ---------------------------
            mcDesired = yinfo.get(mcName, [])
            # For each desired MC sub-category, loop over periods whose key starts with the given year
            for subcat in mcDesired:
                mcFilesNano = {}
                mcEvents = {}
                print(f"  [{mcName}/{subcat}]")
                for periodKey, periodContent in samplesData.items():
                    if not periodKey.startswith(year):
                        continue
                    mcBranch = periodContent.get(mcName, {})
                    # Only process the requested sub-category.
                    if subcat not in mcBranch:
                        continue
                    sampleDict = mcBranch[subcat]
                    print(f"    Processing period: {periodKey}")
                    for sampleKey, dataset in sampleDict.items():
                        #print(f"      Querying sample {sampleKey} ...")
                        filesNano = getFiles(dataset)
                        if not filesNano:
                            print("  DAS returned 0 files — trying EOS fallback...")

                            eosPath = dataset.replace(
                                "/TTToLNu2Q_TuneCP5_13p6TeV_powheg-pythia8",
                                "/store/mc/Run3Winter25NanoAOD/TTToLNu2Q_TuneCP5_13p6TeV_powheg-pythia8"
                            ).replace(
                                "/Run3Winter25NanoAOD-142X_mcRun3_2025_realistic_v7-v2/NANOAODSIM",
                                "/NANOAODSIM/142X_mcRun3_2025_realistic_v7-v2"
                            )

                            print("EOS path = ", eosPath)
                            filesNano = getFilesFromEOS(eosPath)
                        nFiles = len(filesNano)
                        nEvents = getEvents(dataset)
                        # If DAS has no summary (0 events) but we *do* have files → count from files
                        if nEvents == 0 and nFiles > 0:
                            print(f"[INFO] DAS returned 0 events for {dataset}, counting events from files...")
                            nEvents = getEventsFromFiles(filesNano)

                        evtStr = formatNum(nEvents)
                        mcFilesNano[sampleKey] = [[evtStr, nEvents, nFiles], filesNano]
                        print(f"        {nFiles}\t {evtStr}\t {sampleKey}")

                # Write out JSON for this MC sub-category (if not empty)
                if mcFilesNano:
                    nanoOutName = jsonDir / f"FilesNano_{channel}_{year}_{mcName}_{subcat}.json"
                    with open(nanoOutName, 'w') as f:
                        json.dump(mcFilesNano, f, indent=4)
                else:
                    print(f"    No MC samples found for sub-category '{subcat}' in year {year}\n")

            # ---------------------------
            # Process Data samples: one output per desired period
            # ---------------------------
            dataName = "Data"
            #dataName = "DataReprocessing"
            dataDesired = yinfo.get(dataName, [])
            print(dataDesired)
            for dataPeriod in dataDesired:
                dataFilesNano = {}
                # We know the top-level key is the year (e.g. "2022"), so do:
                yearData = samplesData.get(year, {})
                if not yearData:
                    print(f"  {dataName} Year {year} not found in samples JSON!")
                    continue

                if dataPeriod not in yearData.get(f"{dataName}", {}):
                    print(f"  [Data] Period {dataPeriod} not found in samples JSON for year {year}")
                    continue

                dataBranch = yearData[dataName][dataPeriod]
                print(f"  [{dataName}/{dataPeriod}]")
                for sampleKey, dataset in dataBranch.items():
                    #print(f"    Querying sample {sampleKey} ...")
                    filesNano = getFiles(dataset)
                    if not filesNano:
                        print(f"      PROBLEM: No files found for dataset '{dataset}'.\n")
                        continue
                    nFiles = len(filesNano)
                    nEvents = getEvents(dataset)
                    evtStr = formatNum(nEvents)
                    dataFilesNano[sampleKey] = [[evtStr, nEvents, nFiles], filesNano]
                    allEventsYear += nEvents
                    print(f"      {nFiles}\t {evtStr}\t {sampleKey}")
                # Write out JSON for this data period
                if dataFilesNano:
                    nanoOutName = jsonDir / f"FilesNano_{channel}_{year}_{dataName}_{dataPeriod}.json"
                    with open(nanoOutName, 'w') as f:
                        json.dump(dataFilesNano, f, indent=4)
                else:
                    print(f"    No {dataName} samples found for period '{dataPeriod}' in year {year}\n")
            
            print(f"AllEvents for {year} = {formatNum(allEventsYear)}\n")
            allEventsChannel += allEventsYear

        print(f"AllEvents for {channel} = {formatNum(allEventsChannel)}\n")
        allEvents += allEventsChannel

    print('---------------------------------------')
    print(f"AllEvents = {formatNum(allEvents)}")
    print('---------------------------------------')

if __name__ == "__main__":
    main()

