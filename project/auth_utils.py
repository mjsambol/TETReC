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

import base64
import cachetools.func
from datetime import datetime
import functools
import json
import os
from uuid import uuid4
from zoneinfo import ZoneInfo

from flask import redirect, render_template, request
from google.cloud import datastore
from google.cloud.datastore.query import PropertyFilter
from google.appengine.api import mail as gcp_mail
import requests
from requests.auth import HTTPBasicAuth

if __package__ is None or __package__ == '':
    # uses current directory visibility
    from common import DatastoreClientProxy, debug
    from cookies import Cookies, get_cookie_dict, get_today_noise, user_data_from_req
else:
    from .common import DatastoreClientProxy, debug
    from .cookies import Cookies, get_cookie_dict, get_today_noise, user_data_from_req

datastore_client = DatastoreClientProxy.get_instance()

mailjet_basic_auth = HTTPBasicAuth(os.environ.get("MAILJET_KEY", ""), os.environ.get("MAILJET_PWD", ""))


def create_invitation(user):
    key = datastore_client.key("invitation")
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
    query.add_filter(filter=PropertyFilter("link_id", "=", invitation))
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
            debug("Invitation is valid, marking it used...")
            inv.update({"used_at_timestamp": now})
            datastore_client.put(inv)
            user_details = get_user(user_id=inv["user_id"])
            return user_details
    debug("consume_invitation: Returning None")
    return None


@cachetools.func.ttl_cache(ttl=600)
def validate_weekly_birthcert(bcert):
    query = datastore_client.query(kind="crypto_noise")
    daily_noise_entries = query.fetch()
    for daily_noise_entry in daily_noise_entries:
        daily_noise = daily_noise_entry["daily_noise"]
        if daily_noise in bcert:
            return True
    return False


@cachetools.func.ttl_cache(ttl=300)
def get_user(email=None, user_id=None):
    debug("getting users from DB...")

    if email:
        query = datastore_client.query(kind="user")
        debug(f"Based on email {email}")
        query.add_filter(filter=PropertyFilter("email", "=", email))
        users = query.fetch()
        for user in users:
            debug(f"Got back {user}")
            return user
        # for some reason that I cannot understand, I've now twice (at least) seen a new user added to the DB,
        # but then not found by the above query until I add them a second time. I don't know if there's some problem
        # with the query itself or elsewhere, but as an additional check I'm going to try to find the user with 
        # a different approach
        debug(f"get_user: found no results for email {email}, trying instead to loop through all users...")
        query = datastore_client.query(kind="user")
        users = query.fetch()
        for user in users:
            debug(f"get_user({email}) - query for all users got {user}")
            if user['email'] == email:
                return user
    elif user_id:
        debug(f"Based on user ID {user_id}")
        user = datastore_client.get(datastore_client.key("user", int(user_id)))
        debug(f"Got back {user}")
        return user

    debug("No matching user found.")
    return None


def send_invitation(user_details, invitation):
    email_message = (f"To access the Tamtzit HaChadashot Admin Application, click the link below:\n\n "
                     f"{invitation}")

    rtf_content = invitation
    # rtf_content2 = r"""
    # {\rtf1\ansi\ansicpg1252\deff0\nouicompat\deflang1033
    # {\fonttbl{\f0\fnil\fcharset0 Calibri;}}
    # {\*\generator Riched20 10.0.22621}\viewkind4\uc1
    # \pard\sa200\sl276\slmult1\f0\fs22\lang9 To access the Tamtzit console, click the link below:\par
    # \par
    # {\field{\*\fldinst{HYPERLINK """ + invitation + r""" }}{\fldrslt """ + invitation + r"""Access the Application}}\par
    # }
    # """

    data = {"Messages": [{"From": {"Email": os.environ.get("EMAIL_SENDER_ADDR", ""), "Name": os.environ.get("EMAIL_SENDER_NAME", "")},
                          "To": [{"Email": user_details["email"], "Name": user_details["name"]}],
                          "Subject": "Tamtzit HaChadashot Admin App Access",
                          "TextPart": email_message}]}

    # Malke uses Outlook and her company has enabled Safe Links, which has two negative side effects:
    # 1. URLs are mangled
    # 2. A server pre-checks the content at the URL's target to verify that it's "safe"
    #    - which means the invitation is clicked before she gets to it.
    # According to MSFT's documentation, 
    # https://learn.microsoft.com/en-us/defender-office-365/safe-links-about?view=o365-worldwide
    #   Safe Links doesn't provide protection for URLs in Rich Text Format (RTF) email messages.
    # So I'm atting an RTF attachment to every email to Malke and other users who need it.
    if "overrides" in user_details and "rtf_email" in user_details["overrides"]:
        debug(f"send_invitation: user {user_details['name']} requires RTF email, adding the attachment.")

        data["Messages"][0]["TextPart"] = "Your account is set for use with Outlook email. Please use the link in the attachment."
        data["Messages"][0]["Attachments"] = [
                {
                    "ContentType": "application/rtf",
                    "Filename": "Invitation.rtf",
                    "Base64Content": base64.b64encode(rtf_content.encode("utf-8")).decode('utf-8')
                }
        ]

    mailjet_resp = requests.post("https://api.mailjet.com/v3.1/send", auth=mailjet_basic_auth, 
                                 headers={"Content-Type": "application/json"}, data=json.dumps(data))

    debug(f'Sending invitation email (mailjet) - status: {mailjet_resp.json()["Messages"][0]["Status"]}')

    # now trying with GCP mail
    message = gcp_mail.EmailMessage(sender=os.environ.get("EMAIL_SENDER_ADDR", ""), subject="Tamtzit HaChadashot Admin App Access")
    message.to = user_details["email"]
    if "overrides" in user_details and "rtf_email" in user_details["overrides"]:
        message.body = "Your account is set for use with Outlook email. Please use the link in the attachment."
        message.attachments = [("Invitation.rtf", rtf_content)]
    else:
        message.body = email_message

    try:
        message.send()
    except:
        debug("Error sending email via GCP, hopefully because I'm running locally.")


