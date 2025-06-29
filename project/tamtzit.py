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

import os
import cachetools.func
from collections import defaultdict
from datetime import datetime, timedelta
import json
import re
from textwrap import dedent
from zoneinfo import ZoneInfo

from babel.dates import format_date, format_datetime
from bs4 import BeautifulSoup, Tag
from flask import Blueprint, render_template, request, redirect, make_response, url_for
from google.cloud import translate, datastore  # noqa -- Intellij is incorrectly flagging the import
from google.cloud.datastore.key import Key  # noqa -- Intellij is incorrectly flagging the import
from google.cloud.datastore.query import PropertyFilter
from markupsafe import Markup
import requests

from auth_utils import confirm_user_has_role, consume_invitation, create_invitation, get_user, require_login
from auth_utils import require_role, get_user_availability, update_user_availability
from auth_utils import send_invitation, validate_weekly_birthcert, zero_user
from common import _set_debug, ARCHIVE_BASE, debug, DatastoreClientProxy, expand_lang_code, JERUSALEM_TZ
from cookies import Cookies, get_cookie_dict, get_today_noise, make_cookie_from_dict, make_daily_cookie
from cookies import user_data_from_req
from draft_utils import create_draft, DraftStates, fetch_drafts, get_latest_day_worth_of_editions, make_date_info
from draft_utils import make_new_archive_entry, upload_to_cloud_storage, update_hebrew_draft, update_translation_draft
from diff_draft_versions import get_translated_additions_since_ok_to_tx
from language_mappings import editions, keywords, sections, supported_langs_mapping, translated_section_names
from template_text_chunks import make_header, make_footer
from translation_utils import translate_text, strip_header_and_footer
from weekly_schedule import Schedule

translation_client = translate.TranslationServiceClient()

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


tamtzit = Blueprint('tamtzit', __name__)


def detect_mobile(param_request, page_name):
    ua = param_request.user_agent
    ua = str(ua).lower()
    if "mobile" in ua or "android" in ua or "iphone" in ua:
        next_pg = page_name + "_mobile.html"
    else:
        next_pg = page_name + ".html"
    return next_pg


# at /auth, check if there is a 7-day cookie with a signed user ID. Look up the user ID in our DB, if found,
# extend the 7 days, then create and set a daily session cookie, then redirect back to the requested URL.
# This is a week-long cookie and saves re-auth
#
# if at /auth no username found, prompt for email address, look it up in DB, create an invitation link for that user
# save it in the DB and send the link, then redir to page "check your email" or "email not found".
# Together with the invitation link save the URL user wanted to go to.
#
# when user clicks invitation link look it up in DB, if found create a 7-day cookie and set it,
# redirect to requested URL from invitation table with invitation link save created and used dates,
# don't let it be reused
@tamtzit.route("/auth", methods=['GET', 'POST'])
def route_authenticate():
    debug("/auth called with method " + request.method)

    if request.method == "GET":
        weekly_cookie = request.cookies.get(Cookies.ONE_WEEK_SESSION)
        if not weekly_cookie:
            debug("No weekly cookie found")
            return render_template("login.html")

        # how to create and manage the weekly cookie?
        # one option: just keep a week's worth of entries of the daily noise, check each one of them for inclusion
        # in the weekly cookie and delete any old ones as they're found
        # other option is yet another entity, but it doesn't seem any better, still have to keep it updated...
        debug("checking validity of weekly cookie which is present")
        weekly_session = get_cookie_dict(request, Cookies.ONE_WEEK_SESSION)
        if Cookies.COOKIE_CERT not in weekly_session:
            debug("Weekly cookie is not valid")
            return render_template("login.html")
        bcert = weekly_session[Cookies.COOKIE_CERT]
        if validate_weekly_birthcert(bcert):
            debug("weekly cookie is valid, refreshing it, setting daily cookie and redirecting to " +
                  request.args.get('requested'))
            weekly_session[Cookies.COOKIE_CERT] = get_today_noise()
            response = redirect(request.args.get('requested'))
            new_cookie = make_cookie_from_dict(weekly_session)
            response.set_cookie(Cookies.ONE_DAY_SESSION, new_cookie, expires=datetime.now() + timedelta(days=1))
            response.set_cookie(Cookies.ONE_WEEK_SESSION, new_cookie, expires=datetime.now() + timedelta(days=7))
            # response.set_cookie("tz_autha", new_cookie, max_age=60*60*24, domain='.' + request.host,
            # samesite="Lax", secure=True)
            # response.set_cookie("tz_authb", new_cookie, max_age=60*60*24*7, domain='.' + request.host,
            # samesite="Lax", secure=True)
            return response
        else:
            debug("Weekly cookie is not valid")
            return render_template("login.html")
    else:
        # handle login form submission    
        email = request.form.get("email")
        debug("login attempt from user " + email)
        user_details = get_user(email.lower())
        if not user_details:
            return render_template("error.html", dont_show_home_link=True,
                                   msg="The email address you provided is unknown. Contact the admin.",
                                   heb_msg="כתובת מייל זו לא מוכרת. צור קשר עם משה.")

        debug("Confirmed - it's a known user. Preparing an invitation link...")
        # create an invitation link and store it in the DB
        invitation = create_invitation(user_details)
        debug("new invitation: " + invitation["link_id"])
        # send the invitation via email to the user
        send_invitation(user_details, request.url_root + "use_invitation?inv=" + invitation["link_id"])

        return render_template("error.html", dont_show_home_link=True,
                               msg="Check your email for an authentication link.",
                               heb_msg="לינק לכניסה נשלח למייל שלך")


@tamtzit.route('/')
@require_login
def route_home_page():
    debug("top-level: do we know this user?")
    db_user_info = get_user(user_id=user_data_from_req(request)[Cookies.COOKIE_USER_ID])
    debug(f"user is {db_user_info}")
    role = db_user_info['role']

    daily_summary_in_progress = check_if_daily_summary_in_progress('H1')
    next_translators = get_next_translators()

    if request.method == "GET":
        return render_template(detect_mobile(request, 'index'), user_role=role,
                               daily_summary_in_progress=(daily_summary_in_progress is not None),
                               next_translators=Markup(json.dumps(next_translators)))
    elif request.method == "HEAD":
        debug("top-level: responding to head request with empty ...")
        return ''
    else:
        debug(f"top-level got unexpected request type {request.method}")
        return "UH oh"


def get_font_sz_prefs(param_request):
    heb_font_size = "30"
    en_font_size = "18"
    site_prefs = param_request.cookies.get('tamtzit_prefs')
    if site_prefs:
        spd = json.loads(site_prefs)
        if "heb-font-size" in spd:
            heb_font_size = spd["heb-font-size"]
            debug("/debug: overriding Hebrew font size from cookie: " + heb_font_size)
        if "en-font-size" in spd:
            en_font_size = spd["en-font-size"]
            debug("/debug: overriding English font size from cookie: " + en_font_size)
    return {"he": heb_font_size, "en": en_font_size}


@tamtzit.route('/debug')
def device_info():
    fsz_prefs = get_font_sz_prefs(request)
    return render_template('fonts.html', heb_font_size=fsz_prefs['he'], en_font_size=fsz_prefs['en'])


