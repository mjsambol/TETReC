##################################################################################
#
#    Team Text Editing, Translation and Review Coordination tool
#    Copyright (C) 2023-2025, Moshe Sambol, https://github.com/mjsambol
#
#    Originally created for the Tamtzit Hachadashot / News In Brief project
#    of the Lokhim Ahrayut non-profit organization
#    Published in English as "Israel News Highlights"
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
##################################################################################

from datetime import datetime, timedelta
import itertools
import json
import os
import sys
from typing import List
from zoneinfo import ZoneInfo

from babel.dates import format_date
from google.cloud import datastore
from google.cloud.datastore.query import PropertyFilter

if __package__ is None or __package__ == '':
    # uses current directory visibility
    from common import DatastoreClientProxy
    from auth_utils import update_user_availability, zero_user
else:
    # uses current package visibility
    from .common import DatastoreClientProxy
    from .auth_utils import update_user_availability, zero_user


class Person:
    def __init__(self, name) -> None:
        self.name = name
        self.db_details = None
        self.offered_translate = None  # once set, this dict is static. The format is {"Sunday":[0,1,1], "Monday":[1,0,0]}
        self.offered_review = None  # once set, this dict is static. The format is {"Sunday":[0,1,1], "Monday":[1,0,0]}
        self.days_offered = 0
        self.total_offered = 0
        self.assigned = []
        self.reviewing = []

    def set_offered(self, offer_dict, for_function):
        if for_function == 'translation':
            self.offered_translate = offer_dict
        elif for_function == 'review':
            self.offered_review = offer_dict

        for day_offer_name in offer_dict:
            if len(offer_dict[day_offer_name]) < 3:
                # pad out any partial arrays so we don't have trouble with them later
                if for_function == 'translation':
                    self.offered_translate[day_offer_name] = offer_dict[day_offer_name] + [0] * (3 - len(offer_dict[day_offer_name]))
                elif for_function == 'review':
                    self.offered_review[day_offer_name] = offer_dict[day_offer_name] + [0] * (3 - len(offer_dict[day_offer_name]))
        for day_offer in offer_dict.values():
            self.days_offered += any(day_offer)
            self.total_offered += sum([int(x) for x in day_offer])


class Edition:
    def __init__(self, day_name: str, name: str) -> None:
        self.day_name: str = day_name
        self.name: str = name
        self.offered_translate: list[Person] = []  # original volunteers - doesn't change
        self.offered_review: list[Person] = []  # original volunteers - doesn't change
        self.t_candidates: list[Person] = []  # grows and shrinks due to the algorithm
        self.r_candidates: list[Person] = []  # grows and shrinks due to the algorithm
        self.translator: Person | None = None
        self.reviewer: Person | None = None

    def set_translator(self, translator: Person):
        self.translator = translator
        translator.assigned.append(self)

    def add_offer(self, volunteer: Person, for_function: str):
        if for_function == "translation":
            self.offered_translate.append(volunteer)
            self.t_candidates.append(volunteer)
            self.r_candidates.append(volunteer)
        elif for_function == 'review':
            self.offered_review.append(volunteer)
            self.r_candidates.append(volunteer)

    def set_reviewer(self, reviewer: Person):
        self.reviewer = reviewer
        reviewer.reviewing.append(self)


class Day:
    def __init__(self, name: str) -> None:
        self.name = name
        self.morning = Edition(self.name, "Morning")
        self.afternoon = Edition(self.name, "Afternoon")
        self.evening = Edition(self.name, "Evening")


def remove_same_day_candidacy(ed, all_editions):
    print(f"remove_same_day_candidacy: {ed.day_name}, {ed.reviewer.name}")
    other_editions_same_day = [d for d in all_editions if d.day_name == ed.day_name]
    print(f"checking {len(other_editions_same_day)} other days")
    for oed in other_editions_same_day:
        # for some reason the two objects are not evaluating as equal so I'm doing this in a bit of an ugly way
        oed.r_candidates = [rc for rc in oed.r_candidates if rc.name != ed.reviewer.name]


def safe_get_name(input_var):
    if not input_var:
        return "---"
    return input_var.name


