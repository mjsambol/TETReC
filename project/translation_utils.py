import json
import re
from textwrap import dedent
from google.cloud import translate, datastore  # prerequisite: pip install google-cloud-translate
from openai import OpenAI                      # prerequisite: pip install openai

from common import debug, DatastoreClientProxy

from language_mappings import supported_langs_mapping, translated_section_names

PROJECT_ID = "tamtzit-hadashot"
PARENT = f"projects/{PROJECT_ID}"
section_header_pat = re.compile(r"[📌>] \*?_?([^_:*]+):_?\*?")

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
    'טוראי': 'Private',
    'רב טוראי': 'Corporal',
    'רב"ט': 'Corporal',
    'סמל': 'Sergeant',
    'סמל ראשון': 'Staff Sergeant',
    'סמ"ר': 'Staff Sergeant',

    'רב סמל': 'Sergeant First Class',
    'רס"ל': 'Sergeant First Class',

    'רב סמל ראשון': 'Master Sergeant', # < switching based on other sources and Ilana's friend. Originally had: 'Chief Sergeant First Class',
    'רס"ר': 'Master Sergeant',       # < Originally had: 'Chief Sergeant First Class',
    'רב סמל מתקדם': 'Sergeant Major',
    'רס"מ': 'Sergeant Major',        # < Originally had: 'Master Sergeant',
    'רס"ם': 'Sergeant Major',        # < Originally had: 'Master Sergeant',

    'רב סמל בכיר': 'Warrant Officer',
    'רס"ב': 'Warrant Officer',
    'רנ"מ': 'Sergeant Major',        # "apparently doesn't exist anymore" per Ilana's friend & Wikipedia
    'רנ"ם': 'Sergeant Major',        # "apparently doesn't exist anymore" per Ilana's friend & Wikipedia
    'רב נגד': 'Chief Warrant Officer',
    'רנ"ג': 'Chief Warrant Officer',

    'סגן משנה': 'Second Lieutenant',
    'סג"מ': 'Second Lieutenant',
    'סג"ם': 'Second Lieutenant',
    'סגן': 'Lieutenant',
    'סרן': 'Captain',

    'רב סרן': 'Major',
    'רס"ן': 'Major',
    'רס"נ': 'Major',

    'סגן אלוף': 'Lieutenant Colonel',
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

    'מ"מ': 'Platoon Commander',
    'מ"פ': 'Company Commander',
    'סמ"פ': 'Deputy Company Commander',
    'מג"ד': 'Battalion Commander',
    'סמג"ד': 'Deputy Battalion Commander',
    'מח"ט': 'Brigade Commander',
    'סמח"ט': 'Deputy Brigade Commander',
    'מא"ז': 'District Commander',
    'מש"ט': 'Flight Commander',
    'מט"ק': 'Tank Commander',

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

        # text = re.sub(r'\bהלילה\b', 'last night', text, flags=re.U)  # removing, it's wrong half the time
        text = re.sub(r'\bיישוב\b', "community", text, flags=re.U)
        text = re.sub(r'\bיישובים\b', "communities", text, flags=re.U)

        text = re.sub(r'\b([למהבו]+)?עוטף עזה\b', lambda m: tx_heb_prefix(m.group(1), "en") + 'the Gaza envelope', text, flags=re.U)
        text = re.sub(r'\b([למהבו]+)?עוטף\b', lambda m: tx_heb_prefix(m.group(1), "en") + 'the Gaza envelope [?]', text, flags=re.U)

        text = re.sub(r'\bהסברה\b', 'hasbara (public diplomacy)', text, flags=re.U)
        text = re.sub(r'\b([למהבו]+)?חלל(י)?\b', lambda m: tx_heb_prefix(m.group(1), "en") + 'fallen', text, flags=re.U)
        text = re.sub(r'\b([למהבו]+)?כטמ"[מם]\b', lambda m: tx_heb_prefix(m.group(1), "en") + "UAV", text, flags=re.U)
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
        text = re.sub("West Bank", "Yehuda and Shomron", text, flags=re.IGNORECASE)
        text = re.sub("Beer Sheva", "Be'er Sheva", text, flags=re.IGNORECASE)
        text = re.sub("slightly injured", "lightly injured", text, flags=re.IGNORECASE)
        text = re.sub(r"ultra[ -]?orthodox", "Haredi", text, flags=re.IGNORECASE)
        text = re.sub(r"red alert (siren)?", "siren", text, flags=re.IGNORECASE)
        text = re.sub(r"Ben Gabir", "Ben Gvir", text)
        text = re.sub("spokesman", "spokesperson", text, flags=re.IGNORECASE)
        text = re.sub("militant", "terrorist", text, flags=re.IGNORECASE)
        text = re.sub("settlement", "community", text, flags=re.IGNORECASE)

    elif target_language_code == 'fr':
        text = re.sub(r'\balarm(s?)\b', lambda m: "alert" + ('s' if m.group(1).startswith("s") else ''), text, flags=re.IGNORECASE)

    text = re.sub(r'\bGalant\b', 'Gallant', text)
    
    return text


