#!/bin/bash
#To be run on remote machine
#Take input arguments as an array
myArray=( "$@" )
#Array: Size=$#, an element=$1, all element = $@

printf "Start skimming at ";/bin/date
printf "Worker node hostname ";/bin/hostname

if [ -z ${_CONDOR_SCRATCH_DIR} ] ; then 
    echo "Running Interactively" ; 
else
    echo "Running In Batch"
    echo ${_CONDOR_SCRATCH_DIR}
	tar -zxf Skim.tar.gz
    cd Skim
    # Setup ROOT/CMS environment for building
    if [ -f /cvmfs/cms.cern.ch/cmsset_default.sh ]; then
        source /cvmfs/cms.cern.ch/cmsset_default.sh
    fi
    if command -v root-config >/dev/null 2>&1; then
        export LD_LIBRARY_PATH=$(root-config --libdir):$LD_LIBRARY_PATH
        export LIBRARY_PATH=$(root-config --libdir):$LIBRARY_PATH
    fi
    make clean
    make
fi

#Run for Base, Signal region
echo "All arguements: "$@
echo "Number of arguements: "$#
oName=$1
outDir=$2
echo "./runMain -o oName"
./runMain -o ${oName}

printf "Done skimming at ";/bin/date
#---------------------------------------------
#Copy the ouput root files
#---------------------------------------------
if [ -z ${_CONDOR_SCRATCH_DIR} ] ; then
    echo "Running Interactively" ;
else
    xrdcp -f output/${oName} ${outDir}/${oName}
    echo "Cleanup"
    cd ..
    rm -rf Skim 
fi
printf "Done ";/bin/date
