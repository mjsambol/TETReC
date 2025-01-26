from google.cloud import datastore
from pyluach import dates
from pyluach.utils import Transliteration

import os
from babel.dates import format_date
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
# if running on python 3.8 the above line needs to be changed to
# from backports.zoneinfo import ZoneInfo
from enum import Enum, auto

if __package__ is None or __package__ == '':
    from language_mappings import locales
else:
    from .language_mappings import locales

ARCHIVE_BASE = "https://storage.googleapis.com/tamtzit-archive/"
JERUSALEM_TZ = ZoneInfo("Asia/Jerusalem")

debug_state = os.getenv("FLASK_DEBUG") == "1"


def _set_debug(new_state):
    global debug_state
    if type(new_state) is bool:
        debug_state = new_state
    else:
        debug_state = type(new_state) is str and new_state.lower() in ['on', 'true', 'debug', "1"]
    return debug_state


def debug(stuff):
    if debug_state:
        now = datetime.now(tz=ZoneInfo("Asia/Jerusalem"))
        print(f"DEBUG: [{now.strftime('%d/%m/%Y %H:%M:%S')}] {stuff}")


def expand_lang_code(from_lang, to_lang='H'):
    if to_lang == 'H':
        if from_lang == '--':
            return 'עברית'
        if from_lang == 'H1':
            return 'עברית יומי'
        if from_lang == 'en':
            return 'אנגלית'
        if from_lang == 'fr':
            return 'צרפתית'
        if from_lang == 'YY':
            return 'נוער'
    if to_lang == 'E':
        if from_lang in ['--', 'H1']:
            return 'Hebrew'
        if from_lang == 'en':
            return 'English'
        if from_lang == 'fr':
            return 'French'
        if from_lang == 'YY':
            return "Youth"
    return '??'


class DraftStates(Enum):
    WRITING = auto()
    EDIT_READY = auto()
    EDIT_ONGOING = auto()
    EDIT_NEAR_DONE = auto()
    PUBLISH_READY = auto()
    PUBLISHED = auto()
    ADMIN_CLOSED = auto()


def compare_draft_state_lists(dict_of_states1, dict_of_states2):
    states_in_order = [DraftStates.PUBLISHED, DraftStates.PUBLISH_READY, DraftStates.EDIT_NEAR_DONE,
                       DraftStates.EDIT_ONGOING, DraftStates.EDIT_READY, DraftStates.WRITING]
    for state in states_in_order:
        if state in dict_of_states1:
            if state in dict_of_states2:
                return 0
            return -1
        if state in dict_of_states2:
            return 1
        

class DatastoreClientProxy:

    _proxy_instances_by_project = {}

    def __init__(self, project) -> None:
        self.client = datastore.Client(project=project)
        self.debug_mode = os.getenv("FLASK_DEBUG") == "1" and not os.getenv("FLASK_DEBUG_USE_PROD") == "1"

    @classmethod
    def get_instance(cls, project="tamtzit-hadashot"):
        if project not in cls._proxy_instances_by_project:
            cls._proxy_instances_by_project[project] = DatastoreClientProxy(project=project)
        return cls._proxy_instances_by_project[project]

    def key(self, name, value=None):
        if value:
            return self.client.key(("debug_" if self.debug_mode else "") + name, value)
        else:
            return self.client.key(("debug_" if self.debug_mode else "") + name)
        
    def put(self, entity):
        return self.client.put(entity)
    
    def get(self, key):
        return self.client.get(key)
    
    def delete(self, key):
        return self.client.delete(key)
    
    def query(self, kind):
        return self.client.query(kind=("debug_" if self.debug_mode else "") + kind)


@dataclass
class DateInfo:
    part_of_day: str
    day_of_week: str
    day_of_week_digit: int
    hebrew_dom: int
    hebrew_month: str
    hebrew_year: int
    secular_month: str
    secular_month_digit: int
    secular_dom: int
    secular_year: int
    day_of_war: int
    hebrew_dom_he: str
    hebrew_month_he: str
    hebrew_year_he: str
    motzei_shabbat_early: bool
    erev_shabbat: bool
    is_dst: bool   # indication of summer time when there is only one motzei Shabbat edition
    based_on_dt: datetime

    def __init__(self, dt: datetime, lang, part_of_day, motzei_shabbat_early, erev_shabbat, is_dst):
        oct6 = datetime(2023, 10, 6, tzinfo=ZoneInfo('Asia/Jerusalem'))
        heb_dt = dates.HebrewDate.from_pydate(dt)

        self.based_on_dt     = dt
        self.part_of_day     = part_of_day
        self.day_of_week     = format_date(dt, "EEEE", locale=locales[lang])  # dt.strftime('%A')
        self.day_of_week_digit = dt.isoweekday()  # Monday = 1, Sunday = 7
        if self.day_of_week_digit == 7:
            self.day_of_week_digit = 0   # make Sun-Sat 0-6
        self.secular_month   = format_date(dt, "MMMM", locale=locales[lang])
        self.secular_month_digit = dt.month
        self.secular_dom     = dt.day
        self.secular_year    = dt.year 
        self.hebrew_dom      = heb_dt.day
        self.hebrew_month    = heb_dt.month_name(transliteration=Transliteration.MODERN_ISRAELI)
        self.hebrew_year     = heb_dt.year
        self.day_of_war      = (dt - oct6).days
        self.hebrew_dom_he   = heb_dt.hebrew_day()
        self.hebrew_month_he = heb_dt.month_name(True)
        self.hebrew_year_he  = heb_dt.hebrew_year()
        self.erev_shabbat    = erev_shabbat
        self.motzei_shabbat_early = motzei_shabbat_early
        self.is_dst          = is_dst
