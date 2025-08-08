import os
import sys
import json
import math
import itertools
import subprocess
import multiprocessing
from datetime import datetime

sys.dont_write_bytecode = True
sys.path.insert(0, os.getcwd().replace("condor", ""))
from Inputs import *


def check_git_status():
    """Check that there are no uncommitted changes and that the local branch is pushed."""
    # Check for uncommitted changes
    try:
        status = subprocess.check_output(["git", "status", "--porcelain"]).decode("utf-8").strip()
    except subprocess.CalledProcessError as e:
        print("Error running git status")
        sys.exit(1)
    if status:
        print("ERROR: There are uncommitted changes in your repository. Please commit your changes before submitting jobs.")
        sys.exit(1)
    
    # Check if local branch is ahead of remote
    try:
        # Update remote information
        subprocess.check_call(["git", "fetch"])
        # Get current branch name
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode("utf-8").strip()
        # Count commits ahead of remote
        ahead_count = subprocess.check_output(
            ["git", "rev-list", "HEAD...origin/{}".format(branch), "--count"]
        ).decode("utf-8").strip()
    except subprocess.CalledProcessError as e:
        print("Error checking if your branch is ahead of remote.")
        sys.exit(1)
    if int(ahead_count) > 0:
        print(f"ERROR: Your local branch '{branch}' is ahead of origin by {ahead_count} commits. Please push before submitting jobs.")
        sys.exit(1)
    print("Git status check passed: Repository is clean and synchronized with remote.")

def get_git_info():
    """Retrieve the short commit hash and current date."""
    try:
        git_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode("utf-8").strip()
    except subprocess.CalledProcessError:
        git_hash = "unknown"
    # Include hours, minutes, and seconds to ensure uniqueness even on the same day 
    current_date = datetime.now().strftime("date-%d%b%Y_time-%H%M%S")
    return current_date, git_hash



def create_skim_json(ch, year, dataOrMc, sample, version_suffix, allJobsChYear):
    outPath = f"{outSkimDir}/{ch}/{year}/{dataOrMc}/{sample}/{version_suffix}"
    os.system(f"gfal-mkdir -p {outPath}")
   
    chYearOther = f"{ch}_{year}_{dataOrMc}_{sample}" 
    # Read the Nano json
    nano_json_path = f"../input/nano_files/FilesNano_{chYearOther}.json"
    print(f"\n{nano_json_path}")
    if not os.path.exists(nano_json_path):
        print(f"ERROR: JSON file {nano_json_path} does not exist.")
        sys.exit(1)
    with open(nano_json_path, "r") as f:
        nano_json_load = json.load(f)
    
    skim_file_dict = {}
    # Loop over each sampleKey and update file paths in the list.
    for sampleKey, nano_list in nano_json_load.items():
        nEvents = nano_list[0][1]
        nFiles  = nano_list[0][2]
        nJobs = math.ceil(nEvents / eventsPerJobMC)
        if "Data" in sampleKey: 
            nJobs = math.ceil(nEvents / eventsPerJobData)
        nJobs = min(nJobs, nFiles)
        allJobsChYear += nJobs
        print(f"\t{nJobs}\t {sampleKey}")
        skimFiles = [
            f"{outPath}/{sampleKey}_Skim_{i+1}of{nJobs}.root"
            for i in range(nJobs)
        ]
        skim_file_dict[sampleKey] = skimFiles

    # Write the modified JSON into {tmpSubDir} with a new file name.
    skim_json_path_version = os.path.join(f"{tmpSubDir}", f"FilesSkim_{chYearOther}_{version_suffix}.json")
    with open(skim_json_path_version, "w") as f:
        json.dump(skim_file_dict, f, indent=4)
    skim_json_name = f"FilesSkim_{chYearOther}.json"
    print({skim_json_path_version})
    #print(f"Output dir: {outPath}")
    
    os.system(f"cp {skim_json_path_version} skim_files/{skim_json_name}")
    os.system(f"cp {skim_json_path_version} skim_files/archive")
    
    #print(f"Modified JSON file created: {skim_json_path_version}")
    return skim_json_path_version,  allJobsChYear


