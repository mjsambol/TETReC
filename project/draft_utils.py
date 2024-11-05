from bs4 import BeautifulSoup
from google.cloud import datastore, storage
from google.cloud.datastore.query import PropertyFilter
import requests

from .common import ARCHIVE_BASE, compare_draft_state_lists, DateInfo, debug, DatastoreClientProxy, DraftStates
from .common import JERUSALEM_TZ
from .language_mappings import editions

import cachetools.func
from collections import defaultdict
from datetime import datetime
import re
from zoneinfo import ZoneInfo

DRAFT_TTL = 60 * 60 * 24

storage_client = storage.Client()
archive_bucket = storage_client.bucket("tamtzit-archive")

datastore_client = DatastoreClientProxy.get_instance()


def make_new_archive_entry(soup, next_entry_tag, draft, anchor, lang_code):
    new_entry = soup.new_tag("div")
    new_entry.attrs['id'] = anchor
    next_entry_tag.insert_after("\n\n", new_entry)

    table_tag = soup.new_tag("table")
    table_tag.attrs['border'] = '4'
    table_tag.attrs['width'] = '750px'
    table_tag.attrs['cellpadding'] = '20px'
    new_entry.append(table_tag)

    tr_tag = soup.new_tag("tr")
    table_tag.append(tr_tag)

    td_tag = soup.new_tag("td")
    td_tag.attrs['id'] = anchor + "-td"
    if lang_code == 'he':
        td_tag.attrs['dir'] = 'rtl'
        td_tag.attrs['align'] = 'right'
    tr_tag.append(td_tag)

    script_tag = soup.new_tag("script")
    script_tag.string = f"""document.getElementById('{anchor}-td').innerHTML = 
                makeWhatsappPreview(`{draft['hebrew_text'] if lang_code == 'he' else draft['translation_text']}`);"""
    td_tag.append(script_tag)

    other_langs_div = soup.new_tag("div")
    other_langs_div.attrs['id'] = anchor + "-other-langs"
    other_langs_div.attrs['style'] = "padding-top: 10px; font-weight: bold;"
    other_langs_div.string = "Other Languages:"
    new_entry.append("\n")
    new_entry.append(other_langs_div)

    section_divider_tag = soup.new_tag("hr")
    new_entry.insert_after(section_divider_tag)

    if lang_code != 'fr':
        link_to_fr = soup.new_tag("a")
        link_to_fr.attrs['href'] = f'{ARCHIVE_BASE}archive-fr.html#{anchor}'
        link_to_fr.attrs['style'] = "padding-left: 20px;"
        link_to_fr.string = 'French'
        other_langs_div.append(link_to_fr)

    if lang_code != 'en':
        link_to_en = soup.new_tag("a")
        link_to_en.attrs['href'] = f'{ARCHIVE_BASE}archive-en.html#{anchor}'
        link_to_en.attrs['style'] = "padding-left: 20px;"
        link_to_en.string = 'English'
        other_langs_div.append(link_to_en)

    if lang_code != 'he':
        link_to_he = soup.new_tag("a")
        link_to_he.attrs['href'] = f'{ARCHIVE_BASE}archive-he.html#{anchor}'
        link_to_he.attrs['style'] = "padding-left: 20px;"
        link_to_he.string = 'Hebrew'
        other_langs_div.append(link_to_he)


def get_latest_day_worth_of_editions():
    """This method is used from two locations:
    nightly_archive_cleanup() - which is invoked only by a cron job
    and 
    start_daily_summary() which is a route method, called by the hebrew.html page on submission
    """
    latest_drafts, _ = fetch_drafts()
    yesterdays_editions = defaultdict(dict)
    for draft in latest_drafts:
        draft_lang = 'he' if draft['translation_lang'] == '--' else draft['translation_lang']
        draft_time_of_day = get_edition_name_from_text(draft)
        debug(f"GLDWOE: Checking latest {draft_lang} draft ({draft_time_of_day}) - is this most mature for this lang at this time of day? {draft['states']}")
        if draft_time_of_day not in yesterdays_editions[draft_lang]:
            yesterdays_editions[draft_lang][draft_time_of_day] = draft
            debug(f"GLDWOE: added {draft_time_of_day} to yesterdays_Editions for lang {draft_lang}")            
        else:
            draft_maturity = compare_draft_state_lists(draft, yesterdays_editions[draft_lang][draft_time_of_day])
            if draft_maturity == -1:
                yesterdays_editions[draft_lang][draft_time_of_day] = draft
                debug(f"GLDWOE: Yes, this is the most mature draft found so far.")
            else:
                debug("GLDWOE: No, this edition is not newer.")
                
    return yesterdays_editions


