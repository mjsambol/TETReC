import re

def debug(stuff):
    print(stuff)

def pre_translation_swaps(text):
    text = re.sub(r'\bרב"ט\b', 'Corporal', text, re.U)
    text = re.sub(r'\bסמל\b',  'Sergeant', text, re.U)
    text = re.sub(r'\bסמ"ר\b', 'Staff Sergeant', text, re.U)

    text = re.sub(r'\bרב סמל\b', 'Sergeant First Class', text, re.U)
    text = re.sub(r'\bרס"ל\b',   'Sergeant First Class', text, re.U)

    text = re.sub(r'\bרב סמל ראשון\b', 'Chief Sergeant First Class', text, re.U)
    text = re.sub(r'\bרס"ר\b',       'Chief Sergeant First Class', text, re.U)
    text = re.sub(r'\bרס"מ\b',       'Master Sergeant', text, re.U)
    text = re.sub(r'\bרס"ם\b',       'Master Sergeant', text, re.U)

    text = re.sub(r'\bרס"ב\b', 'First Sergeant', text, re.U)
    text = re.sub(r'\bרנ"מ\b', 'Sergeant Major', text, re.U)
    text = re.sub(r'\bרנ"ם\b', 'Sergeant Major', text, re.U)
    text = re.sub(r'\bרנ"ג\b', 'Command Sergeant Major', text, re.U)

    text = re.sub(r'\bסמ"ג\b', 'Second Lieutenant', text, re.U)
    text = re.sub(r'\bסגן\b',  'First Lieutenant', text, re.U)
    text = re.sub(r'\bסרן\b',  'Captain', text, re.U)

    text = re.sub(r'\bרב סרן\b', 'Major', text, re.U)
    text = re.sub(r'\bרס"ן\b', 'Major', text, re.U)
    text = re.sub(r'\bרס"נ\b', 'Major', text, re.U)

    text = re.sub(r'\bסא"ל\b',   'Lieutenant Colonel', text, re.U)
    text = re.sub(r'\bסגן אלוף\b', 'Lieutenant Colonel', text, re.U)

    text = re.sub(r'\bאלוף משנה\b', 'Colonel', text, re.U)

    text = re.sub(r'\bתת אלוף\b', 'Brigadier General', text, re.U)
    text = re.sub(r'\bאלוף\b',    'Major General', text, re.U)
    text = re.sub(r'\bרב אלוף\b', 'Lieutenant General', text, re.U)

    return text

def post_translation_swaps(text):
    return text