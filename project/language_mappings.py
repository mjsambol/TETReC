##################################################################################
#
# Team Text Editing, Translation and Review Coordination tool
# Copyright (C) 2023-2025, Moshe Sambol, https://github.com/mjsambol
#
# Originally created for the Tamtzit Hachadashot / News In Brief project
# of the Lokhim Ahrayut non-profit organization
# Published in English as "Israel News Highlights"
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
#################################################################################

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
locales['H1'] = 'he_IL.UTF-8'
sections = {} # noqa
sections['keys_from_Hebrew'] = {
    "מלחמת חרבות ברזל": "SwordsOfIron",
    'מבצע "עם כלביא"': "RISING-LION",
    "החזית הדרומית": "SOUTH",
    "החזית הצפונית": "NORTH",
    "החזית מול תימן": "YEMEN",
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
    "SwordsOfIron": "Swords of Iron",
    "RISING-LION": "Operation Rising Lion",
    "SOUTH": "Southern Front",
    "NORTH": "Northern Front",
    "YEMEN": "Yemeni Front",
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
    "SwordsOfIron": "Guerre des Épées de Fer",
    "RISING-LION": Markup('Opération "Rising Lion" (Am Kélavi)'),
    "SOUTH": Markup("Au sud"),
    "NORTH": Markup("Au nord"),
    "YEMEN": Markup("Le front face au Yémen"),
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
    "SwordsOfIron": "מלחמת חרבות ברזל",
    "RISING-LION": 'מבצע "עם כלביא"',
    "SOUTH": "החזית הדרומית",
    "NORTH": "החזית הצפונית",
    "YEMEN": "החזית מול תימן",
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

translated_section_names = {}
for target_lang in ['en', 'fr']:
    translated_section_names[target_lang] = {
        section_name_in_he: sections[target_lang][sections['keys_from_Hebrew'][section_name_in_he]]
        for section_name_in_he in sections['keys_from_Hebrew'].keys()}
for target_lang in ['he', 'YY']:  # necessary for daily summary
    translated_section_names[target_lang] = {
        section_name_in_he: section_name_in_he for section_name_in_he in sections['keys_from_Hebrew'].keys()}


keywords = {}  # noqa
keywords['en'] = {
    "edition": "edition",
    "intro_pin": ["war of iron swords", "iron swords war", "swords of iron"],
    "rising-lion": "lion",
    "northern": "northern ",
    "southern": "southern ",
    "yemen": ["yemen", "yemeni"],
    "jands": "iosh",
    "security": "security",
    "policy": ["policy", "politics"],
    "politics": "politics",
    "in the world": "in the world",
    "in israel": ["in israel", "israel local news"],
    "world": "world",
    "weather": "weather",
    "economy": "economy",
    "sport": "sport",
    "finish": ["finish", "good note", "end well", "positive note"]
}
keywords['fr'] = {
    "edition": "édition",
    "intro_pin": "guerre des épées de fer",
    "rising-lion": "lion",
    "northern": " nord",
    "southern": " sud",
    "yemen": " yémen",
    "security": "sécurité",
    "jands": "iosh",
    "policy": "politique",
    "politics": "politique",
    "in the world": "UNKNOWN",
    "in israel": "en israël",
    "world": " monde",
    "weather": "météo",
    "economy": "économie",
    "sport": "sport",
    "finish": ["bien", "note positive"]
}
keywords['he'] = {
    "edition": "מהדורת",
    "intro_pin": "מלחמת חרבות ברזל",
    "rising-lion": "כלביא",
    "northern": "הצפונית",
    "southern": "הדרומית",
    "yemen": "תימן",
    "jands": 'חזית איו"ש',
    "security": "ביטחון",
    "policy": ["מדיניות", "ופוליטיקה"],
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
editions['H1'] = ['בוקר', 'צוהריים', 'ערב']
