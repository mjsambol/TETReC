# for starters I'll process a JSON input file
# later will make this a flask app that can run in the cloud,
# expose a form for input and a page showing results after everyone has provided input

import json
from typing import List


class Person:
    def __init__(self, name) -> None:
        self.name = name
        self.offered = None  # once set, this dict is static. The format is {"Sunday":[0,1,1], "Monday":[1,0,0]}
        self.days_offered = 0
        self.total_offered = 0
        self.assigned = []

    def set_offered(self, offer_dict):
        self.offered = offer_dict
        for day_offer_name in offer_dict:
            if len(offer_dict[day_offer_name]) < 3:
                # pad out any partial arrays so we don't have trouble with them later
                self.offered[day_offer_name] = offer_dict[day_offer_name] + [0] * (3 - len(offer_dict[day_offer_name]))
        for day_offer in offer_dict.values():
            self.days_offered += any(day_offer)
            self.total_offered += sum(day_offer)


class Edition:
    def __init__(self, day_name: str, name: str) -> None:
        self.day_name = day_name
        self.name = name
        self.offered = []  # original volunteers - doesn't change
        self.candidates = []  # grows and shrinks due to the algorithm
        self.translator = None
        self.reviewer = None

    def set_translator(self, translator: Person):
        self.translator = translator
        translator.assigned.append(self)

    def add_offer(self, volunteer: Person):
        self.offered.append(volunteer)
        self.candidates.append(volunteer)


class Day:
    def __init__(self, name: str) -> None:
        self.name = name
        self.morning = Edition(self.name, "Morning")
        self.afternoon = Edition(self.name, "Afternoon")
        self.evening = Edition(self.name, "Evening")


def offered_and_available(per: Person) -> List[Edition]:
    offered_and_available_list = []
    for offer_day_name in per.offered:
        day_data = week[offer_day_name]
        offer_data = per.offered[offer_day_name]
        if offer_data[0] == 1 and not day_data.morning.translator and per in day_data.morning.candidates:
            offered_and_available_list.append(day_data.morning)
        if offer_data[1] == 1 and not day_data.afternoon.translator and per in day_data.afternoon.candidates:
            offered_and_available_list.append(day_data.afternoon)
        if offer_data[2] == 1 and not day_data.evening.translator and per in day_data.evening.candidates:
            offered_and_available_list.append(day_data.evening)
    return offered_and_available_list


week = {n: Day(n) for n in ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]}
team = {n: Person(n) for n in ["Anne", "Ayelet", "Gabriela", "Karen", "Malke", "Moshe", "Rebecca", "Rochel"]}

no_edition_times = [week["Friday"].evening, week["Saturday"].morning, week["Saturday"].afternoon]


def parse_input():
    with open("weekly_availability.json") as in_file:
        volunteer_input = json.load(in_file)
    for volunteer_entry in volunteer_input:
        volunteer = team[volunteer_entry["name"]]
        volunteer.set_offered(volunteer_entry["offer"])
        print(f'{volunteer.name} offered {volunteer.total_offered} options across {volunteer.days_offered} days')
        for day_name in week:
            day = week[day_name]
            day_offer = volunteer_entry["offer"][day_name]
            if day_offer[0]:
                day.morning.add_offer(volunteer)
            if day_offer[1]:
                day.afternoon.add_offer(volunteer)
            if day_offer[2]:
                day.evening.add_offer(volunteer)


def check_rule_1():
    # Rule 1: For a slot that has only one person available, assign them
    print("Checking rule 1...")
    for day in week.values():
        print(f"Checking {day.name}")
        day = week[day.name]
        all_editions = [day.morning, day.afternoon, day.evening]
        for edition in all_editions:
            if edition.translator:
                continue
            if edition in no_edition_times:
                continue

            print(f"checking {edition.name} - {len(edition.offered)} original offers, ")
            print(f" with {len(edition.candidates)} curr candidates")
            if len(edition.candidates) == 1:
                # and also tell the translator he's been assigned, so that he can keep track of how many assignments
                edition.set_translator(edition.candidates[0])
                print(f"Rule 1: {edition.translator.name} will translate on {day.name} {edition.name}")


def check_rule_2():
    print("Checking rule 2...")
    rule_appled = False
    # Rule 2: For each day, for each person who already has an assignment that day,
    # remove them as candidates for other slots that day unless they are the only volunteer in the second slot as well,
    # or unless they are one of two, both of whom have one of the day's other slots  -- @TODO not yet being checked

    for day in week.values():
        all_editions = [day.morning, day.afternoon, day.evening]
        for edition in all_editions:
            if edition.translator:
                other_edidtions = [e for e in all_editions if e != edition]
                for other_edition in other_edidtions:
                    if other_edition.translator:
                        continue
                    if edition.translator in other_edition.candidates and len(other_edition.candidates) > 1:
                        other_edition.candidates.remove(edition.translator)
                        print(f"Rule 2: removing {edition.translator.name} from {day.name} {other_edition.name}")
                        rule_appled = True
    return rule_appled


def check_rule_3():
    # Rule 3: Once a person has three assigned slots, remove them from other slots across the week
    # unless they are the only one left in that slot (in which case they're already assigned to there),
    # or unless all volunteers for that slot have the same number of other assignments
    print("Checking rule 3...")
    rule_applied = False

    for day in week.values():
        for edition in [day.morning, day.afternoon, day.evening]:
            if edition.translator:
                continue

            to_remove = []
            for volunteer in edition.candidates:
                if len(volunteer.assigned) >= 3:
                    to_remove.append(volunteer)
            # sort to_remove by number of assignments, high to low
            to_remove.sort(reverse=True, key=lambda x: len(x.assigned))

            # remove volunteers from edition.candidates working through the list of to_remove
            # until all those left have the same number of assignments as the last in the list
            while len(to_remove) > 0 and len(to_remove[0].assigned) > len(to_remove[-1].assigned):
                print(f"removing {to_remove[0].name} as candidate for {day.name} {edition.name} ")
                print(f"  - already has {len(to_remove[0].assigned)} assignments")
                edition.candidates.remove(to_remove[0])
                to_remove.remove(to_remove[0])
                rule_applied = True
    print("done with rule 3")
    return rule_applied


def check_rule_5():
    # rather than rule 5 as written in the doc, I'm trying what looks like a simpler approach:
    # for each volunteer, calculate the number of slots which they have volunteered for and which are still available.
    # Call this num_offered_and_available
    # for anyone where that number is zero, remove them from the list, there's nothing I can assign them
    # otherwise, sort the list of volunteers by primary criteria num_offered_and_available (ascending)
    # and secondary criteria num_assignments (ascending)
    # take the first person with the lowest of those two, give them an assignment,
    # recalculate their num_offered_and_available, repeat the outer loop from the top

    offered_and_available_cache = {p: len(offered_and_available(p)) for p in team.values()}

    available_volunteers = [p for p in team.values()
                            if len(p.assigned) < max_assignments_per_volunteer
                            and offered_and_available_cache[p] > 0]
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
    edition = offered_and_available(volunteer)[0]
    edition.set_translator(volunteer)
    print(f"Rule 5: assgned {volunteer.name} to translate {edition.day_name} {edition.name}")
    return True


parse_input()

max_assignments_per_volunteer = 3  # hopefully. This may get raised as we go, if needed
reloop = True

while reloop:
    reloop = False
    check_rule_1()

    if check_rule_2():
        reloop = True
        continue

    if check_rule_3():
        reloop = True
        continue

    # step 4 is just to repeat, it's not a separate rule

    if check_rule_5():
        reloop = True

print("done")
