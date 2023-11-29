from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import locale
from collections import defaultdict
import re
import json
from uuid import uuid4
import functools
import cachetools.func
from flask import Blueprint, render_template, request, redirect, make_response
#from flask_login import login_required, current_user
from google.cloud import translate, datastore
from google.cloud.datastore.key import Key
from dataclasses import dataclass
from pyluach import dates
from markupsafe import Markup
import requests
from requests.auth import HTTPBasicAuth
from .translation_utils import *
from .cookies import *
from .common import *
from .language_mappings import *

PROJECT_ID = "tamtzit-hadashot"
PARENT = f"projects/{PROJECT_ID}"
mailjet_basic_auth = HTTPBasicAuth('dbe7d877e71f69f13e19d2af6671f6cb', 'a7e171ca7aeb40920bc93f69d79459d6')   
DRAFT_TTL = 60 * 60 * 24

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


datastore_client = DatastoreClientProxy.get_instance()


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

def create_draft(heb_text, user_info, translation_text='', translation_lang='en', heb_draft_id=None):
    '''Create a new entry in the Datastore, save the original text and, optionally, the translation, and return the new key and timestamp'''

    if len(heb_text) > 0 and heb_draft_id is None:
        debug("create_draft() ERROR: received heb_text but no heb_draft_id")
        raise ValueError("No draft ID though text is present")

    key=datastore_client.key("draft")
    draft_timestamp = datetime.now(tz=ZoneInfo('Asia/Jerusalem'))
    entity = datastore.Entity(key=key, exclude_from_indexes=["hebrew_text","translation_text"])
    entity.update({"hebrew_text": heb_text, "heb_draft_id": heb_draft_id, 
                   "translation_text": translation_text, "translation_lang": translation_lang, 
                   "timestamp": draft_timestamp, "last_edit": draft_timestamp, 
                   "is_finished": False, "ok_to_translate": False, "created_by": user_info["user_id"]}) 
    datastore_client.put(entity)
    entity = datastore_client.get(entity.key)
    return entity.key

def fetch_drafts(query_order="-timestamp"):
    query = datastore_client.query(kind="draft")
    query.order = [query_order]

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
                   "is_finished": draft["is_finished"], "ok_to_translate": draft["ok_to_translate"], "created_by": draft["created_by"],
                   "backup_timestamp": datetime.now(tz=ZoneInfo('Asia/Jerusalem'))})
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


def create_invitation(user):
    key=datastore_client.key("invitation")
    entity = datastore.Entity(key=key)
    entity.update({"creation_timestamp": datetime.now(tz=ZoneInfo('Asia/Jerusalem')),
                   "user_id": user.key.id,
                   "link_id": str(uuid4())}) 
    datastore_client.put(entity)
    entity = datastore_client.get(entity.key)
    return entity

def consume_invitation(invitation):
    debug(f"Seeking DB invitation [{invitation}]")
    query = datastore_client.query(kind="invitation")
    query.add_filter("link_id", "=", invitation)
    found_invs = query.fetch()
    now = datetime.now(tz=ZoneInfo('Asia/Jerusalem'))
    for inv in found_invs:
        debug(f"found {inv['link_id']}")
        if inv['link_id'] == invitation:
            if 'used_at_timestamp' in inv and inv['used_at_timestamp']:
                debug("It's already been used.")
                return None
            if (now - inv['creation_timestamp']).days > 0 or (now - inv['creation_timestamp']).seconds > (60 * 60):
                debug("It's expired, deleting it.")
                datastore_client.delete(inv.key)
                return None
            inv.update({"used_at_timestamp": now})
            datastore_client.put(inv)
            user_details = get_user(user_id=inv["user_id"])
            return user_details
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
    return next_pg

@cachetools.func.ttl_cache(ttl=600)
def validate_weekly_birthcert(bcert):
    query = datastore_client.query(kind="crypto_noise")
    daily_noise_entries = query.fetch()
    for daily_noise_entry in daily_noise_entries:
        daily_noise = daily_noise_entry["daily_noise"]
        if daily_noise in bcert:
            return True
    return False

