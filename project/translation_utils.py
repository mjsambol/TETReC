import re
from google.cloud import translate
from .common import debug

PROJECT_ID = "tamtzit-hadashot"
PARENT = f"projects/{PROJECT_ID}"

def vav_hey(title):
    # this lambda works but is a bit hard to read
    # return lambda match: ("and " if match.group(1).startswith("ו") else '') + ("the " + title if match.group(2).startswith("ה") else title)
    def translate_prefix(match):
        result = ''
        if match.group(1).startswith('ו'):
            result = 'and '
        if match.group(2).startswith('ה'):
            result = result + 'the '
        result += title
        return result
    return translate_prefix


def tx_heb_prefix(word, lang):
    # use caution - assumes that the letters בולמה are intended as prefixes
    # do not use this with words which have one of those letters as part of the main word!
    if not word or not lang or word == "" or lang == "":
        debug(f"tx_heb_prefix: uhoh got {word} - {lang}")
        return ""
    result = ""
    if lang == "en":
        for char in word:
            if char == "ב":
                result = result + "in "
            if char == "ו":
                result = result + "and "
            if char == "ל":
                result = result + "to "
            if char == "מ":
                result = result + "from "
            if char == "ה":
                result = result + "the "
    elif lang == "fr":
        for char in word:
            if char == "ב":
                result = result + "en "
            if char == "ו":
                result = result + "et "
            if char == "ל":
                result = result + "à "
            if char == "מ":
                result = result + "dès "
            if char == "ה":
                result = result + "la "
    return result


title_translations = {"en":{
    # This section of translations is based on an image shared by Yair, original source unknown
    'רב"ט': 'Corporal',
    'סמל': 'Sergeant',
    'סמ"ר': 'Staff Sergeant',

    'רב סמל': 'Sergeant First Class',
    'רס"ל': 'Sergeant First Class',

    'רב סמל ראשון': 'Master Sergeant', # < switching based on other sources and Ilana's friend. Originally had: 'Chief Sergeant First Class',
    'רס"ר': 'Master Sergeant',       # < Originally had: 'Chief Sergeant First Class',
    'רס"מ': 'Sergeant Major',        # < Originally had: 'Master Sergeant',
    'רס"ם': 'Sergeant Major',        # < Originally had: 'Master Sergeant',

    'רס"ב': 'First Sergeant',
    'רנ"מ': 'Sergeant Major',        # "apparently doesn't exist anymore" per Ilana's friend
    'רנ"ם': 'Sergeant Major',        # "apparently doesn't exist anymore" per Ilana's friend
    'רנ"ג': 'Command Sergeant Major',

    'סג"מ': 'Second Lieutenant',
    'סג"ם': 'Second Lieutenant',
    'סגן': 'First Lieutenant',
    'סרן': 'Captain',

    'רב סרן': 'Major',
    'רס"ן': 'Major',
    'רס"נ': 'Major',

    'סא"ל': 'Lieutenant Colonel',
    'סגן אלוף': 'Lieutenant Colonel',

    'אלוף משנה': 'Colonel',
    'אל"מ': 'Colonel',
    'אל"ם': 'Colonel',

    'תת אלוף': 'Brigadier General',
    'תא"ל': 'Brigadier General',

    'אלוף': 'Major General',
    'רב אלוף': 'Lieutenant General',
    'רא"ל': 'Lieutenant General',

    # This section of translations is based on https://www.almaany.com/en/dict/en-he/commander/
    # which is a surprising source but nothing here seems controversial
    'רמטכ"ל': 'Chief of General Staff',     # More accurate translation than this source's 'Commander in Chief',
    'מ"פ': 'Company Commander',
    'מג"ד': 'Battalon Commander',
    'סמג"ד': 'Deputy Battalon Commander',
    'מח"ט': 'Brigade Commander',
    'סמח"ט': 'Deputy Commander of Brigade',
    'מא"ז': 'District Commander',
    'מש"ט': 'Flight Commander',
    'מ"מ': 'Platoon Commander',
    'מט"ק': 'Tank Commander',
    # not 100% sure about this one... it's also an abbreviation for mefaked she'eino katzin
    # 'מש"ק': 'Tank Company Commander',   
    # end section

    # this came up in conversation, seems straightforward though I don't have an official source
    'סמ"פ': 'Deputy Company Commander',

    # from a stamp shared by Chana
    'רבשצ': 'Military Security Coordinator',
    'רבש"צ': 'Military Security Coordinator',
    'כיתת הכוננות': 'First Response Squad'
}, 
"fr": {
    'רב"ט': 'Première classe',
    'סמל': 'Caporal',
    'סמ"ר': 'Caporal-chef',
    'סמל ראשון': 'Caporal-chef',

    'רב סמל': 'Sergent',
    'רס"ל': 'Sergent',

    'רב סמל ראשון': 'Sergent-chef', 
    'רס"ר': 'Sergent-chef',
    'רס"מ': 'Adjudant',       
    'רס"ם': 'Adjudant',       

    'רס"ב': 'Adjudant-chef',
    # 'רנ"מ': 'Sergeant Major',        # "apparently doesn't exist anymore" per Ilana's friend
    # 'רנ"ם': 'Sergeant Major',        # "apparently doesn't exist anymore" per Ilana's friend
    'רנ"ג': 'Major',
    'רב נגד': 'Major',

    'סג"מ': 'Sous-lieutenant',
    'סג"ם': 'Sous-lieutenant',
    'סגן משנה': 'Sous-lieutenant',
    'סגן': 'Lieutenant',
    'סרן': 'Capitaine',

    'רב סרן': 'Commandant',
    'רס"ן': 'Commandant',
    'רס"נ': 'Commandant',

    'סא"ל': 'Lieutenant-colonel',
    'סגן אלוף': 'Lieutenant-colonel',

    'אלוף משנה': 'Colonel',
    'אל"מ': 'Colonel',
    'אל"ם': 'Colonel',

    'תת אלוף': 'Général de brigade',
    'תא"ל': 'Général de brigade',

    'אלוף': 'Général',
    'רב אלוף': "Chef d'état-major",
    'רא"ל': "Chef d'état-major",
}
}

