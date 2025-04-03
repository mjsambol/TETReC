from fastapi import FastAPI
from common import DatastoreClientProxy
from concurrent.futures import ThreadPoolExecutor
from translation_utils import openai_translate, strip_header_and_footer
from datetime import datetime
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
import os
# if running on python 3.8 the above line needs to be changed to
# from backports.zoneinfo import ZoneInfo

app = FastAPI()

project_id = os.getenv("PROJECT_ID")
service_account_json = os.getenv("SERVICE_ACCOUNT_JSON_LOC")

if not project_id or not service_account_json or not os.path.isfile(service_account_json):
    print("Environment variables PROJECT_ID and SERVICE_ACCOUNT_JSON_LOC must be defined.")
    exit(1)

credentials = service_account.Credentials.from_service_account_file(service_account_json)

datastore_client = DatastoreClientProxy.get_instance(project=project_id, credentials=credentials)
# more relevant reading about authentication with Service Accounts:
# https://googleapis.dev/python/google-api-core/latest/auth.html
# https://googleapis.dev/python/google-auth/latest/user-guide.html#service-account-private-key-files
# https://cloud.google.com/iam/docs/service-accounts-create

executor = ThreadPoolExecutor(3)

@app.get("/")
def read_root():
    return {"Hello": "World"}

def call_openai(heb_text, target_lang, async_job):
    print("Calling OpenAI...")
    tx_result = openai_translate(heb_text, target_lang)
    print("OpenAI returned, writing to DB")

    async_job.update({"translation_timestamp": datetime.now(tz=ZoneInfo('Asia/Jerusalem')),
                   "translation_result": tx_result, "result_code": "Success"})
    datastore_client.put(async_job)


@app.get("/items/{item_id}")
def read_item(item_id: int):
    # query = datastore_client.query(kind="async_job")
    # query.add_filter(filter=PropertyFilter("heb_author_id", "=", item_id))
    # jobs = query.fetch()
    # my_job = None
    # for job in jobs:
    #     print(f'got job: {job} with id {job.key.id} ')
    #     if job.key.id == item_id:
    #         my_job = job
    #         break

    my_job = datastore_client.get(datastore_client.key("async_job", item_id))

    if my_job:
        translation_target_lang = my_job["translation_lang"]
        heb_text = my_job["heb_text"]
        heb_text = strip_header_and_footer(heb_text, translation_target_lang)
        executor.submit(call_openai, heb_text, translation_target_lang, my_job)

        return {"item_id": item_id, "heb_draft_id": my_job["heb_draft_id"]}
    else:
        return {"Error": "No data returned from DataStore"}