@tamtzit.route("/setSettings", methods=['POST'])
def route_set_settings():
    he_font_preference = request.form.get("he-font-size")
    en_font_preference = request.form.get("en-font-size")
    debug(f"Changing settings: Hebrew font size is now {he_font_preference}, English is {en_font_preference}")
    response = make_response(redirect("/"))
    prefs = {"heb-font-size": he_font_preference, "en-font-size": en_font_preference}
    response.set_cookie('tamtzit_prefs', json.dumps(prefs),
                        expires=datetime.now() + timedelta(days=100), domain='.' + request.host)
    return response


def refresh_cookies(param_request, response):
    site_prefs = param_request.cookies.get('tamtzit_prefs')
    if site_prefs:
        response.set_cookie('tamtzit_prefs', site_prefs,
                            expires=datetime.now() + timedelta(days=100), domain='.' + param_request.host)


@cachetools.func.ttl_cache(ttl=15)  # note that this only works when the method has an input param!
def check_if_daily_summary_in_progress(lang):
    debug("checking existence of daily summary")
    dt = datetime.now(ZoneInfo('Asia/Jerusalem'))

    # is there a daily summary draft from the last 3 hours [not a criteria: that's not yet "Done"]
    drafts, local_tses = fetch_drafts()

    for draft in drafts:
        if draft['translation_lang'] != lang:
            continue

        draft_last_mod = draft['last_edit']
        debug(f"/check_if_daily_summary_in_progress: draft last edit: " +
              f"{draft_last_mod}, now {dt}, delta: {dt - draft_last_mod}")
        if (dt - draft_last_mod).seconds > (60 * 90):  # 1.5 hours 
            return None
        return draft


@cachetools.func.ttl_cache(ttl=15)  # note that this only works when the method has an input param!
def get_cachable_status(role):
    debug("fetching uncached status info")
    status_per_lang = {}
    now = datetime.now(tz=JERUSALEM_TZ)
    drafts = fetch_drafts(query_order="-last_edit")[0]
    for draft in drafts:
        if draft['translation_lang'] in status_per_lang:
            continue
        status_per_lang[draft['translation_lang']] = {
            "lang": expand_lang_code(draft["translation_lang"], to_lang="H"),
            "who": get_user(user_id=draft["created_by"])['name_hebrew'],
            "started": draft['timestamp'].astimezone(JERUSALEM_TZ).strftime('%H:%M'),
            "last_edit": draft['last_edit'].astimezone(JERUSALEM_TZ).strftime('%H:%M'),
            "elapsed_since_last_edit": (now - draft['last_edit']).seconds,
            "ok_to_translate": draft['ok_to_translate'],
            "done": draft['is_finished'],
            "states": draft['states']
        }
        if draft['translation_lang'] in ['--']:  # not including H1 here - we don't need its text unless it's finished
            # we're keeping the Hebrew in the status even when it's not yet done as we're using it on the translation
            # page (edit.html) to let translators flip back and forth
            # between the Hebrew they started with and the 'latest'
            status_per_lang[draft['translation_lang']]['text'] = draft['hebrew_text']
        elif draft['is_finished'] and "admin" in role:
            if draft['translation_lang'] in ['H1']:
                status_per_lang[draft['translation_lang']]['text'] = draft['hebrew_text']
            else:
                status_per_lang[draft['translation_lang']]['text'] = draft['translation_text']
    response = {
        'as_of': now.strftime("%H:%M"),
        'by_lang': status_per_lang
    }
    return json.dumps(response)


@tamtzit.route("/status")
@require_login
def route_get_status_json():
    db_user_info = get_user(user_id=user_data_from_req(request)[Cookies.COOKIE_USER_ID])
    role = db_user_info['role']

    return get_cachable_status(role)


@tamtzit.route("/use_invitation")
def route_use_invitation_link():
    invitation = request.args.get("inv")
    debug(f"use_invitation: checking invitation {invitation}")
    if not invitation or len(invitation) < 36:
        return "Badly formatted request - missing invitation paramter"
    if len(invitation) > 36:
        invitation = invitation[0:36]
        debug(f"use_invitation: checking *trimmed* invitation {invitation}")

    if request.method == "GET":
        response = make_response(redirect("/"))
    elif request.method == "HEAD":
        debug("use_invitation: responding to head request with empty ...")
        return ''
    else:
        debug(f"use_invitation got unexpected request type {request.method}")
        return "UH oh"

    user_details = consume_invitation(invitation)

    if user_details:

        debug(f"/use_invitation: valid invitation for user {user_details['email']}")

        new_cookie = make_daily_cookie(user_details)
        response.set_cookie(Cookies.ONE_DAY_SESSION, new_cookie, expires=datetime.now() + timedelta(days=1))
        response.set_cookie(Cookies.ONE_WEEK_SESSION, new_cookie, expires=datetime.now() + timedelta(days=7))

        # response.set_cookie("tz_autha", new_cookie, max_age=60*60*24,
        # domain='.' + request.host, samesite="Lax", secure=True)
        # response.set_cookie("tz_authb", new_cookie, max_age=60*60*24*7,
        # domain='.' + request.host, samesite="Lax", secure=True)

        return response
    else:
        debug(f"use_invitation: returning an error - invitation seems invalid.")
        return render_template("error.html", dont_show_home_link=True,
                               msg="Invalid authentication link. Please contact an admin.",
                               heb_msg="הלינק לא תקין, צור קשר עם משה")


@tamtzit.route('/headers', methods=['POST', 'GET'])
def route_test_headers():

    if request.method == 'GET':
        return render_template("test_headers.html")
    elif request.method == 'POST':
        inputs = request.get_json()
        target_dt = inputs["date"]
        dt = datetime.fromisoformat(target_dt).replace(tzinfo=ZoneInfo("Asia/Jerusalem"))
        if inputs["time"] == "morn":  # noon eve motz
            dt = dt.replace(hour=7)
        elif inputs["time"] == "noon":
            dt = dt.replace(hour=13)
        elif inputs["time"] == "eve":
            dt = dt.replace(hour=19)
        elif inputs["time"] == "motz":
            dt = dt.replace(hour=17)

        lang = inputs["lang"]

        date_info = make_date_info(dt, lang)
        try:
            header = make_header(lang, date_info)
            body = dedent("""\
            תוכן תוכן תוכן 
            תוכן תוכן תוכן 
            תוכן תוכן תוכן       
            """)
            footer = make_footer(lang, date_info)
            return {"this":"thing", "that":(header + body + footer)}
        except:
            return {"that": "האפשרות הזאת לא קיימת"}



