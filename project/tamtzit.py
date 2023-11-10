from datetime import datetime
from zoneinfo import ZoneInfo
import locale
from collections import defaultdict
import re
import os
from flask import Blueprint, render_template, request
#from flask_login import login_required, current_user
from google.cloud import translate, datastore
from google.cloud.datastore.key import Key
from dataclasses import dataclass
from pyluach import dates
from markupsafe import Markup

PROJECT_ID = "tamtzit-hadashot"
PARENT = f"projects/{PROJECT_ID}"
DRAFT_TTL = 60 * 60 * 12
supported_langs_mapping = {}
supported_langs_mapping['English'] = 'en' 
supported_langs_mapping['en'] = 'English' 
supported_langs_mapping['Francais'] = 'fr'
supported_langs_mapping['fr'] = 'Francais'
locales = {}
locales['en'] = "en_US.UTF-8"
locales['fr'] = "fr_FR.UTF-8"
sections = {}
sections['en'] = {"SOUTH":"Southern Front", 
            "NORTH":"Northern Front", 
            "YandS":"Yehuda and Shomron",
            "Civilian":"Civilian Front", 
            "InIsrael":"Israel Local News",
            "PandP":"Policy, Law and Politics",
            "WorldEyes":"In the Eyes of the World", 
            "Worldwide":"World News",
            "Economy":"Economy",
            "Sports":"Sports",
            "Weather":"Weather",
            "FinishWell":"On a Positive Note",
            "UNKNOWN":"UNKNOWN"
            }
sections['fr'] = {"SOUTH":Markup("L'arène sud"), 
            "NORTH":Markup("L'arène nord"), 
            "YandS":"Judée et Samarie",
            "Civilian":"Civilian Front", 
            "InIsrael":"De ce qui se passe dans le pays",
            "PandP":"Politique, droit et politique",
            "WorldEyes":"In the Eyes of the World", 
            "Worldwide":"Autour du monde",
            "Economy":"Economie",
            "Sports":"Sport",
            "Weather":"Météo",
            "FinishWell":"Et bien finir",
            "UNKNOWN":"UNKNOWN"
            }
keywords = {}
keywords['en'] = {
    "edition": "edition",
    "intro_pin": "📌 war of iron swords",
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
    "edition": "Édition",
    "intro_pin": "📌 guerre des épées de fer",
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
    "finish": "terminera"
}
editions = {}
editions['en'] = ['Morning', 'Afternoon', 'Evening']
editions['fr'] = ['Matin', 'après-midi', 'soir']


client = translate.TranslationServiceClient()

# def print_supported_languages(display_language_code: str):
#     client = translate.TranslationServiceClient()

#     response = client.get_supported_languages(
#         parent=PARENT,
#         display_language_code=display_language_code,
#     )

#     languages = response.languages
#     print(f" Languages: {len(languages)} ".center(60, "-"))
#     for language in languages:
#         language_code = language.language_code
#         display_name = language.display_name
#         print(f"{language_code:10}{display_name}")

def translate_text(text: str, target_language_code: str, source_language='he') -> translate.Translation:
    # for reasons I don't understand, we regularly lose the last paragraph of text
    # perhaps it's just too long. Let's try breaking it up.

    break_point = text.index("📌", text.index("📌") + 1)
    first_section = text[0:break_point]
    second_section = text[break_point:]

    debug(f"translate_text(): Hebrew is -----\n{text}\n-----")
    debug(f"first section length: {len(first_section)}")
    debug(f"second section length: {len(second_section)}")
    client = translate.TranslationServiceClient()

    result = ""
    for section in [first_section, second_section]:
        response = client.translate_text(
            parent=PARENT,
            contents=[section],
            source_language_code=source_language,  # optional, can't hurt
            target_language_code=target_language_code,
            mime_type='text/plain' # HTML is assumed!
        )
        result += response.translations[0].translated_text
    # print(f"DEBUG: translation result has {len(response.translations)} translations")
    # if len(response.translations) > 1:
    #     print("DEBUG: the second one is:")
    #     print(response.translations[1].translated_text)
    return result