def pre_translation_swaps(text, target_language_code):
    if target_language_code in title_translations:
        for title in title_translations[target_language_code]:
            text = re.sub(fr'\b(ו?)(ה?){title}\b', vav_hey(title_translations[target_language_code][title]), text, flags=re.U)

    # our Motzei Shabbat header is confused for regular content, this is an easy way to get rid of it
    text = re.sub(r'\*עדכון מוצאי שבת\*', '', text, flags=re.U)
    text = re.sub(r'קוראים יקרים, זהו עדכון מקוצר. מהדורה רגילה תישלח אחרי 21:00.', '', text, flags=re.U)
    # and this is from the Friday afternoon edition
    text = re.sub(r'\*קוראים יקרים,\*', '', text, flags=re.U)
    text = re.sub(r'\*המהדורה הבאה תישלח במוצאי שבת, בשעה הרגילה של מהדורת הערב.\*', '', text, flags=re.U)

    text = re.sub(r'\bמשגב עם\b', 'Misgav Am', text, flags=re.U)

    if target_language_code == 'en':
        text = re.sub(r'\bהי"ד\b',   'HYD', text, flags=re.U)
        
        text = re.sub(r'\b(ב)צו?הריים\b', lambda m: ("in " if m.group(1).startswith("ב") else '') + 'the afternoon', 
                    text, flags=re.U)
        text = re.sub(r'\b(אחר )?ה?צו?הריים\b', 'the afternoon', text, flags=re.U)

        text = re.sub(r'\bהלילה\b', 'last night', text, flags=re.U)

        text = re.sub(r'\b([למהבו]+)?עוטף עזה\b', lambda m: tx_heb_prefix(m.group(1), "en") + 'the Gaza envelope', text, flags=re.U)
        text = re.sub(r'\b([למהבו]+)?עוטף\b', lambda m: tx_heb_prefix(m.group(1), "en") + 'the Gaza envelope [?]', text, flags=re.U)

        text = re.sub(r'\bהסברה\b', 'hasbara (public diplomacy)', text, flags=re.U)
        text = re.sub(r'\b([למהבו]+)?חלל(י)?\b', lambda m: tx_heb_prefix(m.group(1), "en") + 'fallen', text, flags=re.U)
        text = re.sub(r'\b([למהבו]+)?כטמ"[מם]\b', lambda m: tx_heb_prefix(m.group(1), "en") + "remotely operated UAV", text, flags=re.U) 
        text = re.sub(r'\b([למהבו]+)?אמל"ח\b', lambda m: tx_heb_prefix(m.group(1), "en") + "weapons", text, flags=re.U)
        text = re.sub(r'\b([למהבו]+)?חטוף\b', lambda m: tx_heb_prefix(m.group(1), "en") + "hostage", text, flags=re.U)
        text = re.sub(r'\b([למהבו]+)?חטופים\b', lambda m: tx_heb_prefix(m.group(1), "en") + "hostages", text, flags=re.U)
        text = re.sub(r'\bחטיבת ה?אש\b', "artillery brigade", text, flags=re.U)
        text = re.sub(r'\b([למהבו]+)?יחידת ה?לוט"ר\b', lambda m: tx_heb_prefix(m.group(1), "en") + "LOTAR (counter-terrorism special forces) unit", text, flags=re.U)
        text = re.sub(r'\b([למהבו]+)?אגורות\b', lambda m: tx_heb_prefix(m.group(1), "en") + "agorot", text, flags=re.U)
        text = re.sub(r'\b([למהבו]+)?אגורה\b', lambda m: tx_heb_prefix(m.group(1), "en") + "agora", text, flags=re.U)
        text = re.sub(r'\b([למהבו]+)?מרגש\b', lambda m: tx_heb_prefix(m.group(1), "en") + "moving", text, flags=re.U)

    elif target_language_code == 'fr':
        text = re.sub(r'\bבית משפט מחוזי\b', "Cour d'Appel", text, flags=re.U)
        text = re.sub(r'\bהותר לפרסום\b', "Il a été autorisé à la publication", text, flags=re.U)
        text = re.sub(r'\bיהי זכרו ברוך\b', "Que sa mémoire soit bénie", text, flags=re.U)
        text = re.sub(r'\bיהי זכרם ברוך\b', "Que leur mémoire soit bénie", text, flags=re.U)
        text = re.sub(r'\bיישוב\b', "localité", text, flags=re.U)
        text = re.sub(r'\bיישובים\b', "localités", text, flags=re.U)
        text = re.sub(r'\bכותל המערבי\b', "Kotel", text, flags=re.U)
        text = re.sub(r'\bהלילה\b', 'la nuit dernière', text, flags=re.U)

        text = re.sub(r'\b([למהבו]+)?עוטף עזה\b', lambda m: tx_heb_prefix(m.group(1), "fr") + 'La zone autour de Gaza', text, flags=re.U)
        text = re.sub(r'\b([למהבו]+)?עוטף\b', lambda m: tx_heb_prefix(m.group(1), "fr") + 'La zone autour de Gaza [?]', text, flags=re.U)

        text = re.sub(r'\bהסברה\b', 'diplomatie publique', text, flags=re.U)
        text = re.sub(r'\b([למהבו]+)כטב"[מם]\b', lambda m: tx_heb_prefix(m.group(1), "fr") + "drone", text, flags=re.U) 
        text = re.sub(r'\b([למהבו]+)כטמ"[מם]\b', lambda m: tx_heb_prefix(m.group(1), "fr") + "drone de combat", text, flags=re.U) 

    return text