@tamtzit.route('/heb')
@require_login
@require_role("Hebrew")
def route_hebrew_template():
    next_page = detect_mobile(request, "hebrew")

    # is there a Hebrew draft from the last 3 hours [not a criteria: that's not yet "Done"]
    drafts, local_tses = fetch_drafts()
    current_user_info = get_user(user_id=user_data_from_req(request)[Cookies.COOKIE_USER_ID])
    debug(f"/heb: user={current_user_info['name']}, Drafts is {'' if drafts is None else 'not '} null")

    dt = datetime.now(ZoneInfo('Asia/Jerusalem'))
    for draft in drafts:
        if draft['translation_lang'] != '--':
            continue

        debug(f"/heb: should we show draft w/ lang={draft['translation_lang']}, " +
              f"is_finished={'is_finished' in draft and draft['is_finished']}, " +
              f"ok_to_translate={'ok_to_translate' in draft and draft['ok_to_translate']}")
        draft_last_mod = draft['last_edit']
        debug(f"/heb: draft's last edit is {draft_last_mod}, it's now {dt}, delta is {dt - draft_last_mod}")
        if (dt - draft_last_mod).seconds > (60 * 90):  # 1.5 hours per Yair's choice 
            break

        draft_creator_user_info = get_user(user_id=draft["created_by"])
        editor_name = "עוד לא ידוע"
        if ("editor" in current_user_info["role"] and 
            DraftStates.EDIT_ONGOING.name not in [states_entry["state"] for states_entry in draft["states"]]):
            editor_name = current_user_info["name_hebrew"]

        # originally I didn't bother passing date_info based on the assumption that by the time we reach this point
        # we're editing an existing draft, and the text will already have the date filled in, so there will be no
        # templating left to resolve. But there is an edge case where that might not play out: When we create the
        # draft entry in the DB, the text is *blank*. If the user quickly refreshes the page, heb_text here is blank,
        # so the logic in the hebrew.html page will use the template ... and will need this date info. One approach
        # to fixing it would be to ensure that _something_ is always saved to the DB, not blank; it seems not worse
        # to ensure that the call to render_template is kept as close as possible between here and the call below.
        date_info = make_date_info(dt, 'he')
        header = make_header('he', date_info)
        footer = make_footer('he', date_info)

        response = make_response(
            render_template(next_page, date_info=date_info, heb_text=Markup(draft['hebrew_text']),
                            header=header, footer=footer,
                            draft_key=draft.key.to_legacy_urlsafe().decode("utf8"),
                            ok_to_translate=("ok_to_translate" in draft and draft["ok_to_translate"]),
                            is_finished=('is_finished' in draft and draft['is_finished']), in_progress=True,
                            heb_font_size=get_font_sz_prefs(request)['he'],
                            author_user_name=draft_creator_user_info["name_hebrew"],
                            editor_user_name=editor_name,
                            states=draft['states'], user_role=current_user_info['role'],
                            user_info=current_user_info,
                            req_rule=request.url_rule.rule))
        refresh_cookies(request, response)
        return response

    # if no current draft was found, create a new one so that we have a key to work with and save to while editing
    key = create_draft('', current_user_info, dt, translation_lang='--')
    debug(f'Creating a new Hebrew draft with key {key.to_legacy_urlsafe().decode("utf8")}')
    date_info = make_date_info(dt, 'he')
    header = make_header('he', date_info)
    footer = make_footer('he', date_info)

    editor_name = "עוד לא ידוע"
    if "editor" in current_user_info["role"]:
        editor_name = current_user_info["name_hebrew"]

    response = make_response(
        render_template(next_page, date_info=date_info, draft_key=key.to_legacy_urlsafe().decode("utf8"),
                        header=header, footer=footer,                        
                        ok_to_translate=False, is_finished=False, in_progress=False,
                        heb_font_size=get_font_sz_prefs(request)['he'],
                        author_user_name=current_user_info["name_hebrew"],
                        editor_user_name=editor_name,
                        user_info=current_user_info,
                        states=[{"state": DraftStates.WRITING.name, "at": dt.strftime('%Y%m%d-%H%M%S'),
                                 "by": current_user_info["name"], "by_heb": current_user_info["name_hebrew"]}],
                        user_role=current_user_info['role'], req_rule=request.url_rule.rule))
    refresh_cookies(request, response)
    return response


@tamtzit.route("/keep_alive")
@require_login
@require_role("Hebrew")
def route_keep_alive():
    dt = datetime.now(ZoneInfo('Asia/Jerusalem'))
    return format_datetime(dt, locale='en_US')


@tamtzit.route('/heb_edit_daily_summary', methods=['POST', 'GET'])
@require_login
@require_role("Hebrew")
def route_hebrew_edit_daily_summary():
    next_page = detect_mobile(request, "hebrew")
    current_user_info = get_user(user_id=user_data_from_req(request)[Cookies.COOKIE_USER_ID])
    debug(f"/heb_edit_daily_summary: user={current_user_info['name']}")
    dt = datetime.now(ZoneInfo('Asia/Jerusalem'))

    if request.method == 'POST':
        key = create_draft(heb_text='', user_info=current_user_info, draft_timestamp=dt, translation_lang='H1')

        debug(f'Creating a new H1 draft with key {key.to_legacy_urlsafe().decode("utf8")}')
        date_info = make_date_info(dt, 'he')
        header = make_header('H1', date_info)
        footer = make_footer('H1', date_info)
        response = make_response(render_template(next_page, date_info=date_info,
                                                 header=header, footer=footer,
                                                 draft_key=key.to_legacy_urlsafe().decode("utf8"),
                                                 heb_text_body_only=Markup(request.form.get("hebrew_body_text")),
                                                 ok_to_translate=False, is_finished=False, in_progress=False,
                                                 heb_font_size=get_font_sz_prefs(request)['he'],
                                                 author_user_name=current_user_info["name_hebrew"],
                                                 editor_user_name="עוד לא ידוע",
                                                 user_info=current_user_info,
                                                 states=[{"state": DraftStates.WRITING.name,
                                                          "at": dt.strftime('%Y%m%d-%H%M%S'),
                                                          "by": current_user_info["name"],
                                                          "by_heb": current_user_info["name_hebrew"]}],
                                                 user_role=current_user_info['role'], req_rule=request.url_rule.rule))
        return response
    else:
        draft = check_if_daily_summary_in_progress('H1')
        if not draft:
            return render_template("error.html", dont_show_home_link=True,
                                   msg="No recent daily summary draft found.",
                                   heb_msg="אין סיכום יומי לערוך")

        draft_creator_user_info = get_user(user_id=draft["created_by"])
        date_info = make_date_info(dt, 'he')

        editor_name = "עוד לא ידוע"
        debug("checking what name to use for the editor...")
        if "editor" in current_user_info["role"]:
            editor_name = current_user_info["name_hebrew"]
        debug(f"set editor name to {editor_name}")

        response = make_response(
            render_template(next_page, date_info=date_info, heb_text=Markup(draft['hebrew_text']),
                            draft_key=draft.key.to_legacy_urlsafe().decode("utf8"),
                            ok_to_translate=("ok_to_translate" in draft and draft["ok_to_translate"]),
                            is_finished=('is_finished' in draft and draft['is_finished']), in_progress=True,
                            heb_font_size=get_font_sz_prefs(request)['he'],
                            author_user_name=draft_creator_user_info["name_hebrew"],
                            editor_user_name=editor_name,
                            states=draft['states'], user_role=current_user_info['role'],
                            user_info=current_user_info,
                            req_rule=request.url_rule.rule))
        return response


