from textwrap import dedent

from .common import DateInfo
from .language_mappings import editions

friday_afternoon_not_dst = {  # not in_dst == WINTER i.e. Simchat Torah to Pesach
    "he":
        dedent("""\
        *קוראים יקרים,*
        *המהדורה הבאה תישלח כשעה לאחר צאת השבת.*
        """),
    "H1":
        dedent("""\
        *קוראים יקרים,*
        *המהדורה הבאה תישלח במוצאי שבת, בשעה הרגילה של מהדורת הערב.*
        אם יהיו אירועים חריגים נשלח עדכון מיוחד לאחר צאת השבת.
        """)
}
friday_afternoon_not_dst["YY"] = friday_afternoon_not_dst["he"]

friday_afternoon_in_dst = {  # in dst == SUMMER i.e. Pesach to Simchat Torah
    "he":
        dedent("""\
        *קוראים יקרים,*
        *המהדורה הבאה תישלח במוצאי שבת, בשעה הרגילה של מהדורת הערב.*
        """)
}
friday_afternoon_in_dst["YY"] = friday_afternoon_in_dst["he"]

saturday_early_edition = {
    "he":
        dedent("""\
        *קוראים יקרים, זוהי מהדורה מקוצרת*.
        מהדורת ערב תישלח בשעה הרגילה.
        """)
}
saturday_early_edition["YY"] = saturday_early_edition["he"]


def make_header(lang_code: str, date_info: DateInfo) -> str:
    which_edition = 1  # 0 / 1 / 2 = morning, afternoon, evening. 
    if date_info.part_of_day == editions[lang_code][2]:
        which_edition = 2
    elif date_info.part_of_day == editions[lang_code][0]:
        which_edition = 0

    print(f"Which edition: {which_edition}")

    result = ""

    if date_info.erev_shabbat:
        if date_info.is_dst:
            result += friday_afternoon_in_dst[lang_code]
        else:
            result += friday_afternoon_not_dst[lang_code]
    elif date_info.motzei_shabbat_early:
        result += saturday_early_edition[lang_code]

    result = result.strip()

    if len(result):

        result += dedent("""
            
            •   •   •
                         
            """)
    result += "📻 *תמצית החדשות"

    if lang_code == "YY":
        result += " לנוער"
    
    result += "*\n"

    mehadura = ""
    if lang_code == "H1":
        mehadura = "*המהדורה היומית, "
        if date_info.day_of_week_digit == 6:
            mehadura += "מוצאי שבת, "
    else:
        mehadura = "*מהדורת "
        if date_info.day_of_week_digit == 6:
            if not date_info.is_dst:
                if date_info.motzei_shabbat_early:
                    mehadura += "מוצאי שבת, "
                elif which_edition == 2:
                    mehadura += "ערב, מוצאי שבת, "
            else:
                mehadura += "מוצאי שבת, "
        else:           
            mehadura += f"{date_info.part_of_day}, {date_info.day_of_week}, "

    result += mehadura
    result += f"{date_info.hebrew_dom_he} ב{date_info.hebrew_month_he} "
    result += f"{date_info.hebrew_year_he}*, {date_info.secular_dom} ב{date_info.secular_month} {date_info.secular_year}"

    result += dedent("""\
        \n
        •   •   •
        
        """)

    return result


def make_footer(lang_code: str, date_info: DateInfo) -> str:
    result = dedent("""\
                    
        •   •   •

        """)

    if lang_code in ["he", "H1", "YY"]:
        
        if lang_code == "H1":
            result += dedent("""\
            ✓ *להצטרפות לתמצית החדשות - המהדורה היומית:*
                https://link.mmb.org.il/1news""")
        elif lang_code == "he":
            result += dedent("""\
            ✓ *להצטרפות לתמצית החדשות:*
                https://link.mmb.org.il/news""")
        elif lang_code == "YY":
            result += dedent("""\
            ✓ *להצטרפות לקבוצות תמצית החדשות לנוער:*
                https://link.mmb.org.il/newsteen""")

        result += dedent("""
                         
            ✓ *בדף הפייסבוק שלנו כבר ביקרת?*
                https://link.mmb.org.il/news_facebook
            
            ✓ *לפניות למוקד הוואטסאפ שלנו:*
                052-439-3118""")
        
    return result

