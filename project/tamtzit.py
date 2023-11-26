from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import locale
from collections import defaultdict
import re
import os
import json
from flask import Blueprint, render_template, request, redirect, make_response
#from flask_login import login_required, current_user
from google.cloud import translate, datastore
from google.cloud.datastore.key import Key
from dataclasses import dataclass
from pyluach import dates
from markupsafe import Markup
from .translation_utils import *

PROJECT_ID = "tamtzit-hadashot"
PARENT = f"projects/{PROJECT_ID}"
DRAFT_TTL = 60 * 60 * 24
supported_langs_mapping = {}
supported_langs_mapping['English'] = 'en' 
supported_langs_mapping['en'] = 'English' 
supported_langs_mapping['Francais'] = 'fr'
supported_langs_mapping['fr'] = 'Francais'
locales = {}
# Note that at least locally, getting locale support requires some prep-work:
# sudo apt-get install language-pack-he-base  (or fr instead of he, etc)
# sudo dpkg-reconfigure locales
# they seemed to thankfully be supported out of the box in appengine
locales['en'] = "en_US.UTF-8"
locales['fr'] = "fr_FR.UTF-8"
locales['he'] = 'he_IL.UTF-8'
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
sections['fr'] = {"SOUTH":Markup("Au sud"), 
            "NORTH":Markup("Au nord"), 
            "YandS":"Yehuda et Shomron",
            "Civilian":"Civilian Front", 
            "InIsrael":Markup("Ce qu'il se passe en Israël"),
            "PandP":"Politique",
            "WorldEyes":"Autour du monde", 
            "Worldwide":"Autour du monde",
            "Economy":"Economie",
            "Sports":"Sport",
            "Weather":"Météo",
            "FinishWell":"Et on termine sur une bonne note 🎶",
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
editions = {}
editions['en'] = ['Morning', 'Afternoon', 'Evening']
editions['fr'] = ['Matin', "l'après-midi", 'soir']
editions['he'] = ['בוקר', 'צוהריים', 'ערב']


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

    text = pre_translation_swaps(text)

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

    result = post_translation_swaps(result)
    # print(f"DEBUG: translation result has {len(response.translations)} translations")
    # if len(response.translations) > 1:
    #     print("DEBUG: the second one is:")
    #     print(response.translations[1].translated_text)
    return result

class DatastoreClientProxy:
    def __init__(self) -> None:
        self.client = datastore.Client()
        self.debug_mode = os.getenv("FLASK_DEBUG") == "1"

    def key(self, name):
        return self.client.key(("debug_" if self.debug_mode else "") + name)
    
    def put(self, entity):
        return self.client.put(entity)
    
    def get(self, key):
        return self.client.get(key)
    
    def delete(self, key):
        return self.client.delete(key)
    
    def query(self, kind):
        return self.client.query(kind =("debug_" if self.debug_mode else "") + kind)
        

datastore_client = DatastoreClientProxy()


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

def create_draft(heb_text, translation_text='', translation_lang='en'):
    '''Create a new entry in the Datastore, save the original text and, optionally, the translation, and return the new key and timestamp'''

    key=datastore_client.key("draft")
    draft_timestamp = datetime.now(tz=ZoneInfo('Asia/Jerusalem'))
    entity = datastore.Entity(key=key, exclude_from_indexes=["hebrew_text","translation_text"])
    entity.update({"hebrew_text": heb_text, "translation_text": translation_text, "translation_lang": translation_lang, 
                   "timestamp": draft_timestamp, "last_edit": draft_timestamp, 
                   "is_finished": False, "ok_to_translate": False}) 
    datastore_client.put(entity)
    entity = datastore_client.get(entity.key)
    return entity.key

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
            # also delete all the history of edits to that draft
            query2 = datastore_client.query(kind="draft_backup")
            query2.add_filter("draft_id", "=", draft.key.id)
            draft_backups = query2.fetch()
            for dbkup in draft_backups:
                debug("found a backup, deleting it")
                datastore_client.delete(dbkup.key)
            
    return query.fetch(), drafts_local_timestamp

def create_draft_history(draft):
    key = datastore_client.key("draft_backup")
    entity = datastore.Entity(key=key, exclude_from_indexes=["hebrew_text","translation_text"])
    entity.update({"draft_id":draft.key.id, "hebrew_text": draft["hebrew_text"], "translation_text": draft["translation_text"], 
                   "translation_lang": draft["translation_lang"], "draft_timestamp": draft["timestamp"], "last_edit": draft["last_edit"], 
                   "is_finished": draft["is_finished"], "ok_to_translate": draft["ok_to_translate"], "backup_timestamp": datetime.now(tz=ZoneInfo('Asia/Jerusalem'))})
    datastore_client.put(entity)
    entity = datastore_client.get(entity.key)
    return entity.key
    
def store_draft_backup(draft):
    debug("checking whether to save a draft backup...")
    prev_backup_time = 0
    query2 = datastore_client.query(kind="draft_backup")
    query2.order = ["-backup_timestamp"]
    #query2.add_filter("draft_id", "=", draft.key.id)
    draft_backups = query2.fetch()
    for dbkup in draft_backups:
        if dbkup["draft_id"] != draft.key.id:
            debug("Found a backup but not for this draft")
            continue
        else:
            debug(f"found a relevant backup which was created on {dbkup['backup_timestamp']}")
            prev_backup_time = dbkup['backup_timestamp']
            break
    if prev_backup_time == 0:
        debug("No prev backup found")
    else:
        debug(f'draft last edit is {draft["last_edit"]} so the backup is {draft["last_edit"] - prev_backup_time} which is {(draft["last_edit"] - prev_backup_time).seconds} seconds old')
    if prev_backup_time == 0 or (draft["last_edit"] - prev_backup_time).seconds > 90:
        debug("creating a draft backup")
        create_draft_history(draft)


def update_translation_draft(draft_key, translated_text, is_finished=False):   # can't change the original Hebrew
    draft = datastore_client.get(draft_key)
    prev_last_edit = draft["last_edit"]
    draft.update({"translation_text": translated_text})
    draft.update({"is_finished": is_finished})
    edit_timestamp = datetime.now(tz=ZoneInfo('Asia/Jerusalem'))
    draft.update({"last_edit": edit_timestamp}) 
    datastore_client.put(draft)

    # also store history in case of dramatic failure
    store_draft_backup(draft)


def update_hebrew_draft(draft_key, hebrew_text, is_finished=False, ok_to_translate=False):
    draft = datastore_client.get(draft_key)
    prev_last_edit = draft["last_edit"]
    draft.update({"hebrew_text": hebrew_text})
    draft.update({"is_finished": is_finished})
    if ok_to_translate:  # we don't want to go back once it's set to true
        draft.update({"ok_to_translate": True})
    edit_timestamp = datetime.now(tz=ZoneInfo('Asia/Jerusalem'))
    draft.update({"last_edit": edit_timestamp}) 
    draft.update({"translation_lang": '--'})
    datastore_client.put(draft)

    # also store history in case of dramatic failure
    store_draft_backup(draft)


def get_latest_published(lang_code):
    drafts = fetch_drafts()[0]
    debug(f"get_latest_published({lang_code}): ...")
    for draft in drafts:
        debug(f"Checking: {draft['translation_lang']}")
        if lang_code == 'he' and 'is_finished' in draft and draft['is_finished'] == True:
            return draft
        if draft['translation_lang'] == lang_code and 'is_finished' in draft and draft['is_finished'] == True:
            return draft
    return None


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
    hebrew_dom_he: str
    hebrew_month_he: str
    hebrew_year_he: str

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
def route_create():
    return render_template(detect_mobile(request, 'index'))

@tamtzit.route('/debug')
def device_info():
    heb_font_size = "30px";
    site_prefs = request.cookies.get('tamtzit_prefs')
    if site_prefs:
        spd = json.loads(site_prefs)
        fsz = spd["heb-font-size"]
        if fsz:
            heb_font_size = fsz
            print("/debug: overriding font size from cookie: " + heb_font_size)

    return render_template('fonts.html', heb_font_size=heb_font_size);

@tamtzit.route("/setSettings", methods=['POST'])
def route_set_settings():
    font_preference = request.form.get("font-size")
    debug("Changing settings: font size is now " + font_preference)
    response = make_response(redirect("/heb"))
    prefs = {"heb-font-size": font_preference}
    response.set_cookie('tamtzit_prefs', json.dumps(prefs), expires=datetime.now() + timedelta(days=100))
    return response

def refresh_cookies(request, response):
    site_prefs = request.cookies.get('tamtzit_prefs')
    if site_prefs:
        response.set_cookie('tamtzit_prefs', site_prefs, expires=datetime.now() + timedelta(days=100))


@tamtzit.route('/heb')
def route_hebrew_template():
    next_page = detect_mobile(request, "hebrew")
    print("next page is " + next_page)
    # is there a Hebrew draft from the last 3 hours [not a criteria: that's not yet "Done"]
    drafts, local_tses = fetch_drafts()
    print("Drafts is " + ("" if drafts is None else "not ") + "null")

    dt = datetime.now(ZoneInfo('Asia/Jerusalem'))
    for draft in drafts:
        print("checking a draft...")
        if draft['translation_lang'] != '--': 
            continue

        debug(f"/heb: should we show draft w/ lang={draft['translation_lang']}, is_finished={'is_finished' in draft and draft['is_finished']}, ok_to_translate={'ok_to_translate' in draft and draft['ok_to_translate']}")
        draft_last_mod = draft['last_edit']
        debug(f"/heb: draft's last edit is {draft_last_mod}, it's now {dt}, delta is {dt - draft_last_mod}")
        if (dt - draft_last_mod).seconds > (60 * 90):  # 1.5 hours per Yair's choice 
            break

        heb_font_size = "30px";
        site_prefs = request.cookies.get('tamtzit_prefs')
        if site_prefs:
            spd = json.loads(site_prefs)
            fsz = spd["heb-font-size"]
            if fsz:
                heb_font_size = fsz

        response = make_response(render_template(next_page, heb_text=Markup(draft['hebrew_text']), draft_key=draft.key.to_legacy_urlsafe().decode("utf8"), 
                                ok_to_translate=("ok_to_translate" in draft and draft["ok_to_translate"]),
                                is_finished=('is_finished' in draft and draft['is_finished']), heb_font_size=heb_font_size))
        refresh_cookies(request, response)
        return response
            
    # if no current draft was found, create a new one so that we have a key to work with and save to while editing
    key = create_draft('')
    debug(f'Creating a new Hebrew draft with key {key.to_legacy_urlsafe().decode("utf8")}')
#    return redirect(f'/heb_draft?key={key.to_legacy_urlsafe().decode("utf8")}')
    date_info = make_date_info(dt, 'he')
    return render_template(next_page, date_info=date_info, draft_key=key.to_legacy_urlsafe().decode("utf8"), ok_to_translate=False, is_finished=False)

# @tamtzit.route('/heb_draft')
# def route_hebrew_draft(): 
#     draft_key = Key.from_legacy_urlsafe(request.args.get('key'))
#     draft = datastore_client.get(draft_key)
#     heb_text = draft['hebrew_text']
#     ok_to_translate = "ok_to_translate" in draft and draft["ok_to_translate"]
#     if len(heb_text) == 0:
#         dt = datetime.now(ZoneInfo('Asia/Jerusalem'))
#         date_info = make_date_info(dt, 'he')
#         return render_template('hebrew.html', date_info=date_info, draft_key=request.args.get('key'), ok_to_translate=ok_to_translate)
#     else:
#         return render_template('hebrew.html', heb_text=heb_text, draft_key=request.args.get('key'), ok_to_translate=ok_to_translate)

@tamtzit.route("/start_translation")
def route_start_translation():
    drafts, local_tses = fetch_drafts()
    dt = datetime.now(ZoneInfo('Asia/Jerusalem'))
    latest_heb = ''
    for draft in drafts:
        # if we can't find an ok-to-translate Hebrew draft from the last 4 hours, let the user know it's not ready...
        draft_last_mod = draft['last_edit']
        if (dt - draft_last_mod).seconds > (60 * 60 * 4):
            return render_template("error.html", msg="There is no current edition ready for translation.")

        if draft['translation_lang'] == '--' and 'ok_to_translate' in draft and draft['ok_to_translate'] == True:
            # this is the most recent Hebrew text
            latest_heb = draft['hebrew_text']
            break

    if len(latest_heb) == 0:
        return render_template("error.html", msg="There is no current edition ready for translation.")
    
    # we need to restart the iterator
    drafts, local_tses = fetch_drafts() 
    next_page = detect_mobile(request, "input")
    return render_template(next_page, heb_text=latest_heb, drafts=drafts, local_timestamps=local_tses, supported_langs=supported_langs_mapping)

'''
/translate and /draft are very similar:
   /translate creates a new entry based on the submission of the form at /start_translate  (POST)
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

            return render_template(next_page, heb_text=heb_text, translated=translated, draft_timestamp=draft_timestamp, 
                                   lang=draft['translation_lang'],
                                   draft_key=key.to_legacy_urlsafe().decode('utf8'), is_finished=('is_finished' in draft and draft['is_finished']))

    return "Draft not found, please start again."
            
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
    
    info = process_translation_request(heb_text, target_language_code)
    draft_timestamp=datetime.now(tz=ZoneInfo('Asia/Jerusalem')).strftime('%Y%m%d-%H%M%S')

    translated = render_template(target_language.lower() + '.html', **info, draft_timestamp=draft_timestamp)
    translated = re.sub('\n{3,}', '\n\n', translated)  # this is necessary because the template can generate large gaps due to unused sections

    # store the draft in DB so that someone else can continue the translation work
    key = create_draft(heb_text, translation_text=translated, translation_lang=target_language_code)
    return render_template(next_page, heb_text=heb_text, translated=translated, lang=target_language_code,
                           draft_timestamp=draft_timestamp, draft_key=key.to_legacy_urlsafe().decode('utf8'))


@tamtzit.route("/saveDraft", methods=['POST'])
def save_draft():
    debug(f"saveDraft: draft_key is {request.form.get('draft_key')}")
    draft_key = Key.from_legacy_urlsafe(request.form.get('draft_key'))
    if draft_key is None:
        debug("ERROR: /saveDraft got None draft_key!")
        return
    finished = request.form.get('is_finished') and request.form.get('is_finished').lower() == 'true'
    send_to_translators = request.form.get('to_translators') and request.form.get('to_translators').lower() == 'true'
    # we're saving _either_ the Hebrew or the translation, not both at once
    translated_text=request.form.get('translation')
    source_text = request.form.get('source_text')
    if translated_text and len(translated_text) > 0:
        update_translation_draft(draft_key, translated_text, is_finished=finished)
    else:
        update_hebrew_draft(draft_key, source_text, is_finished=finished, ok_to_translate=send_to_translators)
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
            if kw['intro_pin'] in line.lower():
                debug("skipping what looks like the intro pin line")
                continue            
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
            elif (kw["finish"] in line.lower() or "good note" in line.lower() or "end well" in line.lower() 
                  or "bien finir" in line.lower() or "finit bien" in line.lower()):
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
    if 0 <= dt.hour <= 12:
        dt_edition = editions[lang][0]
    elif 12 < dt.hour < 18:
        dt_edition = editions[lang][1]

    locale.setlocale(locale.LC_TIME, locales[lang])
    date_info = DateInfo(dt_edition, dt.strftime('%A'), heb_dt.day, heb_dt.month_name(), heb_dt.year, 
                         dt.strftime('%B'), dt.day, dt.year, (dt - oct6).days, heb_dt.hebrew_day(), heb_dt.month_name(True), heb_dt.hebrew_year())
                         
    return date_info


if __name__ == '__main__':
    text = "האגף לפיקוח על קופות חולים ריכז עבור כולם מידע חיוני לימים אלו."

    print(f" {text} ".center(50, "-"))
    for target_language in ['en', 'ru', 'es', 'fr']:
        translation = translate_text(text, target_language)
        source_language = translation.detected_language_code
        translated_text = translation.translated_text
        print(f"{source_language} → {target_language} : {translated_text}")
