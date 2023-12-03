import re

def debug(stuff):
    print(stuff)

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
    if not word or not lang or word == "" or lang == "":
        debug(f"tx_heb_prefix: uhoh got {word} - {lang}")
        return ""
    if lang == "en":
        if word.startswith("ב"):
            return "in "
        if word.startswith("ו"):
            return "and "
        if word.startswith("ל"):
            return "to "
        if word.startswith("מ"):
            return "from "
        if word.startswith("ה"):
            return "the "
        return ""
    elif lang == "fr":
        if word.startswith("ב"):
            return "en "
        if word.startswith("ו"):
            return "et "
        if word.startswith("ל"):
            return "à "
        if word.startswith("מ"):
            return "dès "
        if word.startswith("ה"):
            return "la "
        return ""


title_translations = {
    # This section of translations is based on an image shared by Yair, original source unknown
    'רב"ט': 'Corporal',
    'סמל': 'Sergeant',
    'סמ"ר': 'Staff Sergeant',

    'רב סמל': 'Sergeant First Class',
    'רס"ל': 'Sergeant First Class',

    'רב סמל ראשון': 'Chief Sergeant First Class',
    'רס"ר': 'Chief Sergeant First Class',
    'רס"מ': 'Master Sergeant',
    'רס"ם': 'Master Sergeant',

    'רס"ב': 'First Sergeant',
    'רנ"מ': 'Sergeant Major',
    'רנ"ם': 'Sergeant Major',
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
    'רמטכ"ל': 'Commander in Chief',
    'מ"פ': 'Company Commander',
    'סמג"ד': 'Deputy Battalon Commander',
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

    # slightly related given the context in which we are unfortunately using these abbreviations
    if target_language_code == 'en':
        text = re.sub(r'\bהי"ד\b',   'HYD', text, re.U)
        
        text = re.sub(r'\b(ב)צו?הריים\b', lambda m: ("in " if m.group(1).startswith("ב") else '') + 'the afternoon', 
                    text, re.U)
        text = re.sub(r'\b(אחר )?ה?צו?הריים\b', 'the afternoon', text, re.U)

        text = re.sub(r'\bהלילה\b', 'last night', text, re.U)

        text = re.sub(r'\b([למהבו])?עוטף עזה\b', lambda m: tx_heb_prefix(m.group(1), "en") + 'the Gaza envelope', text, re.U)
        text = re.sub(r'\b([למהבו])?עוטף\b', lambda m: tx_heb_prefix(m.group(1), "en") + 'the Gaza envelope [?]', text, re.U)

    elif target_language_code == 'fr':
        text = re.sub(r'\bהלילה\b', 'la nuit dernière', text, re.U)

        text = re.sub(r'\b([למהבו])?עוטף עזה\b', lambda m: tx_heb_prefix(m.group(1), "fr") + 'La zone autour de Gaza', text, re.U)
        text = re.sub(r'\b([למהבו])?עוטף\b', lambda m: tx_heb_prefix(m.group(1), "fr") + 'La zone autour de Gaza [?]', text, re.U)

    return text


def post_translation_swaps(text, target_language_code):
    if target_language_code == 'en':
        text = re.sub('infrastructures', 'infrastructure', text)
        text = re.sub(r'\b[Aa]larm(s?)\b', lambda m: "siren" + ('s' if m.group(1).startswith("s") else ''), text)
        text = re.sub(r'\b([Aa])n siren', "\\1 siren", text)
    elif target_language_code == 'fr':
        text = re.sub(r'\b[Aa]larm(s?)\b', lambda m: "alert" + ('s' if m.group(1).startswith("s") else ''), text)

    return text