@cachetools.func.ttl_cache(ttl=600)
def get_user(email=None, user_id=None):
    debug("getting users from DB...")

    if email:
        query = datastore_client.query(kind="user")
        debug(f"Based on email {email}")
        query.add_filter("email", "=", email)
        users = query.fetch()
        for user in users:
            return user
    elif user_id:
        debug(f"Based on user ID {user_id}")
        user = datastore_client.get(datastore_client.key("user", int(user_id)))
        debug(f"Got back {user}")
        return user

    return None

def send_invitation(user_details, invitation):
    email_message = (f"To access the Tamtzit HaChadashot Admin Application, click the link below:\n\n "
                    f"{invitation}")

    data={"Messages":[{"From":{"Email":"moshe.sambol@gmail.com", "Name":"Moshe Sambol"},
                        "To":[{"Email":user_details["email"], "Name":user_details["name"]}],
                        "Subject":"Tamtzit HaChadashot Admin App Access",
                        "TextPart":email_message}]}
    
    mailjet_resp = requests.post("https://api.mailjet.com/v3.1/send", auth=mailjet_basic_auth, 
                                headers={"Content-Type":"application/json"}, data=json.dumps(data))

    debug(f'Sending training launch notification email - status: {mailjet_resp.json()["Messages"][0]["Status"]}')     


def require_login(func):
    @functools.wraps(func)    # this is necessary so that Flask routing will work!!
    def authentication_check_wrapper(*args, **kwargs):
        debug("Checking authentication status...")
        # check if there is a cookie with a valid session cert (session cookie - short expiration, but saves checking the DB frequently)
        # - that is, today's date + some noise encrypted with our key
        # if there is, let the method which called us continue. 
        # if not, redirect to /auth while passing the URL the user was requesting
        session_cookie = request.cookies.get(Cookies.ONE_DAY_SESSION)
        if not session_cookie:
            debug("No session cookie found")
            return redirect("/auth?requested=" + request.full_path)

        today_noise = get_today_noise()
        today_session = get_cookie_dict(request, Cookies.ONE_DAY_SESSION)
        if Cookies.COOKIE_CERT in today_session and today_noise in today_session[Cookies.COOKIE_CERT]:
            debug("Decrypted cookie is valid!")
            return func(*args, **kwargs)
        
        debug("daily cookie found but expired / invalid")
        return redirect("/auth?requested=" + request.full_path)

    return authentication_check_wrapper

def require_role(role_name):
    def decorator_require_role(func):
        @functools.wraps(func)    # this is necessary so that Flask routing will work!!
        def role_check_wrapper(*args, **kwargs):
            debug("Checking role requirements...")
            db_user_info = get_user(user_id=user_data_from_req(request)[Cookies.COOKIE_USER_ID]) 
            roles = db_user_info['role']
            debug(f"user has roles {roles}")
            if role_name in roles:
                return func(*args, **kwargs)
            else:
                return render_template("error.html", msg="You don't have access to this section.",
                                    heb_msg="חלק הזה של האתר מיועד למשתמשים אחרים")
        
        return role_check_wrapper
    return decorator_require_role

#        response.set_cookie('tamtzit_prefs', site_prefs, expires=datetime.now() + timedelta(days=100))


    # at /auth, check if there is a 7-day cookie with a signed user ID. Look up the user ID in our DB, if found,
    # extend the 7 days, then create and set a daily session cookie, then redirect back to the requested URL. This is a week-long cookie and saves re-auth
    #
    # if at /auth no username found, prompt for email address, look it up in DB, create an invitation link for that user
    # save it in the DB and send the link, then redir to page "check your email" or "email not found". 
    # Together with the invitation link save the URL user wanted to go to.
    #
    # when user clicks invitation link look it up in DB, if found create a 7-day cookie and set it, redirect to requested URL from invitation table 
    # with invitation link save created and used dates, don't let it be reused