datastore_client = datastore.Client()

############################################
# Notes on use of GCP DataStore
#   
# Documentation is at https://cloud.google.com/datastore/docs/samples/datastore-add-entity
#
# We're storing *entities* of *kind* Drafts
# each entity has *properties*
# Entity creation returns a key that can later be used to retrieve the entity
#
# key = client.key("Drafts", "aDraftID") -- second field is OPTIONAL, if omitted an ID will be generated
# draft = datastore.Entity(key, other_params_if_needed)
# draft.update( {dict of fields} )
#
# later to fetch the entity:
# draft = key.get()   or draft = client.get(key)
#
# The key has methods:
#   * get() which returns the full entity data object
#   * kind() 
#   * id()
#   * urlsafe() - encoded unique string that can be used in URLs
#                 then later: key = Key(urlsafe=url_string); key.get()
#
# Any property change requires sending *all* properties to be persisted
#
# s = key.get(); s.field=val; s.put();
#
# to delete, use the key:
# key.delete()

def store_draft(heb_text, translation_text='', translation_lang='en'):
    '''Create a new entry in the Datastore, save the original text and, optionally, the translation, and return the new key and timestamp'''

    key=datastore_client.key("draft")
    draft_timestamp = datetime.now(tz=ZoneInfo('Asia/Jerusalem'))
    entity = datastore.Entity(key=key, exclude_from_indexes=["hebrew_text","translation_text"])
    entity.update({"hebrew_text": heb_text, "timestamp": draft_timestamp, "translation_text": translation_text, "translation_lang": translation_lang}) 
    datastore_client.put(entity)
    entity = datastore_client.get(entity.key)
    return (entity.key, entity['timestamp'])

def fetch_drafts():
    query = datastore_client.query(kind="draft")
    query.order = ["-timestamp"]

    drafts = query.fetch()

    now = datetime.now(tz=ZoneInfo('UTC'))
    drafts_local_timestamp = {}
    jlm = ZoneInfo("Asia/Jerusalem")

    for draft in drafts:
        ts = draft['timestamp']
        drafts_local_timestamp[ts] = ts.astimezone(jlm)
        if (now - ts).days > 0 or (now - ts).seconds > DRAFT_TTL:
            datastore_client.delete(draft.key)
            
    return query.fetch(), drafts_local_timestamp

def update_draft(draft_key, translated_text):   # can't change the original Hebrew
    draft = datastore_client.get(draft_key)
    draft.update({"translation_text": translated_text})
    datastore_client.put(draft)


@dataclass
class DateInfo():
    part_of_day: str
    day_of_week: str
    hebrew_dom: int
    hebrew_month: str
    hebrew_year: int
    secular_month: str
    secular_dom: int
    secular_year: int
    day_of_war: int

tamtzit = Blueprint('tamtzit', __name__)

def detect_mobile(request, page_name):
    ua = request.user_agent
    ua = str(ua).lower()
    if "mobile" in ua or "android" in ua or "iphone" in ua:
        next_pg = page_name + "_mobile.html"
    else:
        next_pg = page_name + ".html"
    debug(ua)  
    return next_pg


@tamtzit.route('/')
def index():
    drafts, local_tses = fetch_drafts()
    next_page = detect_mobile(request, "input")
    return render_template(next_page, drafts=drafts, local_timestamps=local_tses, supported_langs=supported_langs_mapping)


'''
/translate and /draft are very similar:
   /translate creates a new entry based on the submission of the form at /  (POST)
   /draft     edits an existing entry based on a link on the main page      (GET)
'''
@tamtzit.route("/draft", methods=['GET'])
def continue_draft():
    next_page = detect_mobile(request, "editing")

    draft_timestamp = request.args.get('ts')
    drafts, _ = fetch_drafts()
    for draft in drafts:
        ts = draft['timestamp']
        if ts.strftime('%Y%m%d-%H%M%S') == draft_timestamp:
            heb_text = draft['hebrew_text']
            translated = draft['translation_text']
            key = draft.key

            return render_template(next_page, heb_text=heb_text, translated=translated, draft_timestamp=draft_timestamp, draft_key=key.to_legacy_urlsafe().decode('utf8'))

    return "Draft not found, please start again."

