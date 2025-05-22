export PROJECT_ID=tamtzit-hadashot
export FLASK_APP=project
export FLASK_DEBUG=1
export CLOUDSDK_DEVAPPSERVER_PYTHON=/path/to/python
alias devappserver="python3 /path/to/google-cloud-sdk/bin/dev_appserver.py --runtime_python_path=/path/to/python /path/to/app.yaml"

# Tamtzit's key
export OPENAI_API_KEY="YOUR-KEY-HERE"
export ASYNC_PROCESSOR_URL="http://YOUR-IP-ADDRESS:PORT/items/"
export PYTHONPATH=/path/to/project
export MAILJET_KEY=''
export MAILJET_PWD=''
export EMAIL_SENDER_ADDR=''
export EMAIL_SENDER_NAME=''
export USER_SCHEDULING_PREFERENCES=''