@tamtzit.route('/admin')
@require_login
@require_role("admin")
def route_administration():
    return render_template('admin.html')


@tamtzit.route('/heb-restart')
@require_login
@require_role("admin")
def route_hebrew_restart():
    db_user_info = get_user(user_id=user_data_from_req(request)[Cookies.COOKIE_USER_ID])

    # is there a Hebrew draft from the last 3 hours [not a criteria: that's not yet "Done"]
    drafts, local_tses = fetch_drafts()
    debug("Drafts is " + ("" if drafts is None else "not ") + "null")

    dt = datetime.now(ZoneInfo('Asia/Jerusalem'))
    for draft in drafts:
        if draft['translation_lang'] != '--':
            continue

        draft_last_mod = draft['last_edit']
        debug(f"/heb-restart: draft's last edit is {draft_last_mod}, it's now {dt}, delta is {dt - draft_last_mod}")
        if (dt - draft_last_mod).seconds > (60 * 90):  # 1.5 hours per Yair's choice 
            break
        else:
            debug("/heb-restart: Overriding last edit time of most recent Hebrew draft")
            edit_timestamp = datetime.now(tz=ZoneInfo('Asia/Jerusalem')) + timedelta(hours=-2)
            draft.update({"last_edit": edit_timestamp})
            draft.update({"is_finished": True})
            prev_states = draft["states"]
            prev_states.append({"state": DraftStates.ADMIN_CLOSED.name, "at": dt.strftime('%Y%m%d-%H%M%S'),
                                "by": db_user_info["name"], "by_heb": db_user_info["name_hebrew"]})
            draft.update({"states": prev_states})
            datastore_client.put(draft)
            break

    return make_response(redirect("/"))


@tamtzit.route("/set-debug-mode")
@require_login
@require_role("admin")
def route_set_debug_mode():
    return str(_set_debug(request.args.get("to")))


@tamtzit.route("/mark_published")
@require_login
@require_role("admin")
def route_mark_published():
    edition_lang = request.args.get("lang")
    db_user_info = get_user(user_id=user_data_from_req(request)[Cookies.COOKIE_USER_ID])

    debug(f"mark_published: {edition_lang} has been copied by {db_user_info['name']}")

    drafts, local_tses = fetch_drafts()
    debug("Drafts is " + ("" if drafts is None else "not ") + "null")

    dt = datetime.now(ZoneInfo('Asia/Jerusalem'))
    for draft in drafts:
        if draft['translation_lang'] != edition_lang:
            continue

        draft_last_mod = draft['last_edit']
        debug(f"/mark_published: draft's last edit is {draft_last_mod}, it's now {dt}, delta is {dt - draft_last_mod}")
        if (dt - draft_last_mod).seconds > (60 * 90):
            # 1.5 hours - if admin is going to publish by copying from the dash, it will certainly be within that time!
            break
        else:
            prev_states = draft["states"]
            if DraftStates.PUBLISHED.name in [st["state"] for st in prev_states]:
                debug("/mark_published: most recent Hebrew draft has already been published")
                break
            if DraftStates.PUBLISH_READY.name in [st["state"] for st in prev_states]:
                debug("/mark_published: marking most recent Hebrew draft as published")
                prev_states.append({"state": DraftStates.PUBLISHED.name, "at": dt.strftime('%Y%m%d-%H%M%S'),
                                    "by": db_user_info["name"], "by_heb": db_user_info["name_hebrew"]})
            draft.update({"states": prev_states})
            datastore_client.put(draft)
            break

    return "OK"


@tamtzit.route("/mark_edit_ready")
@require_login
def route_mark_edit_ready():
    draft_id_key = request.args.get('draft_id')
    if draft_id_key is None:
        debug("ERROR: /mark_edit_ready got no draft_id!")
        return None

    draft_id = Key.from_legacy_urlsafe(draft_id_key)
    if draft_id is None:
        debug("ERROR: /mark_edit_ready got invalid draft_id!")
        return

    draft = datastore_client.get(draft_id)
    if draft is None:
        debug("ERROR: /mark_edit_ready unable to find matching draft data!")
        return None

    prev_states = draft["states"]
    if DraftStates.EDIT_READY.name in [st["state"] for st in prev_states]:
        debug("/mark_edit_ready: draft has already been marked ready for editing")
        return "OK"
    
    dt = datetime.now(ZoneInfo('Asia/Jerusalem'))
    db_user_info = get_user(user_id=user_data_from_req(request)[Cookies.COOKIE_USER_ID])

    prev_states.append({"state": DraftStates.EDIT_READY.name, "at": dt.strftime('%Y%m%d-%H%M%S'),
                        "by": db_user_info["name"], "by_heb": db_user_info["name_hebrew"]})
    draft.update({"states": prev_states})
    datastore_client.put(draft)

    return "OK"



@tamtzit.route("/start_translation")
@require_login
@require_role("translator")
def route_start_translation():
    drafts, local_tses = fetch_drafts()
    dt = datetime.now(ZoneInfo('Asia/Jerusalem'))
    latest_heb = ''
    latest_creator = ''
    draft_id = None
    draft = None
    for draft in drafts:
        # if we can't find an ok-to-translate Hebrew draft from the last 3 hours, let the user know it's not ready...
        draft_last_mod = draft['last_edit']
        if (dt - draft_last_mod).seconds > (60 * 60 * 3):
            return render_template("error.html", msg="There is no current edition ready for translation.")

        if draft['translation_lang'] == '--' and (DraftStates.EDIT_READY.name in
                                                  [states_entry["state"] for states_entry in draft['states']]):
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
                           drafts=drafts, local_timestamps=local_tses, supported_langs=supported_langs_mapping,
                           states=draft['states'])


@tamtzit.route("/draft", methods=['GET'])
@require_login
@require_role("translator")
def route_continue_draft():
    """
    /translate and /draft are very similar:
       /translate creates a new entry based on the submission of the form at /start_translate  (POST)
       /draft     edits an existing entry based on a link       (GET)
    """
    next_page = detect_mobile(request, "editing")
    user_info = get_user(user_id=user_data_from_req(request)[Cookies.COOKIE_USER_ID])

    draft_timestamp = request.args.get('ts')
    edit_mode = request.args.get('edit')
    drafts, _ = fetch_drafts()

    for draft in drafts:
        ts = draft['timestamp']
        if ts.strftime('%Y%m%d-%H%M%S') == draft_timestamp:
            draft_creator_user_info = get_user(user_id=draft["created_by"])
            names = {
                "heb_author_in_heb": draft_creator_user_info["name_hebrew"],
                "heb_author_in_en": draft_creator_user_info["name"],
                "translator_in_heb": user_info["name_hebrew"],
                "translator_in_en": user_info["name"]
            }
            font_size_prefs = get_font_sz_prefs(request)
            key = draft.key

            # we want to show the *latest* Hebrew, and include both so the reviewer can compare
            heb_drafts = [d for d in drafts if d.key.id == int(draft['heb_draft_id'])]
            heb_draft = heb_drafts.pop() if len(heb_drafts) > 0 else None
            if not heb_draft:
                debug("/draft: ERR - unable to find original Hebrew draft!")
                heb_draft = draft

            return render_template(next_page, orig_heb_text=Markup(draft['hebrew_text']),
                                   latest_heb_text=Markup(heb_draft['hebrew_text']), 
                                   translated=Markup(draft['translation_text']),
                                   draft_timestamp=draft_timestamp,
                                   lang=draft['translation_lang'], **names, user_info=user_info,
                                   draft_key=key.to_legacy_urlsafe().decode('utf8'), heb_draft_id=draft['heb_draft_id'],
                                   heb_font_size=font_size_prefs['he'], en_font_size=font_size_prefs['en'],
                                   is_finished=('is_finished' in draft and draft['is_finished']),
                                   in_progress=not edit_mode or edit_mode == "false",
                                   states=draft['states'])

    return "Draft not found, please start again."


