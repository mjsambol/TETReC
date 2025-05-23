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

from cryptography.fernet import Fernet
from datetime import datetime, timedelta
import json
from uuid import uuid4
from zoneinfo import ZoneInfo
from google.cloud import datastore

if __package__ is None or __package__ == '':
    # uses current directory visibility
    from common import DatastoreClientProxy, debug
else:
    from .common import debug, DatastoreClientProxy

class Cookies:

    ONE_DAY_SESSION = 'tamtzit_auth_session'
    ONE_WEEK_SESSION ='tamtzit_auth_weekly'
    COOKIE_USER_ID = "user_id"
    COOKIE_USER_NAME = "user_name"
    COOKIE_CERT = "birth_cert"
    

datastore_client = DatastoreClientProxy.get_instance()
app_crypto_key = None
today_crypto_noise = None

def get_app_key():
    global app_crypto_key

    if app_crypto_key:
        return app_crypto_key
    
    debug("Setting up app crypto key...")

    query = datastore_client.query(kind="crypto")
    crypto_info = query.fetch()
    for cinfo in crypto_info:
        app_crypto_key = cinfo["app_key"]

    if not app_crypto_key:
        debug("Crypto key not found in DB, creating a new one...")
        crypto_key = Fernet.generate_key()  # store in a secure location
        # PRINTING FOR DEMO PURPOSES ONLY, don't do this in production code
        debug("New Crypto Key:" + crypto_key.decode())
        # store it in the DB
        key = datastore_client.key("crypto")
        entity = datastore.Entity(key=key, exclude_from_indexes=["app_key"])
        entity.update({"app_key":crypto_key})
        datastore_client.put(entity)
        debug("New crypto key successfully stored in DB.")
        app_crypto_key = crypto_key
    
    return app_crypto_key

def daily_db_cleanup(now):
    
    debug("daily_db_cleanup() - removing old crypto_noise entries")
    valid_day_stamps = []
    for day_delta in range(7):
        valid_day = now - timedelta(days=day_delta)
        valid_day_stamps.append(valid_day.strftime('%Y.%m.%d'))
    debug(f"daily_db_cleanup(): valid days are {valid_day_stamps}")

    query = datastore_client.query(kind="crypto_noise")
    daily_noise_entries = query.fetch()
    for daily_noise_entry in daily_noise_entries:
        daily_noise = daily_noise_entry["daily_noise"]
        daily_noise_is_valid = False
        for option in valid_day_stamps:
            if option in daily_noise:
                daily_noise_is_valid = True
                break
        if not daily_noise_is_valid:
            datastore_client.delete(daily_noise_entry.key)

    debug("daily_db_cleanup() - removing old draft_backup entries")
    query2 = datastore_client.query(kind="draft_backup")
    draft_backups = query2.fetch()
    for dbkup in draft_backups:
        its_from = dbkup['backup_timestamp']
        debug(f"found a backup from {its_from}")
        if (now - its_from).days > 0 or (now - its_from).seconds > (60 * 60 * 10):
            debug("deleting it.")
            datastore_client.delete(dbkup.key)


def get_today_noise():
    global today_crypto_noise
    debug("get_today_noise() starting...")
    now = datetime.now(tz=ZoneInfo('UTC'))
    if today_crypto_noise and now.strftime('%Y.%m.%d') in today_crypto_noise:
        debug("get_today_noise() returning existing value")
        return today_crypto_noise

    debug("get_today_noise() - need to create a new value")
    key = datastore_client.key("crypto_noise")
    entity = datastore.Entity(key=key, exclude_from_indexes=["daily_noise"])
    today_crypto_noise = now.strftime('%Y.%m.%d') + str(uuid4())
    entity.update({"daily_noise":today_crypto_noise})
    datastore_client.put(entity)

    # since this process happens once a day, it's a good place to do some DB cleanup
    daily_db_cleanup(now)

    debug("get_today_noise(): returning")
    return today_crypto_noise

def make_daily_cookie(user_details):

    today_noise = get_today_noise()
    cookie_data = {Cookies.COOKIE_CERT: today_noise+user_details['name'],
                Cookies.COOKIE_USER_ID: user_details.key.id,
                Cookies.COOKIE_USER_NAME: user_details['name']}
    return make_cookie_from_dict(cookie_data)

def make_weekly_cookie(user_details):   
    # nothing different about it at this stage
    return make_daily_cookie(user_details)

def get_cookie_dict(request, cookie_name):
    cookie = request.cookies.get(cookie_name)
    if not cookie:
        return {}
    
    # this was very helpful documentation: https://stackoverflow.com/questions/2490334/simple-way-to-encode-a-string-according-to-a-password
    encryption_key = get_app_key()
    try:
        decrypted_cookie = Fernet(encryption_key).decrypt(cookie)  
    except:
        debug(f"Error decrypting cookie {cookie_name}")
        return {}
    
    return json.loads(decrypted_cookie)

def make_cookie_from_dict(session):
    # this was very helpful documentation: https://stackoverflow.com/questions/2490334/simple-way-to-encode-a-string-according-to-a-password
    encryption_key = get_app_key()
    encrypted_cookie = Fernet(encryption_key).encrypt(json.dumps(session).encode())  
    return encrypted_cookie

def user_data_from_req(request):
        return get_cookie_dict(request, Cookies.ONE_DAY_SESSION)

def cookie_get(request, cookie_name, key):
    session = get_cookie_dict(request, cookie_name)
    if key not in session:
        return None
    return session[key]
