from markupsafe import Markup

supported_langs_mapping = {}  # noqa
supported_langs_mapping['English'] = 'en'
supported_langs_mapping['en'] = 'English'
supported_langs_mapping['Francais'] = 'fr'
supported_langs_mapping['fr'] = 'Francais'
supported_langs_mapping['Youth'] = 'YY'
supported_langs_mapping['YY'] = 'Youth'
locales = {} # noqa
# Note that at least locally, getting locale support requires some prep-work:
# sudo apt-get install language-pack-he-base  (or fr instead of he, etc)
# sudo dpkg-reconfigure locales
# they seemed to thankfully be supported out of the box in appengine
locales['en'] = "en_US.UTF-8"
locales['fr'] = "fr_FR.UTF-8"
locales['he'] = 'he_IL.UTF-8'
locales['YY'] = 'he_IL.UTF-8'
sections = {} # noqa
sections['keys_from_Hebrew'] = {
    "החזית הצפונית": "NORTH",
    "החזית הדרומית": "SOUTH",
    'חזית איו"ש': "YandS",
    "ביטחון": 'Security',
    "מהמתרחש בארץ": "InIsrael",
    "מדיניות, משפט ופוליטיקה": "PandP",  
    "מסביב לעולם": "Worldwide",
    "כלכלה": "Economy",
    "ספורט": "Sports",
    "מזג האוויר": "Weather",
    "ונסיים בטוב": "FinishWell"
}

sections['en'] = {
    "NORTH": "Northern Front",
    "SOUTH": "Southern Front",
    "YandS": "Yehuda and Shomron",
    "Security": "Security",
    "InIsrael": "Israel Local News",
    "PandP": "Policy, Law and Politics",
    "Worldwide": "World News",
    "Economy": "Economy",
    "Sports": "Sports",
    "Weather": "Weather",
    "FinishWell": "On a Positive Note",
    "UNKNOWN": "UNKNOWN"
}
sections['fr'] = {
    "NORTH": Markup("Au nord"),
    "SOUTH": Markup("Au sud"),
    "YandS": "Yehouda et Shomron",
    "Security": "Sécurité",
    "InIsrael": Markup("En Israël"),
    "PandP": "Politique",
    "Worldwide": "Autour du monde",
    "Economy": "Economie",
    "Sports": "Sport",
    "Weather": "Météo",
    "FinishWell": "Et on termine sur une note positive 🎶",
    "UNKNOWN": "UNKNOWN"
}
sections['he'] = {
    "NORTH": "החזית הצפונית",
    "SOUTH": "החזית הדרומית",
    "YandS": 'חזית איו"ש',
    "Security": "ביטחון",
    "InIsrael": "מהמתרחש בארץ",
    "PandP": "מדיניות, משפט ופוליטיקה",
    "Worldwide": "מסביב לעולם",
    "Economy": "כלכלה",
    "Sports": "ספורט",
    "Weather": "מזג האוויר",
    "FinishWell": "ונסיים בטוב",
    "UNKNOWN": "UNKNOWN"
}
sections['YY'] = sections["he"]

keywords = {}  # noqa
keywords['en'] = {
    "edition": "edition",
    "intro_pin": "war of iron swords",
    "northern": "northern ",
    "southern": "southern ",
    "jands": "iosh",
    "security": "security",
    "policy": "policy",
    "politics": "politics",
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
    "security": "sécurité",
    "jands": "iosh",
    "policy": "politique",
    "politics": "politique",
    "in the world": "UNKNOWN",
    "in israel": "en israël",
    "world": "le monde",
    "weather": "météo",
    "economy": "économie",
    "sport": "sport",
    "finish": "bien"
}
keywords['he'] = {
    "edition": "מהדורת",
    "intro_pin": "מלחמת חרבות ברזל",
    "northern": "הצפונית",
    "southern": "הדרומית",
    "jands": 'חזית איו"ש',
    "security": "ביטחון",
    "policy": "מדיניות",
    "politics": "ופוליטיקה",
    "in the world": "מסביב לעולם",
    "in israel": "מהמתרחש בארץ",
    "world": "עולם",
    "weather": "מזג האוויר",
    "economy": "כלכלה",
    "sport": "ספורט",
    "finish": "ונסיים"
}
keywords['YY'] = keywords["he"]

editions = {}  # noqa
editions['en'] = ['Morning', 'Afternoon', 'Evening']
editions['fr'] = ['Matin', Markup("l'après-midi"), 'soir']
editions['he'] = ['בוקר', 'צוהריים', 'ערב']
editions['YY'] = ['בוקר', 'צוהריים', 'ערב']
