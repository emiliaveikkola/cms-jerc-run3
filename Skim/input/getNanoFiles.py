#!/usr/bin/env python3
import os
import sys
import subprocess
import json
from pathlib import Path

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
                            print(f"        PROBLEM: No files found for dataset '{dataset}'.\n")
                            continue
                        nFiles = len(filesNano)
                        nEvents = getEvents(dataset)
                        evtStr = formatNum(nEvents)
                        mcFilesNano[sampleKey] = [[evtStr, nEvents, nFiles], filesNano]
                        allEventsYear += nEvents
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