def translate_text(text: str, target_language_code: str, source_language='he', engine="Google",
                   transaction_context: dict = {}) -> str:
    if engine == "Google":
        return google_translate(text, target_language_code, source_language)
    else:
        return openai_translate(text, target_language_code, source_language, custom_dirs="", transaction_context=transaction_context)

openai_force_translations = {
    "en": {
        'אגורה': 'agora',
        'אגורות': 'agorot',
        'אזעקה': 'siren',
        'אזעקות': 'sirens',
        'אמל"ח': 'weapons',
        'אצבע הגליל': 'the Galilee Panhandle',
        'הותר לפרסום': 'released for publication',
        'הי"ד': 'HYD',
        'הסברה': 'hasbara (public diplomacy)',
        'חטוף': 'hostage',
        'חטופים': 'hostages',
        'חטיבת האש': 'artillery brigade',
        'חלל': 'fallen',
        'יהודה ושומרון': 'Yehuda and Shomron',
        'יישוב': 'community',
        'יישובים': 'communities',
        'כטב"ם': 'UAV',
        'כטמ"ם': 'UAV',
        'לוט"ר': 'LOTAR (counter-terrorism special forces)',
        'מחבל': 'terrorist',
        'מחבלים': 'terrorists',
        'מרגש': 'moving',
        'עוטף עזה': 'the Gaza envelope',
        'שר הביטחון כ"ץ': 'Defense Minister Katz',
        'ניצנים': 'Nitzanim',
        'חרדי': 'Haredi',
        'חרדים': 'Haredim',
        'איו"ש': 'Yehuda and Shomron'
    },
    "fr": {
        'אזעקות': 'sirènes'
    }
}

openai_fix_translations = {
    "en": {
        'fighter': 'soldier',
        'infrastructures': 'infrastructure',
        'Judea': 'Yehuda',  # per Gabriela they sometimes show individually
        'Samaria': 'Shomron',
        'spokesman': 'spokesperson',
        'slightly injured': 'lightly injured',
        'militant': 'terrorist',
        'militants': 'terrorists',
        'ultra-orthodox': 'Haredi',
        'West Bank': 'Yehuda and Shomron',
        'settlement': 'community',
        'settlements': 'communities'
    }, "fr": {}
}

