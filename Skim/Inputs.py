# Skim/Inputs.py

# Directory where skimmed files will be stored
outSkimDir = "/eos/user/e/eveikkol/Skim" 

# Years and Channels to process
Year2022 = {
    "MC": [
        "GJets", "QCD"
    ],
    "Data": [
        #"2022B", "2022C", "2022D", "2022E", "2022F", "2022G"
    ]
}

Year2023 = {
    "MC": [
        "GJets", "QCD", "Other"
    ],
    "Data": [
        #"2023B", "2023C", "2023D"
    ]
}

Year2024 = {
    "MC": [
        #"GJets", "QCD"
        #"TTtoLNu2Q"
    ],
    "MCSummer24": [
        #"GJets", "GJetsSherpa", "QCD"
        #"GJetsSherpa"
        #"TTtoLNu2Q"
    ],
    "Data": [
        #"2024FCCv2DIv3", 
        #"2024A", "2024B", 
        #"2024C", "2024D", "2024E", "2024F", "2024G", "2024H", "2024I"
        #"2024F", "2024G", "2024H", "2024I"
    ],
    "DataReprocessing": [
        #"2024C", "2024D", "2024E"
    ]
}

Year2025 = {
    "MCWinter25": [
        #"GJets", "QCD"
        #"TTtoLNu2Q"
    ],
    "Data": [
        #"2025C", 
        #"2025D",
        #"2025E",
        #"2025F",
        #"2025G"
    ],
}

Year2026 = {
    "Data": [
        #"2026A" 
        "2026B"
    ],
}


Years = {}
#Years['2022'] = Year2022
#Years['2023'] = Year2023
Years['2024'] = Year2024
Years['2025'] = Year2025
Years['2026'] = Year2026


Channels = [
    #'ZeeJet',
    #'ZmmJet',
    #'GamJet',
    'Wqqm',
    #'Wqqe',
    #'WqqDiLep',
    #'MultiJet',
]

# VOMS Proxy path (adjust as needed)
vomsProxy = "x509up_u151063"

# Events per job
eventsPerJobMC = 2e6  # Number of events per job for MC
eventsPerJobData = 8e6  # Number of events per job for Data

tmpSubDir = "tmpSub"
