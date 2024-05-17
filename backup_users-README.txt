cat backup_user_table-2024-05-16.json | jq -r '(.[0] | keys_unsorted) as $keys | $keys, map([.[ $keys[] ]])[] |@csv' > backup_user_table-2024-05-16.csv
