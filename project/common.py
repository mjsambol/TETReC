import os
from google.cloud import datastore

def debug(stuff):
    if os.getenv("FLASK_DEBUG") == "1":
        print("DEBUG: " + stuff)

def expand_lang_code(from_lang, to_lang='H'):
    if to_lang == 'H':
        if from_lang == '--':
            return 'עברית'
        if from_lang == 'en':
            return 'אנגלית'
        if from_lang == 'fr':
            return 'צרפתית'
        if from_lang == 'YY':
            return 'נוער'
    if to_lang == 'E':
        if from_lang == '--':
            return 'Hebrew'
        if from_lang == 'en':
            return 'English'
        if from_lang == 'fr':
            return 'French'
        if from_lang == 'YY':
            return "Youth"
    return '??'

class DatastoreClientProxy:

    _proxy_instance = None

    def __init__(self) -> None:
        self.client = datastore.Client()
        self.debug_mode = os.getenv("FLASK_DEBUG") == "1" and not os.getenv("FLASK_DEBUG_USE_PROD") == "1"

    @classmethod
    def get_instance(cls):
        if not cls._proxy_instance:
            cls._proxy_instance = DatastoreClientProxy()
        return cls._proxy_instance    

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
        return self.client.query(kind =("debug_" if self.debug_mode else "") + kind)
