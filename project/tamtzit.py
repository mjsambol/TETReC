from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
import re
from flask import Blueprint, render_template, request
#from flask_login import login_required, current_user
from google.cloud import translate
from dataclasses import dataclass
from pyluach import dates
from markupsafe import Markup

PROJECT_ID = "tamtzit-hadashot"
PARENT = f"projects/{PROJECT_ID}"

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
    client = translate.TranslationServiceClient()

    response = client.translate_text(
        parent=PARENT,
        contents=[text],
        source_language_code=source_language,  # optional, can't hurt
        target_language_code=target_language_code,
    )

    return response.translations[0].translated_text

# print_supported_languages('he')

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
    return render_template('input.html')


@tamtzit.route('/translate', methods=['POST'])
def process():
    heb_text = request.form.get('orig_text')
    if not heb_text:
        return "Input field was missing."
    
    heb_lines = heb_text.split("\n")
    # strip the first few lines if necessary, they're causing some problem...
    for i in range(5):
        if "תמצית החדשות" in heb_lines[i]:
            heb_lines.pop(i)
            break
    for i in range(5):
        if "מהדורת " in heb_lines[i]:
            heb_lines.pop(i)
            break

    heb_text_marked = "12345: ".join(heb_lines)
    translated = translate_text(heb_text_marked, 'en')
    # this is a weird bug...
    translated = translated.replace("12345 : ", "12345: ")
    translated_lines = translated.split('12345: ')
    translated = Markup(translated.replace('12345: ', '\n<br>'))
    heb_text = Markup(heb_text) #.replace("\n", "<br>"))

    section = None
    organized = defaultdict(list)
    for line in translated_lines:
        line = line.strip()
        line = line.replace("12345: ", '')
        if len(line) == 0:
            continue
        if "📻" in line:
            continue
        if "• • •" in line:
            if "NORTH" in organized or "SOUTH" in organized:
                # we've processed the main body and moved to a section at the bottom 
                # which should be ignored
                break
            else:
                section = organized['UNKNOWN']
                continue
        if section is None and "edition" in line.lower() and '202' in line.lower():
            continue
        if line.lower().startswith("📌 war of iron swords"):
            continue
        if line.startswith("• "):
            if "southern arena" in line.lower() or "arena southern" in line.lower():
                section = organized['SOUTH']
            elif "northern arena" in line.lower() or "arena northern" in line.lower():
                section = organized['NORTH']
            elif "judea and samaria" in line.lower():
                section = organized['YandS']
            elif "policy and politics" in line.lower():
                section = organized['PandP']
            elif "in the world" in line.lower():
                section = organized["Worldwide"]
            elif section is not None:
                section.append(Markup(line.replace("• ", "> ")))
        elif line.startswith("📌"):
            if line.lower().endswith("happening in israel:"):
                section = organized['InIsrael']
            elif "world" in line.lower():
                section = organized["Worldwide"]
            elif "policy and " in line.lower():
                section = organized['PandP']
            elif "weather" in line.lower():
                section = organized['Weather']
            elif "economy" in line.lower():
                section = organized["Economy"]
            elif "sport" in line.lower():
                section = organized["Sports"]
            elif "finish" in line.lower() or "good note" in line.lower() or "end well" in line.lower():
                section = organized['FinishWell']
            else:
                section = organized['UNKNOWN']
                section.append(Markup(line))    
        else:
            if section is None:
                section = organized['UNKNOWN']
            section.append(Markup(line))
#            section.append(Markup("<br><br>"))
   
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
    rendered = render_template('english.html', date_info=date_info, 
                           translated=translated, heb_len = len(heb_lines),
                           heb_text=heb_text, organized=organized, translated_lines=translated_lines)
    return re.sub('\n{3,}', '\n\n', rendered)


if __name__ == '__main__':
    text = "האגף לפיקוח על קופות חולים ריכז עבור כולם מידע חיוני לימים אלו."

    print(f" {text} ".center(50, "-"))
    for target_language in ['en', 'ru', 'es', 'fr']:
        translation = translate_text(text, target_language)
        source_language = translation.detected_language_code
        translated_text = translation.translated_text
        print(f"{source_language} → {target_language} : {translated_text}")