@tamtzit.route('/translate', methods=['POST'])
@require_login
@require_role("translator")
def route_translate():
    """
    /translate and /draft are very similar:
       /translate creates a new entry based on the submission of the form at /  (POST)
       /draft     edits an existing entry based on a link on the main page      (GET)
    """
    debug("/translate BEGIN")
    basic_user_info = user_data_from_req(request)
    user_info = get_user(user_id=basic_user_info["user_id"])
    transaction_context = {"user_info": user_info}
    draft_timestamp = datetime.now(tz=ZoneInfo('Asia/Jerusalem'))

    heb_text = request.form.get('orig_text')
    translation_engine = request.form.get("tx_engine")
    target_language_code = request.form.get('target_lang')

    if translation_engine == "OpenAI":
        debug("/translate - engine is OpenAI")
        if "use_async_results" not in request.form or request.form.get("use_async_results") != "True":
            debug(f"Create an ASYNC request")
            # create a request for asynchronous translation - we get here based on submit of input.html
            key = datastore_client.key("async_job")
            entity = datastore.Entity(key=key, exclude_from_indexes=("translation_result", "translation_custom_dirs", "heb_text"))
            entity.update({"created_at": draft_timestamp,
                           "created_by": user_info["name"],
                           "operation": "translation",
                           "translation_lang": target_language_code,
                           "heb_draft_id": request.form.get('heb_draft_id'),
                           "heb_author_id": request.form.get('heb_author_id'),
                           "heb_text": heb_text,
                           "translation_engine": "openai/gpt-4o",
                           "translation_custom_dirs": request.form.get("openai-custom-dirs"),
                           "translation_result": ""  # necessary to get it to save exclude from indexes
                           })
            datastore_client.put(entity)
            entity = datastore_client.get(entity.key)

            # call an endpoint exposed by the async processor to let it know there's a pending request
            debug(f"route_translate: calling requests.get({os.getenv('ASYNC_PROCESSOR_URL')}{entity.key.id})")
            requests.get(f"{os.getenv('ASYNC_PROCESSOR_URL')}{entity.key.id}")

            # return a *new* page - OpenAI is processing your request, this page will auto-refresh when it is ready
            return render_template("async_pending.html", async_request_id=entity.key.id,
                                   heb_draft_id=request.form.get('heb_draft_id'),
                                   heb_author_id=request.form.get('heb_author_id'),
                                   orig_text=heb_text,
                                   target_lang=target_language_code)
        else:
            debug("Using ASYNC results")
            # fetch and process the results of asynchronous translation - we get here based on call from async_pending.html
            job = datastore_client.get(datastore_client.key("async_job", int(request.form.get("tx_async_request_id"))))

            transaction_context["heb_draft_id"] = job["heb_draft_id"]
            transaction_context["translation_result"] = job["translation_result"]
            heb_text = job["heb_text"]
            heb_author_id = job["heb_author_id"]
            target_language_code = job["translation_lang"]
    else:
        # we're translating with Google

        transaction_context["heb_draft_id"] = request.form.get('heb_draft_id')
        heb_author_id = request.form.get('heb_author_id')

    # Continue below if translating with Google or parsing raw translation result from async call to OpenAI
    info = process_translation_request(heb_text, target_language_code, translation_engine, transaction_context)

    date_info = make_date_info(draft_timestamp, target_language_code)
    header = make_header(target_language_code, date_info)
    footer = make_footer(target_language_code, date_info)

    # dt = info['date_info'].based_on_dt
    draft_timestamp_str = draft_timestamp.strftime('%Y%m%d-%H%M%S')
    utc_draft_timestamp = draft_timestamp.astimezone(tz=ZoneInfo("UTC"))
    utc_draft_timestamp_str = utc_draft_timestamp.strftime('%Y%m%d-%H%M%S')

    draft_creator_user_info = get_user(user_id=heb_author_id)
    names = {
        "heb_author_in_heb": draft_creator_user_info["name_hebrew"],
        "heb_author_in_en": draft_creator_user_info["name"],
        "translator_in_heb": user_info["name_hebrew"],
        "translator_in_en": user_info["name"]
    }

    target_lang = supported_langs_mapping[target_language_code]
    translated = render_template(target_lang.lower() + '.html', **info, header=header, footer=footer,
                                 draft_timestamp=draft_timestamp_str, **names)
    translated = re.sub('\n{3,}', '\n\n', translated)
    # this is necessary because the template can generate large gaps due to unused sections

    # store the draft in DB so that someone else can continue the translation work
    create_draft(heb_text, user_info, draft_timestamp=draft_timestamp, translation_text=translated,
                 translation_lang=target_language_code, translation_engine=translation_engine,
                 heb_draft_id=transaction_context['heb_draft_id'])
    
    # redirect to /draft so that we'll have the proper link in the URL bar for sharing
    return make_response(redirect(url_for("tamtzit.route_continue_draft", ts=utc_draft_timestamp_str, edit="true")))


@tamtzit.route("/check_async")
def route_check_async():
    debug(f"route_check_async: async_request_id is {request.args.get('async_request_id')}")
    if request.args.get('async_request_id') is None or not request.args.get('async_request_id').isdigit():
        return "Error - missing parameter"
    my_job = datastore_client.get(datastore_client.key("async_job", int(request.args.get('async_request_id'))))
    if my_job and "result_code" in my_job:
        return my_job["result_code"]
    return "Pending"


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
    translated_txt = request.form.get('translation')
    source_text = request.form.get('source_text')
    if translated_txt and len(translated_txt) > 0:
        if confirm_user_has_role(request, "translator"):
            user_info = get_user(user_id=user_data_from_req(request)[Cookies.COOKIE_USER_ID])
            update_translation_draft(draft_key, translated_txt, user_info, is_finished=finished)
        else:
            return "Error: saveDraft called with change to translated text, but user does not have appropriate role."
    elif source_text and len(source_text) > 0:
        if confirm_user_has_role(request, "Hebrew"):
            user_info = get_user(user_id=user_data_from_req(request)[Cookies.COOKIE_USER_ID])
            update_hebrew_draft(draft_key, source_text, user_info, is_finished=finished,
                                ok_to_translate=send_to_translators)
        else:
            return "Error: saveDraft called with change to Hebrew text, but user does not have the appropriate role."
    else:
        debug("ERROR: /saveDraft didn't get the input it was expecting!")
        return "ERROR - saveDraft called without translation or source_text fields"
    return "OK"


