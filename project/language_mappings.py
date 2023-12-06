from markupsafe import Markup

supported_langs_mapping = {}
supported_langs_mapping['English'] = 'en' 
supported_langs_mapping['en'] = 'English' 
supported_langs_mapping['Francais'] = 'fr'
supported_langs_mapping['fr'] = 'Francais'
supported_langs_mapping['Youth'] = 'YY'
supported_langs_mapping['YY'] = 'Youth'
locales = {}
# Note that at least locally, getting locale support requires some prep-work:
# sudo apt-get install language-pack-he-base  (or fr instead of he, etc)
# sudo dpkg-reconfigure locales
# they seemed to thankfully be supported out of the box in appengine
locales['en'] = "en_US.UTF-8"
locales['fr'] = "fr_FR.UTF-8"
locales['he'] = 'he_IL.UTF-8'
locales['YY'] = 'he_IL.UTF-8'
sections = {}
sections['keys_from_Hebrew'] = {
    "הזירה הדרומית": "SOUTH",
    "הזירה הצפונית": "NORTH",
    "יהודה ושומרון": "YandS",
    "מהמתרחש בארץ": "InIsrael",
    "מדיניות, ממשל ופוליטיקה": "PandP",  # an old version still sometimes in use
    "מדיניות, משפט ופוליטיקה": "PandP",  
    "מסביב לעולם": "Worldwide",
    "כלכלה": "Economy",
    "ספורט":"Sports",
    "מזג האוויר":"Weather",
    "ונסיים בטוב":"FinishWell"
}

sections['en'] = {"SOUTH":"Southern Front", 
            "NORTH":"Northern Front", 
            "YandS":"Yehuda and Shomron",
#            "Civilian":"Civilian Front", 
            "InIsrael":"Israel Local News",
            "PandP":"Policy, Law and Politics",
#            "WorldEyes":"In the Eyes of the World", 
            "Worldwide":"World News",
            "Economy":"Economy",
            "Sports":"Sports",
            "Weather":"Weather",
            "FinishWell":"On a Positive Note",
            "UNKNOWN":"UNKNOWN"
            }
sections['fr'] = {"SOUTH":Markup("Au sud"), 
            "NORTH":Markup("Au nord"), 
            "YandS":"Yehuda et Shomron",
#            "Civilian":"Civilian Front", 
            "InIsrael":Markup("Ce qu'il se passe en Israël"),
            "PandP":"Politique",
#            "WorldEyes":"Autour du monde", 
            "Worldwide":"Autour du monde",
            "Economy":"Economie",
            "Sports":"Sport",
            "Weather":"Météo",
            "FinishWell":"Et on termine sur une bonne note 🎶",
            "UNKNOWN":"UNKNOWN"
            }
sections['YY'] = {"SOUTH":"הזירה הדרומית", 
            "NORTH":"הזירה הצפונית", 
            "YandS":"יהודה ושומרון",
#            "Civilian":"Civilian Front", 
            "InIsrael":"מהמתרחש בארץ",
            "PandP":"מדיניות, משפט ופוליטיקה",
#            "WorldEyes":"In the Eyes of the World", 
            "Worldwide":"מסביב לעולם",
            "Economy":"כלכלה",
            "Sports":"ספורט",
            "Weather":"מזג האוויר",
            "FinishWell":"ונסיים בטוב",
            "UNKNOWN":"UNKNOWN"
            }
keywords = {}
keywords['en'] = {
    "edition": "edition",
    "intro_pin": "war of iron swords",
    "northern":"northern ",
    "southern":"southern ",
    "jands":"judea and samaria",
    "policy":"policy",
    "politics":"politics",
    "in the world": "in the world",
    "in israel": "in israel",
    "world": "world",
    "weather": "weather",
    "economy": "economy",
    "sport": "sport",
    "finish": "finish"
}
keywords['fr'] = {
    "edition": "édition",
    "intro_pin": "guerre des épées de fer",
    "northern": "nord ",
    "southern": "sud ",
    "jands": "judée et samarie",
    "policy": "politique",
    "politics": "politique",
    "in the world":"UNKNOWN",
    "in israel": "en israël",
    "world": "le monde",
    "weather": "météo",
    "economy": "economie",
    "sport": "sport",
    "finish": "finir"
}
keywords['YY'] = {
    "edition": "מהדורת",
    "intro_pin": "מלחמת חרבות ברזל",
    "northern":"הצפונית",
    "southern":"הדרומית",
    "jands":"יהודה ושומרון",
    "policy":"מדיניות",
    "politics":"ופוליטיקה",
    "in the world": "מסביב לעולם",
    "in israel": "מהמתרחש בארץ",
    "world": "עולם",
    "weather": "מזג האוויר",
    "economy": "כלכלה",
    "sport": "ספורט",
    "finish": "ונסיים"
}
editions = {}
editions['en'] = ['Morning', 'Afternoon', 'Evening']
editions['fr'] = ['Matin', Markup("l'après-midi"), 'soir']
editions['he'] = ['בוקר', 'צוהריים', 'ערב']
editions['YY'] = ['בוקר', 'צוהריים', 'ערב']
