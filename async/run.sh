# NOTE this is only for one-time manual runs
#      use the systemd setup for continuous daemon processing

export PROJECT_ID=tamtzit-hadashot
export OPENAI_API_KEY="YOUR-KEY-HERE"
export SERVICE_ACCOUNT_JSON_LOC="/path/to/tamtzit-datastore-access-service-acct-key.json"
venv/bin/fastapi run async_txn.py --port 5081 &