@tamtzit.route("/auth", methods=['GET','POST'])
def route_authenticate():
    debug("/auth called with method " + request.method)

    if request.method == "GET":
        weekly_cookie = request.cookies.get(Cookies.ONE_WEEK_SESSION)
        if not weekly_cookie:
            debug("No weekly cookie found")
            return render_template("login.html")
            
        # how to create and manage the weekly cookie?
        # one option: just keep a week's worth of entries of the daily noise, check each one of them for inclusion in the weekly cookie
        # and delete any old ones as they're found
        # other option is yet another entity, but it doesn't seem any better, still have to keep it updated...
        debug("checking validity of weekly cookie which is present")
        weekly_session = get_cookie_dict(request, Cookies.ONE_WEEK_SESSION)
        if Cookies.COOKIE_CERT not in weekly_session:
            debug("Weekly cookie is not valid")
            return render_template("login.html")
        bcert = weekly_session[Cookies.COOKIE_CERT]        
        if validate_weekly_birthcert(bcert):  
            debug("weekly cookie is valid, refreshing it, setting daily cookie and redirecting to " + request.args.get('requested'))    
            weekly_session[Cookies.COOKIE_CERT] = get_today_noise()
            response = redirect(request.args.get('requested'))
            response.set_cookie(Cookies.ONE_DAY_SESSION, make_cookie_from_dict(weekly_session), expires=datetime.now() + timedelta(days=1))
            response.set_cookie(Cookies.ONE_WEEK_SESSION, make_cookie_from_dict(weekly_session), expires=datetime.now() + timedelta(days=7))
            return response
        else:
            debug("Weekly cookie is not valid")
            return render_template("login.html")
    else: 
        # handle login form submission    
        email = request.form.get("email")
        debug("login attempt from user " + email)
        user_details = get_user(email)
        if not user_details:
            return render_template("error.html", dont_show_home_link=True, msg="The email address you provided is unknown. Contact the admin.",
                                   heb_msg="כתובת מייל זו לא מוכרת. צור קשר עם משה.")
    
        debug("Confirmed - it's a known user. Preparing an invitation link...")
        # create an invitation link and store it in the DB
        invitation = create_invitation(user_details)
        debug("new invitation: " + invitation["link_id"])
        # send the invitation via email to the user
        send_invitation(user_details, request.url_root + "use_invitation?inv=" + invitation["link_id"])

        return render_template("error.html", dont_show_home_link=True, msg="Check your email for an authentication link.",
                               heb_msg="לינק לכניסה נשלח למייל שלך")


@tamtzit.route('/')
@require_login
def route_create():    
    return render_template(detect_mobile(request, 'index'))

@tamtzit.route('/debug')
def device_info():
    heb_font_size = "30px"
    site_prefs = request.cookies.get('tamtzit_prefs')
    if site_prefs:
        spd = json.loads(site_prefs)
        fsz = spd["heb-font-size"]
        if fsz:
            heb_font_size = fsz
            print("/debug: overriding font size from cookie: " + heb_font_size)

    return render_template('fonts.html', heb_font_size=heb_font_size)

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


@tamtzit.route("/status")
def route_get_status_json():
    status_per_lang = {}
    jlm = ZoneInfo("Asia/Jerusalem")
    now = datetime.now(tz=jlm)
    drafts = fetch_drafts(query_order="-last_edit")[0]
    for draft in drafts:
        if draft['translation_lang'] in status_per_lang:
            continue
        status_per_lang[draft['translation_lang']] = {
            "lang": expand_lang_code(draft["translation_lang"], to_lang="H"),
            "who": get_user(user_id=draft["created_by"])['name_hebrew'],
            "started": draft['timestamp'].astimezone(jlm).strftime('%H:%M'),
            "last_edit": draft['last_edit'].astimezone(jlm).strftime('%H:%M'),
            "elapsed_since_last_edit": (now - draft['last_edit']).seconds,
            "ok_to_translate": draft['ok_to_translate'],
            "done": draft['is_finished']
        }
    response = {
        'as_of': now.strftime("%H:%M"),
        'by_lang': status_per_lang
    }
    return json.dumps(response)