def require_login(func):
    @functools.wraps(func)    # this is necessary so that Flask routing will work!!
    def authentication_check_wrapper(*args, **kwargs):
        debug("Checking authentication status...")
        today_session = None
        # check if there is a cookie with a valid session cert
        # (session cookie - short expiration, but saves checking the DB frequently)
        # - that is, today's date + some noise encrypted with our key
        # if there is, let the method which called us continue. 
        # if not, redirect to /auth while passing the URL the user was requesting
        session_cookie = request.cookies.get(Cookies.ONE_DAY_SESSION)
        if session_cookie:
            today_session = get_cookie_dict(request, Cookies.ONE_DAY_SESSION)
        else:
            debug("No session cookie found (orig style)")
            session_cookie = request.cookies.get("tz_autha")
            if session_cookie:
                today_session = get_cookie_dict(request, "tz_autha")

        if 'today_session' not in locals():
            debug("tried everything, can't find a cookie. redirecting to auth.")
            return redirect("/auth?requested=" + request.full_path)

        today_noise = get_today_noise()
        if today_session and (Cookies.COOKIE_CERT in today_session) and (today_noise in today_session[Cookies.COOKIE_CERT]):
            debug("Decrypted cookie is valid!")
            return func(*args, **kwargs)
        
        debug("daily cookie found but expired / invalid")
        return redirect("/auth?requested=" + request.full_path)

    return authentication_check_wrapper


def confirm_user_has_role(request_p, roles_accepted):
    debug(f"Checking role requirements, looking for {roles_accepted}")
    db_user_info = get_user(user_id=user_data_from_req(request_p)[Cookies.COOKIE_USER_ID])
    roles = db_user_info['role']
    debug(f"user has roles {roles}")
    has_role = False
    if type(roles_accepted) is str:
        has_role = roles_accepted in roles
    elif type(roles_accepted) is list:
        for role in roles_accepted:
            if role in roles:
                has_role = True
    return has_role


def require_role(roles_accepted):
    # the roles_accepted parameter can be either a string or a list of strings. 
    # If a list, they are treated as "OR" - access is granted if the user has any 
    def decorator_require_role(func):
        @functools.wraps(func)    # this is necessary so that Flask routing will work!!
        def role_check_wrapper(*args, **kwargs):
            if confirm_user_has_role(request, roles_accepted):
                return func(*args, **kwargs)
            else:
                return render_template("error.html", msg="You don't have access to this section.",
                                       heb_msg="חלק הזה של האתר מיועד למשתמשים אחרים")
        
        return role_check_wrapper
    return decorator_require_role


class FakeKey:
    def __init__(self) -> None:
        self.id = 0


class FakeUser:
    def __init__(self) -> None:
        self.key = FakeKey()


zero_user = FakeUser()


def get_user_availability(db_user_info, week_of_str):
    debug("getting user availability from DB...")

    query = datastore_client.query(kind="user_availability")
#    debug(f"Based on user id {db_user_info.key.id}")
    query.add_filter(filter=PropertyFilter("user_id", "=", db_user_info.key.id))
    query.add_filter(filter=PropertyFilter("week_of", "=", week_of_str))
    user_avail_info = query.fetch()
    for info in user_avail_info:
        # debug(f"Got back {info}")
        return info
    
    # if we got nothing, return a valid response anyway
    debug(f"Creating a new availability entry")
    key = datastore_client.key("user_availability")
    entity = datastore.Entity(key=key)
    # ths was a dormant bug, just found it when testing the scheduler mid-week when the coming week's setup hadn't yet been done
    if db_user_info == zero_user:
        new_availability = {"Sunday": [0, 0, 0], "Monday": [0, 0, 0], "Tuesday": [0, 0, 0],
                                 "Wednesday": [0, 0, 0], "Thursday": [0, 0, 0],
                                 "Friday": [0, 0, 1], "Saturday": [1, 1, 0]}
    else:
        new_availability = {
                        "translation": {"Sunday": [0, 0, 0], "Monday": [0, 0, 0], "Tuesday": [0, 0, 0],
                                 "Wednesday": [0, 0, 0], "Thursday": [0, 0, 0],
                                 "Friday": [0, 0, 0], "Saturday": [0, 0, 0]},
                        "review": {"Sunday": [0, 0, 0], "Monday": [0, 0, 0], "Tuesday": [0, 0, 0],
                                 "Wednesday": [0, 0, 0], "Thursday": [0, 0, 0],
                                 "Friday": [0, 0, 0], "Saturday": [0, 0, 0]}
        }

    entity.update({"user_id": db_user_info.key.id,
                   "week_of": week_of_str,
                   "available": new_availability}) 
    datastore_client.put(entity)
    entity = datastore_client.get(entity.key)
    return entity
    

def update_user_availability(db_user_info, week_of_str, availability):
    debug(f"update_user_availability for {db_user_info.key.id}, {week_of_str}")
    curr_availability = get_user_availability(db_user_info, week_of_str)
    debug(f"The new availability value is {availability}")
    curr_availability.update({"available": availability}) 
    datastore_client.put(curr_availability)
#    entity = datastore_client.get(entity.key)
    return curr_availability