def createJobs(jsonFile, jdlFile, logDir="log"):
    os.system(f"mkdir -p {tmpSubDir}/{logDir}")
    os.system(f"cp /tmp/%s {tmpSubDir}" % vomsProxy)
    common_command = \
    'Universe   = vanilla\n\
should_transfer_files = YES\n\
when_to_transfer_output = ON_EXIT\n\
Transfer_Input_Files = Skim.tar.gz, runMain.sh\n\
x509userproxy        = %s\n\
+MaxRuntime = 60*60*24\n\
max_retries = 2\n\
Output = %s/log_$(cluster)_$(process).stdout\n\
Log = %s/log_$(cluster)_$(process).log\n\
Error  = %s/log_$(cluster)_$(process).stderr\n\n' % (vomsProxy, logDir, logDir, logDir)

    #---------------------------------------------
    #Create jdl (job description language) files
    #---------------------------------------------
    data = json.load(jsonFile)
    jdlFile.write('Executable =  runMain.sh \n')
    jdlFile.write(common_command)
    # Generate one queue with explicit infile/outdir pairs
    jdlFile.write("arguments = $(in) $(out)\n")
    jdlFile.write("queue in, out from (\n")
    for sKey, skims in data.items():
        for skim in skims:
            outDir = skim.rsplit(sKey, 1)[0]
            restStr = skim.split(sKey, 1)[1]
            oName = f"{sKey}{restStr}"
            jdlFile.write(f"  {oName} {outDir}\n")
    jdlFile.write(")\n")

if __name__ == "__main__":
    # --- Step 1: Check Git status ---
    #check_git_status()
    os.system("voms-proxy-init --voms cms")

    # --- Step 2: Retrieve Git info ---
    current_date, git_hash = get_git_info()
    version_suffix = f"{current_date}_commit-{git_hash}"
    print(f"Using version: {version_suffix}")

    # --- Prepare temporary submission directory ---
    if os.path.exists(f"{tmpSubDir}"):
        os.system(f"rm -r {tmpSubDir}")
        print(f"Deleted dir: {tmpSubDir}")
    os.system(f"mkdir -p {tmpSubDir}")
    tarFile = f"{tmpSubDir}/Skim.tar.gz"
    os.system("tar --exclude condor --exclude input/old --exclude obj --exclude *.root --exclude output -zcvf %s ../../Skim" % tarFile)
    os.system(f"cp runMain.sh {tmpSubDir}/")
    print(f"Created dir: {tmpSubDir}")
    submitAll = open(f"{tmpSubDir}/submitAll.sh", "w") 

    # --- Process years and channels ---
    allJobs = 0
    logDir   = "log"
    for year, ch in itertools.product(list(Years.keys()), Channels):
        os.system(f"mkdir -p skim_files/archive")
        allJobsChYear = 0
        for dataOrMc, samples in Years[year].items():
            for sample in samples:
                jdlName  = f'submitJobs_{ch}_{year}_{dataOrMc}_{sample}.jdl'
                jdlFile  = open(f'{tmpSubDir}/{jdlName}', 'w')
                # Create a modified JSON file in {tmpSubDir} with updated output paths.
                skim_json_path, allJobsChYear = create_skim_json(ch, year, dataOrMc, sample, version_suffix, allJobsChYear)
                skim_json_path_ = open(skim_json_path, "r")
                createJobs(skim_json_path_, jdlFile, logDir)
                submitAll.write(f'condor_submit {jdlName}\n')
                jdlFile.close() 
        allJobs+=allJobsChYear
        print(f"\nAllJobs for {year}: {ch} = {allJobsChYear}\n")
    print(f"Job submission scripts created in {tmpSubDir}/")
    print('---------------------------------------')
    print(f"AllJobs = {allJobs}")
    print('---------------------------------------')
    print(f"Output Parent Dir: {outSkimDir}")
    submitAll.close()