@tamtzit.route("/getUntranslatedAdditions", methods=["GET"])
def get_untranslated_additions():
    debug(f"get_untranslated_additions: heb_draft_id is {request.args.get('heb_draft_id')}")
    heb_draft_id = request.args.get('heb_draft_id')
    if heb_draft_id is None:
        debug("ERROR: /getUntranslatedAdditions got None heb_draft_id!")
        return None
    # actually we want to compare with the draft as it was when the translation being worked on was created
    # - which is saved in the hebrew_text field of the draft object!
    translation_draft_id = Key.from_legacy_urlsafe(request.args.get('translation_draft_id'))
    if translation_draft_id is None:
        debug("ERROR: /getUntranslatedAdditions got None translation_draft_id!")
        return

    heb_draft = datastore_client.get(datastore_client.key("draft", int(heb_draft_id)))
    if heb_draft is None:
        debug("ERROR: /getUntranslatedAdditions got None matching hebrew_draft!")
        return None

    translated_draft = datastore_client.get(translation_draft_id)
    if translated_draft is None:
        debug("ERROR: /getUntranslatedAdditions got None matching translated_draft!")
        return None

    lang = request.args.get('lang')
    try:
        additions_by_section, translated_additions_by_section = (
            get_translated_additions_since_ok_to_tx(
                heb_draft['hebrew_text'], translated_draft['hebrew_text'], target_lang=lang))
    except Exception:  # noqa eventually I should find the right exception classes
        debug("There was an error trying to get deltas, returning no deltas.")
        additions_by_section = translated_additions_by_section = {}

    response = Markup(json.dumps({"additions": additions_by_section,
                                  "translated_additions": translated_additions_by_section}))
    print(response)
    return response


@tamtzit.route('/start_daily_summary')
@require_login
def start_daily_summary():
    next_page = "start_daily_summary.html"
    # not doing detect mobile - there's only one version of this page, suitable for both desktop and mobile

    lang = request.args.get("lang") or 'he'
    if lang == 'he':
        if not confirm_user_has_role(request, ["Hebrew", "editor", "admin"]):
            return render_template("error.html", msg="You don't have access to this section.",
                                   heb_msg="חלק הזה של האתר מיועד למשתמשים אחרים")
    else:
        raise ValueError("Invalid lang parameter for start_daily_summary")

    # this is a map from edition name (morning, afternoon, eve) to a draft object
    debug(f"start_daily_summary: getting yesterday's editions...")
    todays_editions = get_latest_day_worth_of_editions()[lang]
    organized_editions = {}
    for edition_time_of_day in todays_editions:
        debug(f"start_daily_summary: processing {edition_time_of_day}")
        edition = todays_editions[edition_time_of_day]
        processed_text_info = (
            process_translation_request(edition['hebrew_text' if lang == 'he' else 'translation_text'], lang))
        # we get back:
        #  {'heb_text': heb_text, 'date_info': date_info, 'organized': organized,
        #  'sections': sections[target_language_code]}
        organized_editions[edition_time_of_day] = processed_text_info['organized']
    return render_template(next_page, organized_editions=organized_editions, times_of_day=editions,
                           sections_in_order=sections['keys_from_Hebrew'])


def get_scheduling_dates():
    now = datetime.now(ZoneInfo('Asia/Jerusalem'))
    dow = now.isoweekday()  # Monday = 1, Sunday = 7
    if dow == 7:
        dow = 0   # make Sun-Sat 0-6
    this_week_from = now - timedelta(days=dow)
    this_week_from_str = format_date(this_week_from, "MMMM d", locale='en')
    this_week_to = this_week_from + timedelta(days=6)
    this_week_to_str = format_date(this_week_to, "MMMM d", locale='en')
    read_only = (dow == 6 and now.hour >= 21) #or (dow == 0 and now.hour < 6)
    next_week_from = now + timedelta(days=(7 - dow))
    next_week_to = next_week_from + timedelta(days=6)
    next_week_from_str = format_date(next_week_from, "MMMM d", locale='en')
    next_week_to_str = format_date(next_week_to, "MMMM d", locale='en')
    week_being_scheduled = next_week_from_str + " to " + next_week_to_str
    week_already_scheduled = this_week_from_str + " to " + this_week_to_str

    return {"this_week_from": this_week_from, "this_week_from_str": this_week_from_str,
            "next_week_from": next_week_from, "next_week_from_str": next_week_from_str, 
            "this_week_to": this_week_to, "this_week_to_str": this_week_to_str,
            "next_week_to": next_week_to, "next_week_to_str": next_week_to_str,
            "week_being_scheduled": week_being_scheduled, "week_already_scheduled": week_already_scheduled,
            "read_only": read_only, "day_of_week": dow, "day_of_week_str": now.strftime('%A'), "date_obj": now}


def get_next_translators():
    sched_dates = get_scheduling_dates()
    date_info = make_date_info(sched_dates['date_obj'], 'en')   # always English as page uses En tag names

    result = {"English": None}

    query = datastore_client.query(kind="translation_schedule")
    query.add_filter(filter=PropertyFilter("week_from", "=", sched_dates['this_week_from_str']))
    schedule_info = query.fetch()
    schedule = None
    for s in schedule_info:
        schedule = s['schedule']

    if schedule:
        result["English"] = schedule[sched_dates['day_of_week_str']][date_info.part_of_day]
    else:
        # should happen only when debugging
        result["English"] = "None"

    return result


@tamtzit.route('/tx_schedule_curr')
def route_translation_current_schedule():
    sched_dates = get_scheduling_dates()
    sched_obj = Schedule("en")
    sched_week = sched_dates['next_week_from_str'] if (sched_dates['read_only'] or 'next_week' in request.args) else sched_dates['this_week_from_str']
    editions_to_skip = get_user_availability(zero_user, sched_week)
    if 'translation' in editions_to_skip['available']:
        editions_to_skip = editions_to_skip['available']['translation']
    else:
        editions_to_skip = editions_to_skip['available']

    query = datastore_client.query(kind="translation_schedule")
    debug(f"tx_schedule_curr: fetching schedule for week of {sched_week}")
    query.add_filter(filter=PropertyFilter("week_from", "=", sched_week))
    schedule_info = query.fetch()
    schedule = None
    for s in schedule_info:
        debug("got a schedule from the db...")
        schedule = s['schedule']

    debug(f"tx_schedule_curr: passing data: {schedule}")

    return render_template("tx_schedule.html", week=sched_obj.week,
                           editions_to_skip=Markup(json.dumps(editions_to_skip)),
                           week_being_scheduled=(sched_dates['week_being_scheduled'] if sched_dates['read_only'] else sched_dates['week_already_scheduled']),
                           schedule_data=Markup(json.dumps(schedule))) 
    # make_response(redirect(
    # "https://docs.google.com/spreadsheets/d/1ataLRPh19z_EKiFTM9CxuoVKYL8VvxhQL8h5hZqBtY4/edit?gid=0#gid=0"))