def get_more_mature_draft(draft1, draft2):
    draft_maturity = compare_draft_state_lists(draft1['states'], draft2['states'])
    if draft_maturity == 1:
        return draft2
    return draft1  # we have to return something when they're equal so arbitrarily going with the first one
    

def get_edition_name_from_text(edition, as_english_always=True):
    lang = edition['translation_lang']
    text = edition['hebrew_text']
    debug(f"g_e_n_f_t: lang={lang}")
    m = re.search("^\*?מהדורת ([א-ת]+),", text, re.MULTILINE)   # noqa - the pattern works
    # The pattern WON'T match on the daily summary!
    if m:
        debug(f"g_e_n_f_t found {m.group(1)}, localizing...")
        edition_index = editions['he'].index(m.group(1))
        if as_english_always:
            return editions['en'][edition_index]
        if lang == '--':
            return m.group(1)
        return editions[lang][edition_index]
    else:
        m = re.search("^\*?מהדורה יומית", text, re.MULTILINE)   # noqa
        if m:
            debug("g_e_n_f_t found daily summary edition, localizing...")
            if as_english_always:
                return "Heb Daily Summary"
            else:
                return "מהדורה יומית"
    debug(f"g_e_n_f_t: lang={lang}, can't find edition name, returning UNKNOWN, text was: \n\n{text}\n\n")
    return "UNKNOWN"


# this method is used to build a list of recent translations for the list which is shown on the 
# input.html page, the main page where translators start a new draft
def fetch_drafts(query_order="-timestamp"):
    query = datastore_client.query(kind="draft")
    query.order = [query_order]

    drafts = query.fetch()

    now = datetime.now(tz=ZoneInfo('UTC'))
    drafts_local_timestamps = {}
    drafts_to_return = []

    for draft in drafts:
        draft_start_ts = draft['timestamp']
        if (now - draft_start_ts).days > 0 or (now - draft_start_ts).seconds > DRAFT_TTL:
            datastore_client.delete(draft.key)
            # also delete all the history of edits to that draft
            query2 = datastore_client.query(kind="draft_backup")
            query2.add_filter(filter=PropertyFilter("draft_id", "=", draft.key.id))
            draft_backups = query2.fetch()
            for dbkup in draft_backups:
                debug("found a backup, deleting it")
                datastore_client.delete(dbkup.key)
        else:
            draft_last_change_ts = draft['last_edit']
            drafts_local_timestamps[draft_start_ts] = \
                (draft_start_ts.astimezone(JERUSALEM_TZ), draft_last_change_ts.astimezone(JERUSALEM_TZ))
            drafts_to_return.append(draft)
            
    return drafts_to_return, drafts_local_timestamps
    

def create_draft(heb_text, user_info, translation_text='', translation_lang='en', translation_engine='Google', heb_draft_id=None):
    """Create a new entry in the Datastore, save the original text and, optionally, the translation,
    and return the new key and timestamp"""

    if len(heb_text) > 0 and heb_draft_id is None:
        debug("create_draft() ERROR: received heb_text but no heb_draft_id")
        raise ValueError("No draft ID though text is present")

    key = datastore_client.key("draft")
    draft_timestamp = datetime.now(tz=ZoneInfo('Asia/Jerusalem'))
    entity = datastore.Entity(key=key, exclude_from_indexes=("hebrew_text", "translation_text"))
    entity.update({"hebrew_text": heb_text, "heb_draft_id": heb_draft_id, 
                   "translation_text": translation_text, "translation_lang": translation_lang,
                   "translation_engine": translation_engine,
                   "timestamp": draft_timestamp, "last_edit": draft_timestamp, 
                   "is_finished": False, "ok_to_translate": False, "created_by": user_info.key.id,
                   "states": [{"state": DraftStates.WRITING.name, "at": draft_timestamp.strftime('%Y%m%d-%H%M%S'),
                              "by": user_info["name"], "by_heb": user_info["name_hebrew"]}]}) 
    datastore_client.put(entity)
    entity = datastore_client.get(entity.key)
    return entity.key


def create_draft_history(draft):
    key = datastore_client.key("draft_backup")
    entity = datastore.Entity(key=key, exclude_from_indexes=("hebrew_text", "translation_text"))
    entity.update({"draft_id": draft.key.id, "hebrew_text": draft["hebrew_text"],
                   "translation_text": draft["translation_text"],
                   "translation_lang": draft["translation_lang"], "draft_timestamp": draft["timestamp"],
                   "last_edit": draft["last_edit"],
                   "is_finished": draft["is_finished"], "ok_to_translate": draft["ok_to_translate"],
                   "created_by": draft["created_by"],
                   "states": draft["states"],
                   "backup_timestamp": datetime.now(tz=ZoneInfo('Asia/Jerusalem'))})
    datastore_client.put(entity)
    entity = datastore_client.get(entity.key)
    return entity.key


