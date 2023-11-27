from cryptography.fernet import Fernet
from datetime import datetime, timedelta
import json
from uuid import uuid4
from zoneinfo import ZoneInfo
from google.cloud import datastore
from .common import debug, DatastoreClientProxy

class Cookies:

    ONE_DAY_SESSION = 'tamtzit_auth_session'
    ONE_WEEK_SESSION ='tamtzit_auth_weekly'
    USER_ID = "user_id"


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

    # let's also clean out any old ones that should no longer be valid
    debug("get_today_noise() - removing old crypto_noise entries")
    valid_day_stamps = []
    for day_delta in range(7):
        valid_day = now - timedelta(days=day_delta)
        valid_day_stamps.append(valid_day.strftime('%Y.%m.%d'))
    debug(f"get_today_noise: valid days are {valid_day_stamps}")

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

    debug("get_today_noise(): returning")
    return today_crypto_noise

def make_daily_cookie(user_details):

    today_noise = get_today_noise()
    cookie_data = {"birth_cert": today_noise+user_details['name'],
                Cookies.USER_ID: user_details.key.id,
                "user_name": user_details['name']}
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
    decrypted_cookie = Fernet(encryption_key).decrypt(cookie)  
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