# removing this - since a draft can at any time be edited again, it gets messy... let's just delete them automatically after time
#
# @tamtzit.route("/deleteDraft", methods=['GET'])
# def delete_draft():
#     draft_timestamp = request.args.get('dt')
#     drafts = fetch_drafts()
#     for draft in drafts:
#         ts = draft['timestamp']
#         debug(f"deleteDraft asked to delete {draft_timestamp}, is that the same as {ts.strftime('%Y%m%d-%H%M%S')}?")
#         if ts.strftime('%Y%m%d-%H%M%S') == draft_timestamp:
#             debug("yes, same, deleting")
#             datastore_client.delete(draft.key)
#             return "OK"
#         else:
#             debug("Not the same.")
#     return "Not found"
            
'''
/translate and /draft are very similar:
   /translate creates a new entry based on the submission of the form at /  (POST)
   /draft     edits an existing entry based on a link on the main page      (GET)
'''
@tamtzit.route('/translate', methods=['POST'])
def process():
    heb_text = request.form.get('orig_text')
    if not heb_text:
        return "Input field was missing."

    target_language_code = request.form.get('target-lang')
    target_language = supported_langs_mapping[target_language_code]
    next_page = detect_mobile(request, "editing")
    
    # store the draft in DB so that someone else can continue the translation work
    key, d_timestamp = store_draft(heb_text, translation_lang=target_language_code)

    info = process_translation_request(heb_text, target_language_code)
    draft_timestamp=d_timestamp.strftime('%Y%m%d-%H%M%S')

    translated = render_template(target_language.lower() + '.html', **info, draft_timestamp=draft_timestamp)
    translated = re.sub('\n{3,}', '\n\n', translated)  # this is necessary because the template can generate large gaps due to unused sections

    # now store the translated part as well
    update_draft(key, translated_text=translated)
    rendered = render_template(next_page, heb_text=heb_text, translated=translated, draft_timestamp=draft_timestamp, draft_key=key.to_legacy_urlsafe().decode('utf8'))

    return rendered


@tamtzit.route("/saveDraft", methods=['POST'])
def save_draft():
    draft_key = Key.from_legacy_urlsafe(request.form.get('draft_key'))
    if draft_key is None:
        debug("ERROR: /saveDraft got None draft_key!")
        return
    update_draft(draft_key, translated_text=request.form.get('translation'))
    return "OK"


def debug(stuff):
    if os.getenv("FLASK_DEBUG") == "1":
        print("DEBUG: " + stuff)


