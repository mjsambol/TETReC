from project.common import *
import json

datastore_client = DatastoreClientProxy.get_instance()

query = datastore_client.query(kind="user")
users = query.fetch()

all_users = []
for user in users:
    user_as_json = {
        "key.id": user.key.id
    }
    for attr in ['name', 'name_hebrew', 'email', 'phone', 'role']:
        if attr in user:
            user_as_json[attr] = user[attr]
    all_users.append(user_as_json)

as_text = json.dumps(all_users, ensure_ascii=False)
as_text = as_text.replace("}, {", "},\n{")
print(as_text)