def post_translation_swaps(text, target_language_code):
    if target_language_code == 'en':
        text = re.sub('infrastructures', 'infrastructure', text, flags=re.IGNORECASE)
        text = re.sub(r'\balarm(s?)\b', lambda m: "siren" + ('s' if m.group(1).startswith("s") else ''), text, flags=re.IGNORECASE)
        text = re.sub(r'\b(a)n siren', "\\1 siren", text, flags=re.IGNORECASE)
        text = re.sub('martyrs?', 'fallen', text, flags=re.IGNORECASE)
        text = re.sub('allowed to be published', 'released for publication', text, flags=re.IGNORECASE)
        text = re.sub("Judea and Samaria", "Yehuda and Shomron", text, flags=re.IGNORECASE)
        text = re.sub("Beer Sheva", "Be'er Sheva", text, flags=re.IGNORECASE)
        text = re.sub("slightly injured", "lightly injured", text, flags=re.IGNORECASE)

    elif target_language_code == 'fr':
        text = re.sub(r'\balarm(s?)\b', lambda m: "alert" + ('s' if m.group(1).startswith("s") else ''), text, flags=re.IGNORECASE)

    text = re.sub(r'\bGalant\b', 'Gallant', text)
    
    return text


def translate_text(text: str, target_language_code: str, source_language='he') -> translate.Translation:

    text = pre_translation_swaps(text, target_language_code)

    break_point = text.find("📌", text.find("📌") + 1)
    if break_point == -1:
        break_point = len(text)
    first_section = text[0:break_point]
    second_section = text[break_point:]

    debug(f"translate_text(): Hebrew is -----\n{text}\n-----")
    debug(f"first section length: {len(first_section)}")
    debug(f"second section length: {len(second_section)}")
    client = translate.TranslationServiceClient()

    result = ""
    for section in [first_section, second_section]:
        if len(section.strip()) == 0:
            continue
        response = client.translate_text(
            parent=PARENT,
            contents=[section],
            source_language_code=source_language,  # optional, can't hurt
            target_language_code=target_language_code,
            mime_type='text/plain' # HTML is assumed!
        )
        result += response.translations[0].translated_text

    result = post_translation_swaps(result, target_language_code)
    # print(f"DEBUG: translation result has {len(response.translations)} translations")
    # if len(response.translations) > 1:
    #     print("DEBUG: the second one is:")
    #     print(response.translations[1].translated_text)
    return result