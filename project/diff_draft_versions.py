from difflib import SequenceMatcher
import re
import sys
from collections import defaultdict
from .common import *
from .translation_utils import translate_text
from .language_mappings import sections

def parse_for_comparison(text):
    result = defaultdict(list)
    section = None
    current_entry = None
    for line in text:
        line = line.strip()
        if len(line.replace("•","").strip()) == 0:
#            print(f"skipping a blank line: {line}")
            current_entry = None
            continue
        # two consecutive lines not separated by a blank line will be considered the same entry
        if not re.match("^[•📌>]", line):  # it doesn't start with any prefix
            if current_entry:
                result[section][-1] = result[section][-1] + "\n" + line
 #               print("Appending this line to the previous one")
 #           else:
 #               print(f"skipping a no-prefix non-blank line: {line}")
        elif not line.startswith("•"):
            section = line  ## this should always get replaced, but just in case...
            for heb_section in sections['keys_from_Hebrew']:
                if heb_section in line:
                    section = heb_section
                    break
        else:
            current_entry = line
            result[section].append(current_entry)
    return result


def get_substantial_additions(parsed_heb_draft, parsed_backup):
    additions = defaultdict(list)

    for section in parsed_heb_draft:
        if not section in parsed_backup:
            debug(f"The section {section} is entirely missing from the backup")
            additions[section] = parsed_heb_draft[section]
            continue
        backup_section = parsed_backup[section]
        for bullet in parsed_heb_draft[section]:
            if len(bullet) < 5:
                continue
            best_fit = max([SequenceMatcher(None, backup_bullet, bullet).ratio() for backup_bullet in backup_section])
            if best_fit < 0.5:
#                print(f"More than half ({best_fit}) has been changed, let's consider it added to section {section}:")
#                print(bullet)
                additions[section].append(bullet)
    return additions


def get_pre_translation_backup(draft):
    # the FIRST (oldest) backup in the DB which is marked as "ok to translate"
    # represents the text when the author hit "ok to translate" - there is an auto backup at that point
    # and therefore it's the earliest text the translator could have worked from
    # we want to build a list of additions made since that point
    datastore_client = DatastoreClientProxy.get_instance()
    debug(f"get_pre_translation_backup: draft id is {draft.key.id}")
    backup_query = datastore_client.query(kind="draft_backup")
    backup_query.order = ["-backup_timestamp"]
    backups = backup_query.fetch()
    candidate = None
    for backup in backups:
        if backup["draft_id"] != draft.key.id:
            continue
        if not backup['ok_to_translate']:
            # we've gone too far - want the backup that's 1 younger than this
            return candidate
        candidate = backup
    return candidate


def get_translated_additions_since_ok_to_translate(current_hebrew_text, heb_text_used_for_translation, target_lang="en"):

    parsed_heb_draft = parse_for_comparison(current_hebrew_text.split('\n'))

    parsed_backup = parse_for_comparison(heb_text_used_for_translation.split('\n'))

    additions_by_section = get_substantial_additions(parsed_heb_draft, parsed_backup)
    debug(f"there were {len(additions_by_section)} sections with additions")
    translated_additions_by_section = defaultdict(list)

    for section_with_addition in additions_by_section:
        #print(f"Additions to section {section_with_addition}:\n{additions_by_section[section_with_addition]}")
        try:
            translated_section_name = sections[target_lang][sections['keys_from_Hebrew'][section_with_addition]]

            for addition in additions_by_section[section_with_addition]:
                translated = translate_text(addition, target_language_code=target_lang)
                translated_additions_by_section[translated_section_name].append(translated)
        except KeyError as ke:
            debug("ERROR from get_translated_additions_since_ok_to_translate(): KeyError: {ke}")

    debug(f"there are now {len(translated_additions_by_section)} translations of those")
    return (additions_by_section, translated_additions_by_section)


# if __name__ == "__main__":

#     datastore_client = DatastoreClientProxy.get_instance()

#     draft_query = datastore_client.query(kind="draft")
#     draft_query.order = ["-timestamp"]
#     # need to add indexes...
#     # draft_query.add_filter("ok_to_translate", "=", True)

#     drafts = draft_query.fetch()
#     for draft in drafts:
#         debug(f"Checking: {draft['translation_lang']}")
#         if draft['translation_lang'] == '--' and draft['ok_to_translate']:
#             break

#     debug(f"Processing a Hebrew draft with ID {draft.key.id} from {draft['timestamp']}")
#     heb_additions_by_section, translated_additions_by_section = get_translated_additions_since_ok_to_translate(draft, "en")
#     debug("Here are all the added bullets:")
#     for section in heb_additions_by_section:
#         debug(section + ":")
#         for addition in heb_additions_by_section[section]:
#             debug(addition)
#         translated_section_name = sections["en"][sections['keys_from_Hebrew'][section]]
#         debug(translated_section_name + ":")
#         for addition in translated_additions_by_section[translated_section_name]:
#             debug(addition)
#         debug("\n")