def openai_translate(text: str, target_language_code: str, source_language: str = "he", custom_dirs: str = "",
                     transaction_context: dict = {}) -> str:
        debug(f"translate_text: using OpenAI as engine... ")  # Hebrew is ======\n{text}\n======")
        # debug("Forcing these terms: \n " +
        #       json.dumps(openai_force_translations[target_language_code] | title_translations[target_language_code],
        #                                             ensure_ascii=False, indent=4))
        target_language_name = supported_langs_mapping[target_language_code]
        try:
            openai_client = OpenAI()
        except Exception as err:
            print("OpenAI init caused error")
            print(err)

        if target_language_code == 'en':
            system_prompt = f"""
            You are a professional translator specializing in Hebrew-to-English news updates. 
            Your translation **must strictly follow** the provided dictionaries.

            ### **Rules:**
            1. **Strictly adhere** to the provided terminology dictionary - this is MANDATORY
            2. **Word replacements are MANDATORY** - replace all occurences of words in the second dictionary with their provided values.
            3. **DO NOT use synonyms** for dictionary terms - use exact matches, though words should be conjugated as needed to fit the sentence.
            4. **Maintain the itemization** (hyphens, bullet points, or other separators).
            3. **Produce natural-sounding English** while staying accurate and respecting the provided dictionaries.

            ### Terminology Dictionary:
            {json.dumps(openai_force_translations[target_language_code].update(title_translations[target_language_code]), ensure_ascii=False, indent=2)}

            You MUST also apply the supplied python dictionary's translations to alternate forms of the keys, like those with prefixes. 
            For example, since the dictionary indicates that 'מחבל' MUST be translated as 'terrorist', translate 'המחבל' as 'the terrorist'.

            ### Word Replacements:
            {json.dumps(openai_fix_translations['en'], ensure_ascii=False, indent=2)}

            The word replacement dictionary MUST be applied even to alternate forms of the keys, e.g. those which have been conjugated 
            differently or have prefix or suffix modifiers.

            ### **Incorrect Translations (Avoid These):**
            ❌ "מחבל" → "militant" (Incorrect)  
            ✅ "מחבל" → "terrorist" (Correct)  

            ❌ "יהודה ושומרון" → "Judea and Samaria" (Incorrect)  
            ✅ "יהודה ושומרון" → "Yehuda and Shomron" (Correct)  

            Translate the following Hebrew text while strictly following all these rules.
            """            

            messages = [
                {"role": "system", "content": system_prompt}
            ]
        elif target_language_code == 'fr':
            messages = [
                {"role": "system",
                 "content": dedent('''
                Je suis un journaliste israélien sioniste, et de ce fait ne parle pas de "Judée et Samarie" mais de "la région de Yehouda et Shomron", pas de colonies mais de localités, pas de colons mais d'habitants. 

                Grades de Tsahal:
                אל"מ = Colonel
                אלוף = Général
                אלוף משנה = Colonel
                טוראי = Soldat
                סא"ל = Lieutenant-colonel
                סג"מ = Sous-lieutenant
                סגן = Lieutenant
                סגן-אלוף = Lieutenant-colonel
                סגן-משנה = Sous-lieutenant
                סמ"ר = Caporal-chef
                סמל = Caporal
                סמל ראשון = Caporal-chef
                סרן = Capitaine
                רא"ל = Chef d'état-major
                רב טוראי = Première classe
                רב סרן = Commandant
                רב-אלוף = Chef d'état-major
                רב-נגד = Major
                רב-סמל = Sergent
                רב-סמל בכיר = Adjudant-chef
                רב-סמל מתקדם = Adjudant
                רב-סמל ראשון = Sergent-chef
                רב"ט = Première classe
                רנ"ג = Major
                רס"ב = Adjudant-chef
                רס"ל = Sergent
                רס"מ = Adjudant
                רס"ן = Commandant
                רס"ר = Sergent-chef
                תא"ל = Général de brigade
                תת-אלוף = Général de brigade

                Jargon militaire:
                אוגדה = Division
                פלוגה = Compagnie
                גדוד = Bataillon
                חטיבה = Brigade
                פיקוד העורף = Pikoud Haoref. La première occurrence, ajouter aussi (Commandement du Front intérieur), mais pas les suivantes. Par exemple: Aujourd'hui, une vérification des sirènes du Pikoud Haoref (Commandement du Front intérieur) est prévue à Ein Gedi à 10h05. En cas d'alerte réelle, une deuxième sirène retentira, accompagnée d'une notification via l'application du Pikoud Haoref et d'autres moyens.

                מג"ב = Magav. La première occurrence ajouter (police des frontières), par exemple “quatre combattants de Magav (police des frontières) ont été blessés.”
                ג'יהאד אסלאמי (גא"פ) = Jihad islamique

                Géographie:
                בבנימין = dans la région de Binyamin
                ביהודה ושומרון = dans la région de Yehouda et Shomron
                אצבע הגליל = Doigt de Galilée
                יישוב = localité
                יישובים = localités
                כותל המערבי = Kotel
                עכו = Akko
                גליל העליון = Haute Galilée
                גליל התחתון = Basse Galilée
                ברובע הדאחיה בביירות = dans le secteur de Dahieh à Beyrouth
                עוטף עזה = “enveloppe de Gaza" ou “la région autour de Gaza”. Par exemple “suite au tir de roquettes vers l'enveloppe de Gaza hier”
                טולכרם = Tulkarem
                קבר יוסף = tombeau de Yossef

                Autres:
                בית משפט מחוזי = Cour d'Appel
                הותר לפרסום = Il a été autorisé à la publication
                יהי זכרו ברוך = Que sa mémoire soit bénie
                יהי זכרם ברוך = Que leur mémoire soit bénie
                "כטב""ם" = drone
                "כטמ""ם" = drone de combat
                צהריים = après-midi
                חשוון = Heshvan
                פיקוד העורף = Le Pikoud Haoref (Commandement du Front Intérieur)
                Lorsqu’une personne apparaît pour la 1e fois dans le texte, la nommer par son prénom et nom. Les apparitions suivantes peuvent se suffire du nom de famille.
                חסידי ברסלב = 'hassidim de Breslev (Bratslav)
                כ-10 = une dizaine
                כ-20 = une vingtaine
                אוטובוס = bus
                ''')
            }]

        if len(custom_dirs) > 0:
            messages.extend([{"role": "user", "content": custom_dirs}])

        if target_language_code == 'en':
            messages.extend([{"role": "user", "content": text}])
        elif target_language_code == 'fr':
            messages.extend([{"role": "user", "content": f"Traduire en français le texte hébreu en tenant compte de toutes ces données\n" + text}])

        debug(f"openai_translate(): sending the following directions to openAI: {messages}")

        # low temperature for more deterministic, rule-following results
        completion = openai_client.chat.completions.create(model="gpt-4o", temperature=0.2, messages=messages)
            # {"role": "system", "content": "Do not abbreviate anything which is not abbreviated in the Hebrew."""},
            # {"role": "system", "content": "Text which indicates when the news item happened, such as 'last night' or 'this morning', should be minimized in the translation."},

        result = completion.choices[0].message.content
        result = post_translation_swaps(result, target_language_code)
        return result