def store_draft_backup(draft, force_backup=False):
    debug("checking whether to save a draft backup...")
    prev_backup_time = 0
    query2 = datastore_client.query(kind="draft_backup")
    query2.order = ["-backup_timestamp"]
    # query2.add_filter("draft_id", "=", draft.key.id)
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
        debug(f'''draft last edit is {draft["last_edit"]} so the backup is 
                {draft["last_edit"] - prev_backup_time} 
                which is {(draft["last_edit"] - prev_backup_time).seconds} seconds old''')
    if force_backup or prev_backup_time == 0 or (draft["last_edit"] - prev_backup_time).seconds > 90:
        debug("creating a draft backup")
        create_draft_history(draft)


def update_translation_draft(draft_key, translated_text, user_info, is_finished=False):
    draft = datastore_client.get(draft_key)
    draft.update({"translation_text": translated_text})
    draft.update({"is_finished": is_finished})
    edit_timestamp = datetime.now(tz=ZoneInfo('Asia/Jerusalem'))
    draft.update({"last_edit": edit_timestamp}) 
    prev_states = draft["states"]
    # this method is specific to translation and the only states the tool supports right now for translation
    # are writing and publish_ready. Later it will be good to add additional states, at least edit_ready and published
    if is_finished and DraftStates.PUBLISH_READY.name not in [states_entry["state"] for states_entry in prev_states]:
        prev_states.append({"state": DraftStates.PUBLISH_READY.name, "at": edit_timestamp.strftime('%Y%m%d-%H%M%S'),
                            "by": user_info["name"], "by_heb": user_info["name_hebrew"]})

    datastore_client.put(draft)

    # also store history in case of dramatic failure
    store_draft_backup(draft)

    if is_finished:
        update_archive(draft)


def update_hebrew_draft(draft_key, hebrew_text, user_info, is_finished=False, ok_to_translate=False):
    draft = datastore_client.get(draft_key)
    draft.update({"hebrew_text": hebrew_text})
    draft.update({"is_finished": is_finished})
    if ok_to_translate:  
        # we don't want to ever change it back (on this draft) once it's set to true
        draft.update({"ok_to_translate": True})
    edit_timestamp = datetime.now(tz=ZoneInfo('Asia/Jerusalem'))
    draft.update({"last_edit": edit_timestamp}) 
    # I don't know why the below line was here, whether it was ever necessary,
    # but now it's problematic with the daily_summary flow
    # draft.update({"translation_lang": '--'})
    prev_states = draft["states"]

    if ok_to_translate and DraftStates.EDIT_READY.name not in [states_entry["state"] for states_entry in prev_states]:
        prev_states.append({"state": DraftStates.EDIT_READY.name, "at": edit_timestamp.strftime('%Y%m%d-%H%M%S'),
                            "by": user_info["name"], "by_heb": user_info["name_hebrew"]})
    
    if "editor" in user_info["role"]:
        if DraftStates.EDIT_ONGOING.name not in [states_entry["state"] for states_entry in prev_states]:
            prev_states.append({"state": DraftStates.EDIT_ONGOING.name, "at": edit_timestamp.strftime('%Y%m%d-%H%M%S'),
                                "by": user_info["name"], "by_heb": user_info["name_hebrew"]})

        # has the bottom 20% of text changed from what it was originally?
        bottom_20_percent_changed = do_edits_reach_last_two_sections(draft)

        if (bottom_20_percent_changed and
                DraftStates.EDIT_NEAR_DONE.name not in [states_entry["state"] for states_entry in prev_states]):
            prev_states.append({"state": DraftStates.EDIT_NEAR_DONE.name,
                                "at": edit_timestamp.strftime('%Y%m%d-%H%M%S'),
                                "by": user_info["name"], "by_heb": user_info["name_hebrew"]})
        
    if is_finished and DraftStates.PUBLISH_READY.name not in [states_entry["state"] for states_entry in prev_states]:
        prev_states.append({"state": DraftStates.PUBLISH_READY.name, "at": edit_timestamp.strftime('%Y%m%d-%H%M%S'),
                            "by": user_info["name"], "by_heb": user_info["name_hebrew"]})

    datastore_client.put(draft)

    # also store history in case of dramatic failure
    # and for reasons related to applying deltas in translation, we need to force save this as a backup
    store_draft_backup(draft, force_backup=ok_to_translate)

    if is_finished:
        update_archive(draft)