@tamtzit.route('/tx_schedule_signup')
@require_login
@require_role("translator_en")
def route_translation_schedule_signup():
    sched_obj = Schedule("en")
    sched_dates = get_scheduling_dates()
    # you can schedule *next week* any time from Sunday morning 6 am until Sat night 11pm. 
    # No scheduling allowed Sat night 11pm -> Sun morning so no one gets confused that they're affecting this week

    db_user_info = get_user(user_id=user_data_from_req(request)[Cookies.COOKIE_USER_ID])
    user_schedule_availability = get_user_availability(db_user_info, sched_dates['next_week_from_str'])
    usa_as_json = json.dumps(user_schedule_availability['available'])
    editions_to_skip = get_user_availability(zero_user, sched_dates['next_week_from_str'])
    is_summer_daylight_savings_time = bool(datetime.now(tz=ZoneInfo("Asia/Jerusalem")).dst())
    if not is_summer_daylight_savings_time:
        editions_to_skip["available"]["Saturday"][1] = 0

    debug("tx_schedule_signup returning availability: " + Markup(usa_as_json))
    return render_template("tx_signup.html", week=sched_obj.week,
                           with_early_motzash=not is_summer_daylight_savings_time,
                           week_being_scheduled=sched_dates['week_being_scheduled'],
                           user_availability=Markup(usa_as_json), read_only=sched_dates['read_only'],
                           editions_to_skip=Markup(json.dumps(editions_to_skip['available'])))


@tamtzit.route('/tx_schedule_nextweek_volunteer')
@require_login
@require_role("translator")
def route_translation_schedule_nextweek_volunteer():
    db_user_info = get_user(user_id=user_data_from_req(request)[Cookies.COOKIE_USER_ID])
    # I should really audit this somewhere ... 
    sched_dates = get_scheduling_dates()
    update_user_availability(db_user_info, sched_dates['next_week_from_str'],
                             json.loads(request.args.get('updated_availability')))
    return "OK"


@tamtzit.route('/team_avail_next_week')
@require_login
@require_role("admin")
def route_team_availability_next_week():
    sched_dates = get_scheduling_dates()
    team_availability = {}
    # map of team_name -> team_member_name -> int # slots avail next week
    # I'm not caching as assuming this page will be rarely used, but if false or if this code is reused elsewhere, cache!
    query = datastore_client.query(kind="user")
    users = query.fetch()
    for user in users:
        user_availability = get_user_availability(user, sched_dates['next_week_from_str'])["available"]
        if "translator_" in user["role"]:
            start_pos = user["role"].index("translator_") + len("translator_")
            team = user["role"][start_pos:start_pos+3]
        elif "Hebrew" in user["role"]:
            team = "he"
        else:
            continue # this person is an editor or admin
            # print(f"ERROR: route_team_availability_next_week: can't determine team from {user['role']}")

        if team not in team_availability:
            team_availability[team] = {}

        # I'm adding 'translation' and 'review' to user availability which previously only had one kind
        # need to be backward compatible with old DB entries
        if 'translation' not in user_availability:
            user_availability['translation'] = dict(user_availability)
            user_availability['review'] = {}

        team_availability[team][user['name']] = (sum([sum(user_availability['translation'][key]) for key in user_availability['translation']]) +
                                                 sum([sum(user_availability['review'][key]) for key in user_availability['review']]))

    return render_template("team_avail_next_week.html", team_availability=team_availability)
        


@tamtzit.route('/tx_schedule_thisweek_change')
@require_login
@require_role(["translator", "admin"])
def route_translation_schedule_thisweek_change():
    # db_user_info = get_user(user_id=user_data_from_req(request)[Cookies.COOKIE_USER_ID])

    sched_dates = get_scheduling_dates()
    sched_obj = Schedule("en")
    # day_name=edition_parts[0], edition_name=edition_parts[1], new_translator=new_val to the server
    day_name = request.args.get('day_name')
    edition_name = request.args.get('edition_name')
    tx_or_rv = request.args.get("which_role")
    new_volunteer = request.args.get('new_volunteer') or "---"

    schedule_week = sched_dates['this_week_from_str'] if not sched_dates['read_only'] else sched_dates['next_week_from_str']
    print(f"fetching schedule for {schedule_week}")
    schedule = sched_obj.fetch_from_db(schedule_week)   # @TODO change to support scheds beyond English
    if not day_name or not day_name in schedule['schedule']:
        return "ERROR bad param day_name: " + day_name
    if not edition_name or not edition_name in schedule['schedule'][day_name]:
        return "ERROR bad param edition_name: " + (edition_name if edition_name else "MISSING")
    if not tx_or_rv or not tx_or_rv in ["tx", "rv"]:
        return "ERROR bad param tx_or_rv " + tx_or_rv
    schedule['schedule'][day_name][edition_name]['translator' if tx_or_rv == 'tx' else 'reviewer'] = new_volunteer 

    datastore_client.put(schedule)

    return "OK"


@tamtzit.route('/tx_build_sched_for_next_week')
def route_translation_build_next_schedule():
    # as this is meant to be called only by the App Engine scheduler, we check an expected header
    # and if it's not there, reject the request
    debug("Building next week's translation schedule...")
    # if 'X-Appengine-Cron' not in request.headers or request.headers['X-Appengine-Cron'] != 'true':
    #     debug("This request does not come from AppEngine, so ignoring it.")
    #     return

    sched_dates = get_scheduling_dates()

    # once a week let's clean up old entries from this table
    query = datastore_client.query(kind="user_availability")
    user_avail_info = query.fetch()
    this_month = format_date(sched_dates['this_week_from'], "MMMM", locale='en')
    if this_month in ["January","February","March","April","May","June","July","August","September","October","November","December"]:
        # that check is extra protection because I can't figure out why some availability entries were deleted
        print(f"Deleting old availability entries - anything not from {this_month}")
        for info in user_avail_info:
            if not info["week_of"].startswith(this_month):
                print(f"deleting {info}")
                print(f"Just to be clear, the availability part: {info['available']}")
                datastore_client.delete(info.key)
    # done with cleanup

    for lang in ["en"]:   # @TODO support other langs
        sched = Schedule(lang) 
        sched.cache_user_info()

        if request.args.get('redo'):
            sched.get_input_from_datastore(sched_dates["this_week_from_str"])
        else:
            sched.get_input_from_datastore(sched_dates['next_week_from_str'])
        sched.make_translation_schedule()
        sched.print_schedule()
        if request.args.get('redo'):
            sched.persist_schedule(sched_dates['this_week_from_str'])
        else:
            sched.persist_schedule(sched_dates['next_week_from_str'])
        the_following_week = sched_dates['next_week_from'] + timedelta(days=7)
        the_following_week_str = format_date(the_following_week, "MMMM d", locale='en')
        sched.set_up_next_week(the_following_week_str, non_interactive_mode_p=True)
    return "Done"