def google_translate(text: str, target_language_code: str, source_language: str) -> str:
    text = pre_translation_swaps(text, target_language_code)

    break_point = text.find("📌", text.find("📌") + 1)
    if break_point == -1:
        break_point = len(text)
    first_section = text[0:break_point]
    second_section = text[break_point:]

    debug(f"translate_text(Google): Hebrew is -----\n{text}\n-----")
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


def strip_header_and_footer(heb_text, target_language_code):
    debug(f"RAW HEBREW:--------\n{heb_text}")
    debug(f"--------------------------")

    debug(f"translated section names is {translated_section_names[target_language_code]}")

    # strip off the header and footer, there is no point translating them and they are complicated to ignore later
    stripped_heb_text = ""
    found_a_pin = False
    in_footer = False

    for line in heb_text.split("\n"):
        if not found_a_pin:
            if "📌" in line:
                found_a_pin = True
            else:
                continue   # strip this line, it's header
        else:
            if not in_footer and ("• • •" in line or "•   •   •" in line):
                in_footer = True

            if in_footer:
                continue   # strip this line, it's footer

        # while we're going through the text, replace Hebrew section headings with those of the target language
        # it's too messy to translate and then try to figure it out
        header_match = section_header_pat.match(line)
        if header_match:
            debug(f"replacing header\n'{line}'\ngroup1 is '{header_match.group(1)}'")
            if header_match.group(1) not in translated_section_names[target_language_code]:
                debug(f"We have no mapping for that, so leaving it alone.")
            else:
                line = line.replace(header_match.group(1), translated_section_names[target_language_code][header_match.group(1)])
            debug(f"now it's {line}")

        stripped_heb_text = stripped_heb_text + line + "\n"

    heb_text = stripped_heb_text
    debug(f"STRIPPED OF HEADER & FOOTER:--------\n{heb_text}")
    debug(f"--------------------------")
    return heb_text