@cachetools.func.ttl_cache(ttl=600)
def cache_heb_draft_text_before_edits(draft_id):
    query2 = datastore_client.query(kind="draft_backup")
    query2.order = ["-backup_timestamp"]
    # query2.add_filter("draft_id", "=", draft.key.id)
    draft_backups = query2.fetch()
    for dbkup in draft_backups:
        # this query says: give me the last backup *before* the text went into Edit mode
        if (dbkup["draft_id"] == draft_id and
                DraftStates.EDIT_ONGOING.name not in [states_entry["state"] for states_entry in dbkup["states"]]):
            return dbkup
    # should not happen but could: admin user creates a draft and this method is called on the first attempt to save
    return None


def do_edits_reach_last_two_sections(draft):
    # be careful - we can't actually check against the 20% end of the string
    # because the changes prior to it change where the last 20% starts!
    # so instead we have to find the 2nd to last section heading in the original text,
    # find that same heading in the new text, and see if there
    # are changes from there onward. If that heading isn't found in the new text, the answer is yes.
    # first challenge - get SHIRA'S original version of the Hebrew text currently being changed
    current_text = draft["hebrew_text"]
    last_backup_before_editing = cache_heb_draft_text_before_edits(draft.key.id)
    if not last_backup_before_editing:
        return False
    text_at_ready_to_edit = last_backup_before_editing["hebrew_text"]

    orig_last_heading = text_at_ready_to_edit.rfind("📌")
    orig_second_last_heading = text_at_ready_to_edit.rfind("📌", 0, orig_last_heading)
    orig_footer_start_pos = text_at_ready_to_edit.find("•   •   •")
    orig_last_chunk = text_at_ready_to_edit[orig_second_last_heading:orig_footer_start_pos]
    curr_last_heading = current_text.rfind("📌")
    curr_second_last_heading = current_text.rfind("📌", 0, curr_last_heading)
    curr_footer_start_pos = text_at_ready_to_edit.find("•   •   •")
    curr_last_chunk = current_text[curr_second_last_heading:curr_footer_start_pos]
    # debug("Checking whether edits have reached the last section. Originally it was:")
    # debug(orig_last_chunk)
    # debug("Now the last section is:")
    # debug(curr_last_chunk)
    return curr_last_chunk != orig_last_chunk


############################################
# Notes on use of GCP Cloud Storage (GCS)
#   
# For downloading a file:
# https://github.com/googleapis/python-storage/blob/main/samples/snippets/storage_download_file.py
# 
# For uploading a file:
# https://github.com/googleapis/python-storage/blob/main/samples/snippets/storage_upload_file.py
# or to upload from memory:
# https://github.com/googleapis/python-storage/blob/main/samples/snippets/storage_upload_from_memory.py
# or from a stream:
# https://github.com/googleapis/python-storage/blob/main/samples/snippets/storage_upload_from_stream.py
# 
def update_archive(draft):
    debug("updating archive...")
    lang_code = 'he' if draft["translation_lang"] == '--' else draft["translation_lang"]
    if lang_code == 'YY':
        return  # we're not archiving those editions as they're just a subset of the regular Hebrew content
    
    date_info = make_date_info(datetime.now(JERUSALEM_TZ), 'en')  # Forced to EN so that we get English anchor names
    prev_archive = requests.get(f"{ARCHIVE_BASE}archive-{lang_code}.html").text

    soup = BeautifulSoup(prev_archive, "html.parser")
    next_entry_tag = soup.find(id='next-entry')

    if not next_entry_tag:
        print(f"ERROR: update_archive can't find the next-entry tag for language {lang_code}, returning.")
        return
        
    anchor = draft['timestamp'].astimezone(JERUSALEM_TZ).strftime('%Y-%m-%d') + '-' + date_info.part_of_day

    make_new_archive_entry(soup, next_entry_tag, draft, anchor, lang_code)

    upload_to_cloud_storage(f"archive-{lang_code}.html", str(soup))


def upload_to_cloud_storage(file_name, text_content):
    blob = archive_bucket.blob(file_name)
    blob.upload_from_string(text_content)
    blob.content_type = "text/html; charset=utf-8"
    blob.patch()
    debug("DONE uploading new archive")


def make_date_info(dt, lang):
    dt_edition = editions[lang][2]
    if 0 <= dt.hour < 12:
        dt_edition = editions[lang][0]
    elif 12 <= dt.hour < 18:
        dt_edition = editions[lang][1]

    is_summer_daylight_savings_time = bool(datetime.now(tz=ZoneInfo("Asia/Jerusalem")).dst())

    # locale.setlocale(locale.LC_TIME, locales[lang])

    return DateInfo(dt, lang, part_of_day=dt_edition, 
                    motzei_shabbat_early=((not is_summer_daylight_savings_time) and
                                          dt.isoweekday() == 6 and dt.hour < 19),
                    erev_shabbat=(dt.isoweekday() == 5 and dt.hour >= 12),
                    is_dst=is_summer_daylight_savings_time)