@tamtzit.route("/use_invitation")
def route_use_invitation_link():
    invitation = request.args.get("inv")
    user_details = consume_invitation(invitation)
    if user_details:
        response = make_response(redirect("/"))
        
        debug(f"/use_invitation: valid invitation for user {user_details['email']}")

        response.set_cookie(Cookies.ONE_DAY_SESSION, make_daily_cookie(user_details), expires=datetime.now() + timedelta(days=1))

        response.set_cookie(Cookies.ONE_WEEK_SESSION, make_weekly_cookie(user_details), expires=datetime.now() + timedelta(days=7))

        return response
    else:
        return render_template("error.html", dont_show_home_link=True, msg="Invalid authentication link. Please contact an admin.",
                               heb_msg="הלינק לא תקין, צור קשר עם משה")


@tamtzit.route('/heb')
@require_login
@require_role("Hebrew")
def route_hebrew_template():
    next_page = detect_mobile(request, "hebrew")
    cookie_user_info = user_data_from_req(request)

    # is there a Hebrew draft from the last 3 hours [not a criteria: that's not yet "Done"]
    drafts, local_tses = fetch_drafts()
    debug("Drafts is " + ("" if drafts is None else "not ") + "null")

    dt = datetime.now(ZoneInfo('Asia/Jerusalem'))
    for draft in drafts:
        if draft['translation_lang'] != '--': 
            continue

        debug(f"/heb: should we show draft w/ lang={draft['translation_lang']}, is_finished={'is_finished' in draft and draft['is_finished']}, ok_to_translate={'ok_to_translate' in draft and draft['ok_to_translate']}")
        draft_last_mod = draft['last_edit']
        debug(f"/heb: draft's last edit is {draft_last_mod}, it's now {dt}, delta is {dt - draft_last_mod}")
        if (dt - draft_last_mod).seconds > (60 * 90):  # 1.5 hours per Yair's choice 
            break

        draft_creator_user_info = get_user(user_id=draft["created_by"])

        response = make_response(render_template(next_page, heb_text=Markup(draft['hebrew_text']), draft_key=draft.key.to_legacy_urlsafe().decode("utf8"), 
                                ok_to_translate=("ok_to_translate" in draft and draft["ok_to_translate"]),
                                is_finished=('is_finished' in draft and draft['is_finished']), 
                                heb_font_size=get_heb_font_sz_pref(request), user_name=draft_creator_user_info["name_hebrew"]))
        refresh_cookies(request, response)
        return response
            
    # if no current draft was found, create a new one so that we have a key to work with and save to while editing
    key = create_draft('', cookie_user_info, translation_lang='--')
    draft_creator_user_info = get_user(user_id=cookie_user_info[Cookies.COOKIE_USER_ID])

    debug(f'Creating a new Hebrew draft with key {key.to_legacy_urlsafe().decode("utf8")}')
    date_info = make_date_info(dt, 'he')
    response = make_response(render_template(next_page, date_info=date_info, draft_key=key.to_legacy_urlsafe().decode("utf8"), ok_to_translate=False, is_finished=False,
                                             heb_font_size=get_heb_font_sz_pref(request), user_name=draft_creator_user_info["name_hebrew"]))
    refresh_cookies(request, response)
    return response


def get_heb_font_sz_pref(request):
    heb_font_size = "30px"
    site_prefs = request.cookies.get('tamtzit_prefs')
    if site_prefs:
        spd = json.loads(site_prefs)
        fsz = spd["heb-font-size"]
        if fsz:
            heb_font_size = fsz
    return heb_font_size


