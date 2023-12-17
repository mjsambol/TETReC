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


title_translations = {
    # This section of translations is based on an image shared by Yair, original source unknown
    'רב"ט': 'Corporal',
    'סמל': 'Sergeant',
    'סמ"ר': 'Staff Sergeant',

    'רב סמל': 'Sergeant First Class',
    'רס"ל': 'Sergeant First Class',

    'רב סמל ראשון': 'Master Sergeant', # < switching to that based on other news sources and Ilana's friend. Originally had: 'Chief Sergeant First Class',
    'רס"ר': 'Master Sergeant',       # < switching to that based on other news sources and Ilana's friend. Originally had: 'Chief Sergeant First Class',
    'רס"מ': 'Sergeant Major',        # < switching to that based on other news sources and Ilana's friend. Originally had: 'Master Sergeant',
    'רס"ם': 'Sergeant Major',        # < switching to that based on other news sources and Ilana's friend. Originally had: 'Master Sergeant',

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
    'מח"ט': 'Brigade Commander',
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
}

def pre_translation_swaps(text, target_language_code):
    for title in title_translations:
        text = re.sub(fr'\b(ו?)(ה?){title}\b', vav_hey(title_translations[title]), text, re.U)

    # our Motzei Shabbat header is confused for regular content, this is an easy way to get rid of it
    text = re.sub(r'\*עדכון מוצאי שבת\*', '', text, re.U)
    text = re.sub(r'קוראים יקרים, זהו עדכון מקוצר. מהדורה רגילה תישלח אחרי 21:00.', '', text, re.U)

    if target_language_code == 'en':
        text = re.sub(r'\bהי"ד\b',   'HYD', text, re.U)
        
        text = re.sub(r'\b(ב)צו?הריים\b', lambda m: ("in " if m.group(1).startswith("ב") else '') + 'the afternoon', 
                    text, re.U)
        text = re.sub(r'\b(אחר )?ה?צו?הריים\b', 'the afternoon', text, re.U)

        text = re.sub(r'\bהלילה\b', 'last night', text, re.U)

        text = re.sub(r'\b([למהבו]+)?עוטף עזה\b', lambda m: tx_heb_prefix(m.group(1), "en") + 'the Gaza envelope', text, re.U)
        text = re.sub(r'\b([למהבו]+)?עוטף\b', lambda m: tx_heb_prefix(m.group(1), "en") + 'the Gaza envelope [?]', text, re.U)

        text = re.sub(r'\bהסברה\b', 'hasbara (public diplomacy)', text, re.U)

    elif target_language_code == 'fr':
        text = re.sub(r'\bהלילה\b', 'la nuit dernière', text, re.U)

        text = re.sub(r'\b([למהבו]+)?עוטף עזה\b', lambda m: tx_heb_prefix(m.group(1), "fr") + 'La zone autour de Gaza', text, re.U)
        text = re.sub(r'\b([למהבו]+)?עוטף\b', lambda m: tx_heb_prefix(m.group(1), "fr") + 'La zone autour de Gaza [?]', text, re.U)

        text = re.sub(r'\bהסברה\b', 'diplomatie publique', text, re.U)

    return text


def post_translation_swaps(text, target_language_code):
    if target_language_code == 'en':
        text = re.sub('infrastructures', 'infrastructure', text, re.IGNORECASE)
        text = re.sub(r'\balarm(s?)\b', lambda m: "siren" + ('s' if m.group(1).startswith("s") else ''), text, re.IGNORECASE)
        text = re.sub(r'\b(a)n siren', "\\1 siren", text, re.IGNORECASE)
        text = re.sub('martyrs?', 'fallen', text, re.IGNORECASE)
    elif target_language_code == 'fr':
        text = re.sub(r'\balarm(s?)\b', lambda m: "alert" + ('s' if m.group(1).startswith("s") else ''), text, re.IGNORECASE)

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