class Schedule:
    def __init__(self, lang) -> None:
        self.lang = lang
        self.cached_users = {}
        self.max_assignments_per_volunteer = 3  # hopefully. This may get raised as we go, if needed
        self.week: dict[str, Day] = \
            {n: Day(n) for n in ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]}
        # There is no good reason to stay with first names only. If the team grows, this can be changed
        # and the only other changes needed are in get_input_from_datastore where we match details by first name,
        # and in tx_schedule.html where colors are assigned to each person
        self.team: dict[str, Person] = \
            {n: Person(n) for n in ["Anne", "Ayelet", "Gabriela", "Karen", "Malke", "Moshe", "Rebecca", "Rochel"]}

        self.no_edition_times = \
            [self.week["Friday"].evening, self.week["Saturday"].morning, self.week["Saturday"].afternoon]
        self.datastore_client = DatastoreClientProxy.get_instance()


    def cache_user_info(self):
        query = self.datastore_client.query(kind="user")
        users = query.fetch()
        for user in users:
            if ((self.lang == 'he' and "Hebrew" in user["role"]) or "translator_" + self.lang in user["role"]
                or "editor_" + self.lang in user["role"]):
                self.cached_users[user.key.id] = user
                self.cached_users[user["name"]] = user
                user_fname = user['name'].split(" ")[0]
                if user_fname not in self.team:
                    self.team[user_fname] = Person(user_fname)
                self.team[user_fname].db_details = user

    def parse_file_input(self, fname):
        # this method was only used during development.
        with open(fname) as in_file:
            volunteer_input = json.load(in_file)
        for volunteer_entry in volunteer_input:
            volunteer = self.team[volunteer_entry["name"]]
            volunteer.set_offered(volunteer_entry["offer"], "translation")
            print(f'{volunteer.name} offered {volunteer.total_offered} options across {volunteer.days_offered} days')
            for day_name in self.week:
                day = self.week[day_name]
                day_offer = volunteer_entry["offer"][day_name]
                if day_offer[0]:
                    day.morning.add_offer(volunteer, "translation")
                if day_offer[1]:
                    day.afternoon.add_offer(volunteer, "translation")
                if day_offer[2]:
                    day.evening.add_offer(volunteer, "translation")

    def get_input_from_datastore(self, week_from_str_param):
        query = self.datastore_client.query(kind="user_availability")
        print("Fetching availability of users for week " + week_from_str_param)
        query.add_filter(filter=PropertyFilter("week_of", "=", week_from_str_param))
        user_avail_info = query.fetch()
        for info in user_avail_info:
            if info['user_id'] == 0:
                continue

            if info['user_id'] not in self.cached_users:
                # self.cached_users is people with role translator_XX or editor_XX for the current language
                continue

            user_details = self.cached_users[info['user_id']]
            print(f"Processing availability for {info['user_id']} = {user_details['name']}")

            print(f"Availability is {info['available']}")
            info['available'] = info['available'].replace("'", '"')

            user_fname = user_details['name'].split(" ")[0]
            if user_fname not in self.team:
                # someone got added to the DB but not recognized here yet
                self.team[user_fname] = Person(user_fname)
                self.team[user_fname].db_details = user_details

            volunteer = self.team[user_fname]
            # backward compatibility check
            if 'translation' not in info['available']:
                info['available']['translation'] = dict(info['available'])
                info['available']['review'] = {}
            if type(info['available']) == str:
                as_dict = json.loads(info['available'])
                info['available'] = as_dict

            for func in ['translation', 'review']:
                volunteer.set_offered(info['available'][func], func)
            print(f'{volunteer.name} offered {volunteer.total_offered} options across {volunteer.days_offered} days:')
            print(f'{info["available"]}')

            for day_name in self.week:
                day = self.week[day_name]

                for func in [(volunteer.offered_translate, "translation"), (volunteer.offered_review, "review")]:
                    if day_name not in func[0]:
                        # could happen with backward-compatible patched data
                        continue
                    day_offer = func[0][day_name]
                    if not type(day_offer[0]) == int:
                        day_offer = [int(x) for x in day_offer]
                    print(f"{day_name} day_offer from {volunteer.name} is {day_offer}")                        
                    if day_offer[0]:
                        print("set morning")
                        day.morning.add_offer(volunteer, func[1])
                    if day_offer[1]:
                        print("set afternoon")
                        day.afternoon.add_offer(volunteer, func[1])
                    if day_offer[2]:
                        print("set evening")
                        day.evening.add_offer(volunteer, func[1])

    def confirm_proceed_with_available_data(self, non_interactive_mode_p):
        for team_member_name in self.team:
            if not self.team[team_member_name].offered_translate and not self.team[team_member_name].offered_review:
                print(f"No availability yet for {team_member_name}")
        if not non_interactive_mode_p:
            proceed = input("Do you want to proceed with creating the schedule? [y/n] ")
            if proceed != 'y':
                return False
        return True

    def check_rule_1(self):
        # Rule 1: For a slot that has only one person available, assign them
        print("Checking rule 1...")
        for day in self.week.values():
            print(f"Checking {day.name}")
            day = self.week[day.name]
            all_editions = [day.morning, day.afternoon, day.evening]
            for edition in all_editions:
                if edition.translator:
                    continue
                if edition in self.no_edition_times:
                    continue

                print(f"checking {edition.name} - {len(edition.offered_translate)} translation offers: {[p.name for p in edition.offered_translate]}, ")
                print(f" with {len(edition.t_candidates)} curr candidates - {[p.name for p in edition.t_candidates]}")
                if len(edition.t_candidates) == 1:
                    # and also tell the translator he's been assigned, so that he can keep track of how many assignments
                    edition.set_translator(edition.t_candidates[0])
                    print(f"Rule 1: {edition.translator.name} will translate on {day.name} {edition.name}")

    def check_rule_2(self):
        print("Checking rule 2...")
        rule_applied = False
        # Rule 2: For each day, for each person who already has an assignment that day,
        # remove them as candidates for other slots that day,
        # unless they are the only volunteer in the second slot as well,
        # or unless they are one of two, both of whom have one of the day's other slots  -- @TODO not yet being checked

        for day in self.week.values():
            all_editions = [day.morning, day.afternoon, day.evening]
            for edition in all_editions:
                if edition.translator:
                    other_editions = [e for e in all_editions if e != edition]
                    for other_edition in other_editions:
                        if other_edition.translator:
                            continue
                        if edition.translator in other_edition.t_candidates and len(other_edition.t_candidates) > 1:
                            other_edition.t_candidates.remove(edition.translator)
                            print(f"Rule 2: removing {edition.translator.name} from {day.name} {other_edition.name}")
                            rule_applied = True
        print("Done with rule 2")
        return rule_applied

    def check_rule_3(self):
        # Rule 3: Once a person has three assigned slots, remove them from other slots across the week
        # unless they are the only one left in that slot (in which case they're already assigned to there),
        # or unless all volunteers for that slot have the same number of other assignments
        print("Checking rule 3...")
        rule_applied = False

        for day in self.week.values():
            for edition in [day.morning, day.afternoon, day.evening]:
                if edition.translator:
                    continue

                to_remove = []
                for volunteer in edition.t_candidates:
                    if len(volunteer.assigned) >= 3:
                        to_remove.append(volunteer)
                # sort to_remove by number of assignments, high to low
                to_remove.sort(reverse=True, key=lambda x: len(x.assigned))

                # remove volunteers from edition.t_candidates working through the list of to_remove
                # until all those left have the same number of assignments as the last in the list
                while len(to_remove) > 0 and len(to_remove[0].assigned) > len(to_remove[-1].assigned):
                    print(f"removing {to_remove[0].name} as candidate for {day.name} {edition.name} ")
                    print(f"  - already has {len(to_remove[0].assigned)} assignments")
                    edition.t_candidates.remove(to_remove[0])
                    to_remove.remove(to_remove[0])
                    rule_applied = True
        print("done with rule 3")
        return rule_applied

    def offered_and_available(self, per: Person) -> List[Edition]:
        """Used extensively by Rule 5"""
        offered_and_available_list = []
        print(f"oaa: {per.name}: {per.offered_translate}")
        if not per.offered_translate:
            return []
        for offer_day_name in per.offered_translate:
            print(f"oaa: {per.name}: checking {offer_day_name}")
            day_data = self.week[offer_day_name]
            offer_data = [int(x) for x in per.offered_translate[offer_day_name]]
            if offer_data[0] == 1 and not day_data.morning.translator and per in day_data.morning.t_candidates:
                print(f"oaa: {per.name}: adding morning")
                offered_and_available_list.append(day_data.morning)
            if offer_data[1] == 1 and not day_data.afternoon.translator and per in day_data.afternoon.t_candidates:
                print(f"oaa: {per.name}: adding afternoon")
                offered_and_available_list.append(day_data.afternoon)
            if offer_data[2] == 1 and not day_data.evening.translator and per in day_data.evening.t_candidates:
                print(f"oaa: {per.name}: adding evening")
                offered_and_available_list.append(day_data.evening)
        return offered_and_available_list

    def check_rule_5(self):
        # rather than rule 5 as written in the doc, I'm trying what looks like a simpler approach:
        # for each volunteer, calculate the number of slots which they have volunteered for,
        # and which are still available. Call this num_offered_and_available
        # for anyone where that number is zero, remove them from the list, there's nothing I can assign them
        # otherwise, sort the list of volunteers by primary criteria num_offered_and_available (ascending)
        # and secondary criteria num_assignments (ascending)
        # take the first person with the lowest of those two, give them an assignment,
        # recalculate their num_offered_and_available, repeat the outer loop from the top

        print("Starting rule 5...")
        offered_and_available_cache = {p: len(self.offered_and_available(p)) for p in self.team.values()}
        print(offered_and_available_cache)

        available_volunteers = [p for p in self.team.values()
                                if len(p.assigned) < self.max_assignments_per_volunteer
                                and offered_and_available_cache[p] > 0]
        print(f"There are {len(available_volunteers)} volunteers available: {available_volunteers}")
        if len(available_volunteers) == 0:
            return False

        available_volunteers_by_priority = (
            sorted(available_volunteers,
                   # for those who volunteered 2 or fewer slots, make sure they get them, and no one else
                   # gets an assignment until these have been given their 2
                   # for those who volunteered more than 2 slots, prioritize by whoever has fewest assignments,
                   # second criteria whoever has least remaining availability
                   key=lambda x: ((len(x.assigned) + offered_and_available_cache[x])
                                  if len(x.assigned) + offered_and_available_cache[x] <= 2 else 10,
                                  len(x.assigned),
                                  offered_and_available_cache[x])))

        print("Rule 5: Available volunteers by assignments and num volunteered days:")

        for av in available_volunteers_by_priority:
            key_part_1 = (len(av.assigned) + offered_and_available_cache[av]) \
                if len(av.assigned) + offered_and_available_cache[av] <= 2 else 10
            print(f"{av.name}: {key_part_1}, {len(av.assigned)}, {offered_and_available_cache[av]}")

        # assign to the first entry in the list
        volunteer = available_volunteers_by_priority[0]
        edition = self.offered_and_available(volunteer)[0]
        edition.set_translator(volunteer)
        print(f"Rule 5: assgned {volunteer.name} to translate {edition.day_name} {edition.name}")
        return True

    def do_assign_reviewers(self):
        # For this one we have no goal of min or max # reviews per volunteer;
        # the goal is to get as many editions to have a reviewer as possible, though 100% coverage isn't mandatory.
        # so we work from editions, in two passes over the list of all editions:
        # First, for each edition on each day, get the list of people who were available at that time
        # remove the person who is translating
        # if there is only one person left, assign them - unless they are already translating that day.
        # if there is more than one person left, remove those who are translating the same day,
        # and assign whoever is left if only one
        # Complete this pass so we'll have a starting number for how many editions each person is "forced to" review
        # In the next pass,
        # sort available reviewers by # of total reviews + translations they've been assigned
        # Then - new as of 2025-04 - override all assignments with availability from people with the editor role, UNLESS
        # the assignment to be overridden is the only review being done by the person to whom it's assigned
        # (Also: skipping the possibility of multiple EDITORs for now, we have only 1 and having multiple
        # would call for a more complex algo to balance between them) 
        all_editions: list[Edition] = (
            list(itertools.chain.from_iterable((d.morning, d.afternoon, d.evening) for d in self.week.values())))

        for ed in all_editions:
            if ed.translator in ed.r_candidates:
                ed.r_candidates.remove(ed.translator)

            if len(ed.r_candidates) == 0:
                print(f"There are no viable candidates to act as reviewer for {ed.day_name} {ed.name}")
                continue

            print(f"scheduling reviewer for {ed.day_name}")
            other_editions_same_day = [d for d in all_editions if d.day_name == ed.day_name]

            for oed in other_editions_same_day:
                print(f"other edition that day is {oed.day_name} {oed.name} and has translator {oed.translator.name if oed.translator else 'NONE'}")
                if oed.translator in ed.r_candidates:
                    print("removing that person as review candidate")
                    ed.r_candidates.remove(oed.translator)
            if len(ed.r_candidates) == 0:
                print(f"There are no viable candidates to act as reviewer for {ed.day_name} {ed.name}")
                continue
            if len(ed.r_candidates) == 1:
                ed.set_reviewer(ed.r_candidates[0])
                print(f" {ed.day_name} {ed.name} will be reviewed by {ed.reviewer.name}")
                remove_same_day_candidacy(ed, all_editions)
                continue

        print("Done with forced review assignments, now doing prioritized assignment")
        for ed in all_editions:
            print(f"Checking {ed.day_name} {ed.name}...")

            if ed.reviewer:
                continue

            if len(ed.r_candidates) == 0:
                print(f"There are no viable candidates to act as reviewer for {ed.day_name} {ed.name}")
                continue

            if len(ed.r_candidates) == 1:
                ed.set_reviewer(ed.r_candidates[0])
                print(f"{ed.day_name} {ed.name} will be reviewed by {ed.reviewer.name}")
                remove_same_day_candidacy(ed, all_editions)
                continue

            candidates = sorted(ed.r_candidates, key=lambda x: len(x.assigned) + len(x.reviewing))
            print(f"Sorted candidates are: {[(c.name, len(c.assigned), len(c.reviewing)) for c in candidates]}")
            # wherever the editor is available, assign that review to the editor,
            # unless the person currently assigned to review is not reviewing anywhere else AND that person
            # is translating less than 3 times.
            available_editor = [c for c in candidates if 'editor' in c.db_details['role']]
            if any(available_editor):
                if len(candidates[0].reviewing) == 0 and len(candidates[0].assigned) < 3:
                    ed.set_reviewer(candidates[0])
                else:
                    ed.set_reviewer(available_editor[0])

            if not ed.reviewer:
                ed.set_reviewer(candidates[0])

            print(f"{ed.day_name} {ed.name} will be reviewed by {ed.reviewer.name}")
            remove_same_day_candidacy(ed, all_editions)

    def make_translation_schedule(self):

        reloop = True

        while reloop:
            reloop = False
            self.check_rule_1()

            if self.check_rule_2():
                reloop = True
                continue

            if self.check_rule_3():
                reloop = True
                continue

            # step 4 is just to repeat, it's not a separate rule

            if self.check_rule_5():
                reloop = True

        print("done.\n\n\n Assigning reviewers...")
        self.do_assign_reviewers()
        # print("done")

    def print_schedule(self):
        for day in self.week.values():
            print("\n" + day.name)
            for ed in [day.morning, day.afternoon, day.evening]:
                print(f" * {ed.name}:\n     T: {ed.translator.name if ed.translator else ''}" +
                      f"\n     R: {ed.reviewer.name if ed.reviewer else '---'}")

    def persist_schedule(self, week_from_str_p):
        datastore_client = DatastoreClientProxy.get_instance()
        serializable_week_data = {}
        for day_name in self.week:
            serializable_week_data[day_name] = {
                "Morning": {
                    "translator": safe_get_name(self.week[day_name].morning.translator),
                    "reviewer": safe_get_name(self.week[day_name].morning.reviewer)
                },
                "Afternoon": {
                    "translator": safe_get_name(self.week[day_name].afternoon.translator),
                    "reviewer": safe_get_name(self.week[day_name].afternoon.reviewer)
                },
                "Evening": {
                    "translator": safe_get_name(self.week[day_name].evening.translator),
                    "reviewer": safe_get_name(self.week[day_name].evening.reviewer)
                }
            }

        # in some cases there is already a schedule for the given week. Keeping multiple is problematic, the 
        # code which reads the schedule from the DB expects only one per week. Deleting the old ones is too aggressive -
        # sometimes it may be helpful to refer back to the previously drafted schedule. So we'll just mark them
        # with an invalid week name so that we can still look them up, they won't be used by the system, and they'll
        # be cleaned up later.
        query = datastore_client.query(kind="translation_schedule")
        query.add_filter(filter=PropertyFilter("week_from", "=", week_from_str_p))
        draft_backups = query.fetch()
        for dbkup in draft_backups:
            dbkup.update({"week_from": "Draft - " + week_from_str_p})
            datastore_client.put(dbkup)

        # now store the new schedule
        key = datastore_client.key("translation_schedule")
        entity = datastore.Entity(key=key)
        entity.update({"week_from": week_from_str_p, "lang": self.lang, "schedule": serializable_week_data})
        datastore_client.put(entity)

        # finally, let's delete any schedules that aren't related to this month
        now = datetime.now(ZoneInfo('Asia/Jerusalem'))
        this_month = format_date(now, "MMMM", locale='en')
        months = ["January","February","March","April","May","June","July","August","September","October","November","December"]
        if this_month in months:
            # that check is extra protection because I can't figure out why some availability entries were deleted
            month_index = months.index(this_month)
            next_month = months[(month_index + 1) % 12]
            last_month = months[(month_index - 1) % 12]
            print(f"Deleting old schedule entries - anything not from {last_month}, {this_month} or {next_month}")
            query = datastore_client.query(kind="translation_schedule")
            schedules = query.fetch()
            for sched in schedules:
                if this_month not in sched['week_from'] and last_month not in sched['week_from'] and next_month not in sched['week_from']:
                    datastore_client.delete(sched.key)


    def fetch_from_db(self, week_from_str):
        datastore_client = DatastoreClientProxy.get_instance()
        query = datastore_client.query(kind="translation_schedule")
        query.add_filter(filter=PropertyFilter("week_from", "=", week_from_str))
        schedule_info = query.fetch()
        for s in schedule_info:
            if s["lang"] == self.lang:
                return s
        return None
    

    def set_up_next_week(self, week_from_str_param, non_interactive_mode_p):
        if not non_interactive_mode_p:
            additional_no_edition_times_yn = input(f"Are there any editions to skip this coming week? [y/n] ")
            if additional_no_edition_times_yn == 'y':
                print("Oh. This code is missing - time to add it!")
                return False

        # no Friday evening or Saturday morning / afternoon, but there is an early motzei Shabbat in the winter
        editions_to_skip = {"Sunday": [0, 0, 0], "Monday": [0, 0, 0], "Tuesday": [0, 0, 0], "Wednesday": [0, 0, 0],
                            "Thursday": [0, 0, 0], "Friday": [0, 0, 1], "Saturday": [1, 0, 0]}
        is_summer_daylight_savings_time = bool(datetime.now(tz=ZoneInfo("Asia/Jerusalem")).dst())

        if is_summer_daylight_savings_time:
            editions_to_skip["Saturday"] = [1, 1, 0]

        update_user_availability(zero_user, week_from_str_param, editions_to_skip)

        scheduling_prefs = json.loads(os.environ.get("USER_SCHEDULING_PREFERENCES", "{}"))

        for user_name in scheduling_prefs:

            if user_name not in self.cached_users:
                return

            update_user_availability(self.cached_users[user_name], week_from_str_param, scheduling_prefs[user_name])


if __name__ == "__main__":

    non_interactive_mode = len(sys.argv) > 1 and "-y" in sys.argv

    now = datetime.now(ZoneInfo('Asia/Jerusalem'))
    dow = now.isoweekday()  # Monday = 1, Sunday = 7
    if dow == 7:
        dow = 0   # make Sun-Sat 0-6
 
    if "-r" in sys.argv:  # redo *this* week
        week_from = now + timedelta(days=-1 * dow)
    else:
        week_from = now + timedelta(days=(7 - dow))
    week_from_str = format_date(week_from, "MMMM d", locale='en')  # week_from.strftime("%B %d")

    sched = Schedule("en")
    sched.cache_user_info()

    if len(sys.argv) > 1 and "-f" in sys.argv:
        sched.parse_file_input("../weekly_availability.json")
    else:
        sched.get_input_from_datastore(week_from_str)

    if not sched.confirm_proceed_with_available_data(non_interactive_mode):
        exit()

    sched.make_translation_schedule()
    sched.print_schedule()

    sched.persist_schedule(week_from_str)

    the_following_week = week_from + timedelta(days=7)
    the_following_week_str = format_date(the_following_week, "MMMM d", locale='en')
    sched.set_up_next_week(the_following_week_str, non_interactive_mode)