def process_translation_request(heb_text, target_language_code):
    # heb_lines = heb_text.split("\n")

    debug(f"RAW HEBREW:--------\n{heb_text}")
    debug(f"--------------------------")
        # print(f"Split hebrew has {len(heb_lines)} lines")

    # strip the first few lines if necessary, they're causing some problem...
    # for i in range(5):
    #     if "תמצית החדשות" in heb_lines[i]:
    #         print("popping a tamtzit" + heb_lines[i])
    #         heb_lines.pop(i)
    #         break
    # for i in range(5):
    #     if "מהדורת " in heb_lines[i]:
    #         print("popping a mehadura: " + heb_lines[i])
    #         heb_lines.pop(i)
    #         break

    translated = translate_text(heb_text, target_language_code)
    debug(f"RAW TRANSLATION:--------\n{translated}")
    debug(f"--------------------------")

    heb_text = Markup(heb_text) #.replace("\n", "<br>"))
    translated_lines = translated.split("\n")

    kw = keywords[target_language_code]
    section = None
    organized = defaultdict(list)
    for line in translated_lines:
        line = line.strip()
        debug(f"{len(line)}: {line}")
        if len(line) == 0:
            debug("skipping a blank line")
            continue
        if "📻" in line:
            debug("skipping radio icon line")
            continue
        if "• • •" in line:
            debug("Found three dot line")
            if "NORTH" in organized or "SOUTH" in organized:
                debug("post three dots, skipping")
                # we've processed the main body and moved to a section at the bottom 
                # which should be ignored
                break
            else:
                debug("post three dots, switching to 'unknown'")
                section = organized['UNKNOWN']
                continue
        if section is None and kw["edition"] in line.lower() and '202' in line.lower():
            debug("skipping what looks like the intro edition line")
            continue
        if line.lower().startswith(kw['intro_pin']):
            debug("skipping what looks like the intro pin line")
            continue
        if line.startswith("> "):
            debug("bullet line...")
            if kw["southern"] in line.lower() and 'SOUTH' not in organized:
                debug("starting south section")
                section = organized['SOUTH']
            elif kw["northern"] in line.lower() and 'NORTH' not in organized:
                debug("starting north section")
                section = organized['NORTH']
            elif kw["jands"] in line.lower() and 'YandS' not in organized:
                debug("starting J&S section")
                section = organized['YandS']
            elif kw["policy"] in line.lower() and "politics" in line.lower() and 'PandP' not in organized:
                debug("starting policy section")
                section = organized['PandP']
            elif kw["in the world"] in line.lower() and "Worldwide" not in organized:
                debug("starting world section")
                section = organized["Worldwide"]
            elif section is not None:
                debug("inside a section")
                section.append(Markup(line))
        elif line.startswith("📌"):
            debug("pin line...")
            if kw["in israel"] in line.lower():
                debug("starting inIsrael section")
                section = organized['InIsrael']
            elif kw["world"] in line.lower():
                debug("staerting world section")
                section = organized["Worldwide"]
            elif kw["policy"] in line.lower() and kw["politics"] in line.lower():
                debug("starting policy section")
                section = organized['PandP']
            elif kw["weather"] in line.lower():
                debug("Starting weather section")
                section = organized['Weather']
            elif kw["economy"] in line.lower():
                debug("Starting economy section")
                section = organized["Economy"]
            elif kw["sport"] in line.lower():
                debug("Starting sports section")
                section = organized["Sports"]
            elif kw["finish"] in line.lower() or "good note" in line.lower() or "end well" in line.lower():
                debug("Starting good news section")
                section = organized['FinishWell']
            else:
                section = organized['UNKNOWN']
                debug("Adding to unknown: " + line)
                section.append(Markup(line))    
        else:
            debug("regular text line")
            if section is None:
                section = organized['UNKNOWN']
                debug("Adding to unknown (b): " + line)

            section.append(Markup(line))
            if section == organized['UNKNOWN']:
                debug("Adding to unknown (c):" + line)
   
    dt = datetime.now(ZoneInfo('Asia/Jerusalem'))
    date_info = make_date_info(dt, target_language_code)

    # for the first pass the translation isn't sent as a block of text but rather 
    # as small blocks broken down by section. Later after the first human review pass we'll save it
    # as a contiguous block in the DB and going forward work from that
    result = {'heb_text': heb_text, 'date_info': date_info, 'organized': organized, 'sections': sections[target_language_code]}
    return result


def make_date_info(dt, lang):
    oct6 = datetime(2023,10,6,tzinfo=ZoneInfo('Asia/Jerusalem'))
    heb_dt = dates.HebrewDate.from_pydate(dt)
    dt_edition = editions[lang][2]
    if 4 <= dt.hour <= 12:
        dt_edition = editions[lang][0]
    elif 12 < dt.hour < 18:
        dt_edition = editions[lang][1]

    locale.setlocale(locale.LC_TIME, locales[lang])
    date_info = DateInfo(dt_edition, dt.strftime('%A'), heb_dt.day, heb_dt.month_name(), heb_dt.year, 
                         dt.strftime('%B'), dt.day, dt.year, (dt - oct6).days)
                         
    return date_info


if __name__ == '__main__':
    text = "האגף לפיקוח על קופות חולים ריכז עבור כולם מידע חיוני לימים אלו."

    print(f" {text} ".center(50, "-"))
    for target_language in ['en', 'ru', 'es', 'fr']:
        translation = translate_text(text, target_language)
        source_language = translation.detected_language_code
        translated_text = translation.translated_text
        print(f"{source_language} → {target_language} : {translated_text}")