@tamtzit.route('/nightly_archive_cleanup')
def nightly_archive_cleanup():
    # as this is meant to be called only by the App Engine scheduler, we check an expected header
    # and if it's not there, reject the request
    debug("Cleaning the day's archive entries...")
    if 'X-Appengine-Cron' not in request.headers or request.headers['X-Appengine-Cron'] != 'true':
        debug("This request does not come from AppEngine, so ignoring it.")
        return

    debug(f"n_a_c headers look good, progressing")
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    # make a map of each language's most mature editions from the last day
    yesterdays_editions = get_latest_day_worth_of_editions()

    # For each language which is archived:
    for lang in ['he', 'en', 'fr']:
        debug(f"n_a_c cleaning up archive for {lang}")

        # step 1: get the relevant archive page
        prev_archive = requests.get(f"{ARCHIVE_BASE}archive-{lang}.html").text
        soup = BeautifulSoup(prev_archive, "html.parser")
        next_entry_tag = soup.find(id='next-entry')  # we'll use it later to insert content
        debug(f"n_a_c archive fetched")

        # step 2: strip out all of yesterday's entries from the archives, if any
        for div in soup.find_all("div"):
            div: Tag
            if div is None:
                debug("Strange - got a None div, continuing...")
                continue
            if div.decomposed:
                debug("Skipping an inner decomposed div")
                continue
            if div.attrs is None:
                debug("Strange - div's attrs is None. Probably the inner div of the div we just deleted, continuing...")
                continue
            if 'id' not in div.attrs:
                debug(f"Deleting a div with no id: {div}")
                div.decompose()
                continue
            if div.attrs['id'] == 'next-entry':
                debug("skipping next-entry div")
                continue
            if div.attrs['id'].startswith(yesterday):
                debug(f"deleting a yesterday div: \n{div}")
                div.decompose()
                continue
        debug("n_a_c Done deleting yesterday's entries")

        # step 3: insert (in reverse chronological order) 1 entry for each of yestderday's editions        
        for edition_time_of_day in reversed(yesterdays_editions[lang]):
            edition = yesterdays_editions[lang][edition_time_of_day]
            anchor = edition['timestamp'].astimezone(JERUSALEM_TZ).strftime('%Y-%m-%d') + '-' + edition_time_of_day

            make_new_archive_entry(soup, next_entry_tag, edition, anchor, lang)
            debug(f"n_a_c inserted entry for {edition_time_of_day}")

            # step 3b: save state change history to our audit table
            key = datastore_client.key("audit")
            entity = datastore.Entity(key=key)
            entity.update({"date": yesterday, "edition": edition_time_of_day, "lang": lang,
                           "states": edition['states']})
            datastore_client.put(entity)

        # step 4: push the updated page back to cloud storage
        upload_to_cloud_storage(f"archive-{lang}.html", str(soup))

    return "OK"


def process_translation_request(heb_text, target_language_code, translation_engine="Google",
                                transaction_context: dict = {}):

    if heb_text is not None and len(heb_text) > 0:
        heb_text = strip_header_and_footer(heb_text, target_language_code)

    if target_language_code in ["YY", "he"]:
        translated = heb_text
    else:
        if transaction_context.get("translation_result", None) is not None:
            translated = transaction_context.get("translation_result")
        else:
            translated = translate_text(heb_text, target_language_code=target_language_code,
                                    engine=translation_engine, transaction_context=transaction_context)

    debug(f"RAW TRANSLATION:--------\n{translated}")
    debug(f"--------------------------")

    heb_text = Markup(heb_text)  # .replace("\n", "<br>"))
    translated_lines = translated.split("\n")

    kw = keywords[target_language_code]
    section_titles = sections[target_language_code]

    def kw_match(keywords, line):
        if type(keywords) is str:
            return keywords in line
        elif type(keywords) is list:
            for keyword in keywords:
                if keyword in line:
                    return True
        return False

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
                # @TODO
                # this is where we need to check if we've got a special header, e.g. motzei Shabbat,
                # and need to ignore it rather than add it to UNKNOWN
                debug("post three dots, switching to 'unknown'")
                section = organized['UNKNOWN']
                continue
        if section is None and (kw_match(kw["edition"], line.lower())) and '202' in line.lower():
            debug("skipping what looks like the intro edition line")
            continue
        if line.startswith("> "):
            debug("bullet line...")
            if (kw_match(kw["southern"], line.lower())) and 'SOUTH' not in organized:
                debug("starting south section")
                section = organized['SOUTH']
            elif (kw_match(kw["northern"], line.lower())) and 'NORTH' not in organized:
                debug("starting north section")
                section = organized['NORTH']
            elif (kw_match(kw["yemen"], line.lower())) and "YEMEN" not in organized:
                debug("starting Yemen section")
                section = organized['YEMEN']
            elif (kw_match(kw["jands"], line.lower())) and 'YandS' not in organized:
                debug("starting J&S section")
                section = organized['YandS']
            elif (kw_match(kw["rising-lion"], line.lower())) and 'RISING-LION' not in organized:
                debug("starting RISING-LION section")
                section = organized['RISING-LION']
            # elif kw["policy"] in line.lower() and "politics" in line.lower() and 'PandP' not in organized:
            #     debug("starting policy section")
            #     section = organized['PandP']
            # elif kw["in the world"] in line.lower() and "Worldwide" not in organized:
            #     debug("starting world section")
            #     section = organized["Worldwide"]
            elif section is not None:
                debug(f"inside section {section}")
                section.append(Markup(line))
        elif line.startswith("📌"):
            debug("pin line...")
            if kw_match(kw["intro_pin"], line.lower()):
                debug("skipping what looks like the intro pin line")
                continue
            if kw_match(kw["security"], line.lower()):
                debug("starting Security section")
                section = organized['Security']
            elif kw_match(kw["in israel"], line.lower()):
                debug("starting inIsrael section")
                section = organized['InIsrael']
            elif kw_match(kw["world"], line.lower()):
                debug("starting world section")
                section = organized["Worldwide"]
            elif kw_match(kw["policy"], line.lower()):
                debug("starting policy section")
                section = organized['PandP']
            elif kw_match(kw["weather"], line.lower()):
                debug("Starting weather section")
                section = organized['Weather']
            elif kw_match(kw["economy"], line.lower()):
                debug("Starting economy section")
                section = organized["Economy"]
            elif kw_match(kw["sport"], line.lower()):
                debug("Starting sports section")
                section = organized["Sports"]
            elif kw_match(kw["finish"], line.lower()):
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

    if len(organized["UNKNOWN"]) == 0:
        del organized["UNKNOWN"]

    # for the first pass the translation isn't sent as a block of text but rather 
    # as small blocks broken down by section. Later after the first human review pass we'll save it
    # as a contiguous block in the DB and going forward work from that
    result = {'heb_text': heb_text, 'organized': organized,  # 'date_info': date_info,
              'sections': sections[target_language_code]}
    return result


if __name__ == '__main__':
    text = "האגף לפיקוח על קופות חולים ריכז עבור כולם מידע חיוני לימים אלו."

    print(f" {text} ".center(50, "-"))
    for target_language in ['en', 'ru', 'es', 'fr']:
        translation = translate_text(text, target_language)
        source_language = translation.detected_language_code
        translated_text = translation.translated_text
        print(f"{source_language} → {target_language} : {translated_text}")
