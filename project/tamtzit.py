from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
import re
import os
from flask import Blueprint, render_template, request
#from flask_login import login_required, current_user
from google.cloud import translate, datastore
from dataclasses import dataclass
from pyluach import dates
from markupsafe import Markup

PROJECT_ID = "tamtzit-hadashot"
PARENT = f"projects/{PROJECT_ID}"

sections = {"SOUTH":"Southern Front", 
            "NORTH":"Northern Front", 
            "YandS":"Yehuda and Shomron",
            "Civilian":"Civilian Front", 
            "PandP":"Policy, Law and Politics",
            "WorldEyes":"In the Eyes of the World", 
            "InIsrael":"Israel Local News",
            "Worldwide":"World News",
            "Economy":"Economy",
            "Sports":"Sports",
            "Weather":"Weather",
            "FinishWell":"On a Positive Note",
            "UNKNOWN":"UNKNOWN"
            }

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

    break_point = text.index("📌", text.index("📌"))
    first_section = text[0:break_point]
    second_section = text[break_point:]

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

def store_draft(heb_text):
    entity = datastore.Entity(key=datastore_client.key("draft"), exclude_from_indexes=["hebrew_text"])
    entity.update({"hebrew_text": heb_text})
    draft_timestamp = datetime.now(tz=ZoneInfo('Asia/Jerusalem'))
    entity.update({"timestamp": draft_timestamp})

    datastore_client.put(entity)
    return draft_timestamp

def fetch_drafts():
    query = datastore_client.query(kind="draft")
    query.order = ["-timestamp"]

    drafts = query.fetch()

    return drafts


@dataclass
class DateInfo():
    part_of_day: str
    day_of_week: str
    hebrew_dom: int
    hebrew_month: str
    hebrew_year: int
    secular_month: str
    secular_dom: int
    day_of_war: int

tamtzit = Blueprint('tamtzit', __name__)

@tamtzit.route('/')
def index():
    drafts = fetch_drafts()
    # for draft in drafts:
    #     print(f"draft: {draft}")
    #     ts = draft['timestamp']
    #     print(ts.strftime('%m%d%Y-%H%M%S'))        
    return render_template('input.html', drafts=drafts)


@tamtzit.route("/draft", methods=['GET'])
def continue_draft():
    draft_timestamp = request.args.get('ts')
    drafts = fetch_drafts()
    for draft in drafts:
        ts = draft['timestamp']
        if ts.strftime('%Y%m%d-%H%M%S') == draft_timestamp:
            heb_text = draft['hebrew_text']
            info = process_translation_request(heb_text)
            rendered = render_template('english.html', **info)
            return re.sub('\n{3,}', '\n\n', rendered)
        
    return "Draft not found, please start again."


@tamtzit.route("/deleteDraft", methods=['GET'])
def delete_draft():
    draft_timestamp = request.args.get('dt')
    drafts = fetch_drafts()
    for draft in drafts:
        ts = draft['timestamp']
        if ts.strftime('%Y%m%d-%H%M%S') == draft_timestamp:
            datastore_client.delete(draft.key)
            return "OK"
    return "Not found"
            

@tamtzit.route('/translate', methods=['POST'])
def process():
    heb_text = request.form.get('orig_text')
    if not heb_text:
        return "Input field was missing."
    
    # store the draft in DB so that someone else can continue the translation work
    draft_timestamp = store_draft(heb_text)

    info = process_translation_request(heb_text)
    rendered = render_template('english.html', **info, draft_timestamp=draft_timestamp.strftime('%Y%m%d-%H%M%S'))
    return re.sub('\n{3,}', '\n\n', rendered)

def debug(stuff):
    if os.getenv("FLASK_DEBUG") == "1":
        print("DEBUG: " + stuff)


def process_translation_request(heb_text):
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

    translated = translate_text(heb_text, 'en')
    debug(f"RAW TRANSLATION:--------\n{translated}")
    debug(f"--------------------------")

    heb_text = Markup(heb_text) #.replace("\n", "<br>"))
    translated_lines = translated.split("\n")

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
        if section is None and "edition" in line.lower() and '202' in line.lower():
            debug("skipping what looks like the intro edition line")
            continue
        if line.lower().startswith("📌 war of iron swords"):
            debug("skipping what looks like the intro pin line")
            continue
        if line.startswith("• "):
            debug("bullet line...")
            if "southern " in line.lower() and 'SOUTH' not in organized:
                debug("starting south section")
                section = organized['SOUTH']
            elif "northern " in line.lower() and 'NORTH' not in organized:
                debug("starting north section")
                section = organized['NORTH']
            elif "judea and samaria" in line.lower() and 'YandS' not in organized:
                debug("starting J&S section")
                section = organized['YandS']
            elif "policy" in line.lower() and "politics" in line.lower() and 'PandP' not in organized:
                debug("starting policy section")
                section = organized['PandP']
            elif "in the world" in line.lower() and "Worldwide" not in organized:
                debug("starting world section")
                section = organized["Worldwide"]
            elif section is not None:
                debug("inside a section, switching to arrows")
                section.append(Markup(line.replace("• ", "> ")))
        elif line.startswith("📌"):
            debug("pin line...")
            if "in israel" in line.lower():
                debug("starting inIsrael section")
                section = organized['InIsrael']
            elif "world" in line.lower():
                debug("staerting world section")
                section = organized["Worldwide"]
            elif "policy" in line.lower() and "politics" in line.lower():
                debug("starting policy section")
                section = organized['PandP']
            elif "weather" in line.lower():
                debug("Starting weather section")
                section = organized['Weather']
            elif "economy" in line.lower():
                debug("Starting economy section")
                section = organized["Economy"]
            elif "sport" in line.lower():
                debug("Starting sports section")
                section = organized["Sports"]
            elif "finish" in line.lower() or "good note" in line.lower() or "end well" in line.lower():
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
    oct6 = datetime(2023,10,6,tzinfo=ZoneInfo('Asia/Jerusalem'))
    heb_dt = dates.HebrewDate.from_pydate(dt)
    dt_edition = "Evening"
    if 4 <= dt.hour <= 12:
        dt_edition = "Morning"
    elif 12 < dt.hour < 18:
        dt_edition = "Afternoon"

    date_info = DateInfo(dt_edition, dt.strftime('%A'), heb_dt.day, heb_dt.month_name(), heb_dt.year, 
                         dt.strftime('%B'), dt.day, (dt - oct6).days)

    result = {'heb_text': heb_text, 'translated': translated, 'translated_lines': translated_lines, 
              'organized': organized, 'date_info': date_info, 'sections': sections}
    return result


if __name__ == '__main__':
    text = "האגף לפיקוח על קופות חולים ריכז עבור כולם מידע חיוני לימים אלו."

    print(f" {text} ".center(50, "-"))
    for target_language in ['en', 'ru', 'es', 'fr']:
        translation = translate_text(text, target_language)
        source_language = translation.detected_language_code
        translated_text = translation.translated_text
        print(f"{source_language} → {target_language} : {translated_text}")