@tamtzit.route("/start_translation")
@require_login
@require_role("translator")
def route_start_translation():
    drafts, local_tses = fetch_drafts()
    dt = datetime.now(ZoneInfo('Asia/Jerusalem'))
    latest_heb = ''
    for draft in drafts:
        # if we can't find an ok-to-translate Hebrew draft from the last 3 hours, let the user know it's not ready...
        draft_last_mod = draft['last_edit']
        if (dt - draft_last_mod).seconds > (60 * 60 * 3):
            return render_template("error.html", msg="There is no current edition ready for translation.")

        if draft['translation_lang'] == '--' and 'ok_to_translate' in draft and draft['ok_to_translate'] == True:
            # this is the most recent Hebrew text
            latest_heb = draft['hebrew_text']
            latest_creator = draft['created_by']
            draft_id = draft.key.id
            break

    if len(latest_heb) == 0:
        return render_template("error.html", msg="There is no current edition ready for translation.")
    
    # we need to restart the iterator
    drafts, local_tses = fetch_drafts() 
    next_page = detect_mobile(request, "input")
    return render_template(next_page, heb_text=latest_heb, creator_id=latest_creator, draft_id=draft_id, 
                           drafts=drafts, local_timestamps=local_tses, supported_langs=supported_langs_mapping)

'''
/translate and /draft are very similar:
   /translate creates a new entry based on the submission of the form at /start_translate  (POST)
   /draft     edits an existing entry based on a link on the main page      (GET)
'''
@tamtzit.route("/draft", methods=['GET'])
@require_login
@require_role("translator")
def continue_draft():
    next_page = detect_mobile(request, "editing")
    user_info = get_user(user_id=user_data_from_req(request)[Cookies.COOKIE_USER_ID])

    draft_timestamp = request.args.get('ts')
    drafts, _ = fetch_drafts()
    for draft in drafts:
        ts = draft['timestamp']
        if ts.strftime('%Y%m%d-%H%M%S') == draft_timestamp:
            heb_text = draft['hebrew_text']
            translated = draft['translation_text']
            names = {
                "heb_author_in_heb": draft["name_hebrew"],
                "heb_author_in_en": draft["name"],
                "translator_in_heb":user_info["name_hebrew"],
                "translator_in_en": user_info["name"]
            }
            key = draft.key

            return render_template(next_page, heb_text=heb_text, translated=translated, draft_timestamp=draft_timestamp, 
                                   lang=draft['translation_lang'], **names,
                                   draft_key=key.to_legacy_urlsafe().decode('utf8'), is_finished=('is_finished' in draft and draft['is_finished']))

    return "Draft not found, please start again."
            
'''
/translate and /draft are very similar:
   /translate creates a new entry based on the submission of the form at /  (POST)
   /draft     edits an existing entry based on a link on the main page      (GET)
'''
@tamtzit.route('/translate', methods=['POST'])
@require_login
@require_role("translator")
def process():
    heb_text = request.form.get('orig_text')
    if not heb_text:
        return "Input field was missing."

    target_language_code = request.form.get('target-lang')
    target_language = supported_langs_mapping[target_language_code]
    next_page = detect_mobile(request, "editing")
    basic_user_info = user_data_from_req(request)
    user_info = get_user(user_id=basic_user_info["user_id"])
    draft_creator_user_info = get_user(user_id=request.form.get('heb_author_id'))
    names = {
        "heb_author_in_heb": draft_creator_user_info["name_hebrew"],
        "heb_author_in_en": draft_creator_user_info["name"],
        "translator_in_heb":user_info["name_hebrew"],
        "translator_in_en": user_info["name"]
    }
    
    info = process_translation_request(heb_text, target_language_code)
    draft_timestamp=datetime.now(tz=ZoneInfo('Asia/Jerusalem')).strftime('%Y%m%d-%H%M%S')

    translated = render_template(target_language.lower() + '.html', **info, draft_timestamp=draft_timestamp, **names)
    translated = re.sub('\n{3,}', '\n\n', translated)  # this is necessary because the template can generate large gaps due to unused sections

    # store the draft in DB so that someone else can continue the translation work
    key = create_draft(heb_text, basic_user_info, translation_text=translated, translation_lang=target_language_code, heb_draft_id=request.form.get('heb_draft_id'))
    return render_template(next_page, heb_text=heb_text, translated=translated, lang=target_language_code,
                           draft_timestamp=draft_timestamp, draft_key=key.to_legacy_urlsafe().decode('utf8'))


@tamtzit.route("/saveDraft", methods=['POST'])
@require_login
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

    if target_language_code == "YY":
        translated = heb_text
    else:
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
        if "• • •" in line or "•   •   •" in line:
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
