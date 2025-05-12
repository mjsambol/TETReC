##################################################################################
#
# Team Text Editing, Translation and Review Coordination tool
# Copyright (C) 2023-2025, Moshe Sambol, https://github.com/mjsambol
#
# Originally created for the Tamtzit Hachadashot / News In Brief project
# of the Lokhim Ahrayut non-profit organization
# Published in English as "Israel News Highlights"
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
#################################################################################

from textwrap import dedent

from common import DateInfo
from language_mappings import editions

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
        """),
    "en":
        dedent("""\
        *Dear readers,*
        The next update will be sent about an hour after the end of Shabbat in Israel. Shabbat shalom!
        """),
    "fr":
        dedent("""\
        *Chers lecteurs,*
        *Cette édition est la dernière de la journée.* La prochaine édition sera publiée environ 1 heure après la sortie de Chabbat (heure Israélienne). 
        Chabbat Chalom               
        """)
}
friday_afternoon_not_dst["YY"] = friday_afternoon_not_dst["he"]

friday_afternoon_in_dst = {  # in dst == SUMMER i.e. Pesach to Simchat Torah
    "he":
        dedent("""\
        *קוראים יקרים,*
        *המהדורה הבאה תישלח במוצאי שבת, בשעה הרגילה של מהדורת הערב.*
        """),
    "fr":
        dedent("""\
        *Chers lecteurs,*
        La prochaine édition sera publiée demain soir à l'heure habituelle (entre 21h30 et 22h30). Chabbat Chalom
        """)
}
friday_afternoon_in_dst["YY"] = friday_afternoon_in_dst["he"]
friday_afternoon_in_dst["H1"] = friday_afternoon_in_dst["he"]
friday_afternoon_in_dst["en"] = friday_afternoon_not_dst["en"]

saturday_early_edition = {
    "he":
        dedent("""\
        *קוראים יקרים, זוהי מהדורה מקוצרת*.
        מהדורת ערב תישלח בשעה הרגילה.
        """),
    "en":
        dedent("""\
        *Motzei Shabbat Update*

        Dear readers, shavua tov. This is an abridged edition. 
        A regular edition will be sent after 9 PM Israel time.
        """),
    "fr":
        dedent("""\
        *Mise à jour résumée du samedi soir.*

        Chers lecteurs, 
        Ceci est une mise à jour résumée de l'actualité. L'édition régulière sera publiée après 21h30.
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

    if lang_code in ["he", "H1", "YY"]:

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

    elif lang_code == "en":
        result += "📻 *Israel News Highlights*\n"
        part_of_day = "Early Evening" if date_info.motzei_shabbat_early else date_info.part_of_day
        result += f"*{part_of_day} Edition: {date_info.day_of_week}, {date_info.hebrew_dom} {date_info.hebrew_month}, {date_info.hebrew_year}*"
        result += f" / {date_info.secular_month} {date_info.secular_dom}, {date_info.secular_year}"

    elif lang_code == "fr":
        result += "📻 *L'essentiel de l'actualité*\n"
        result += f"*Édition "
        heb_month_name = date_info.hebrew_month
        if heb_month_name == "Cheshvan":
            heb_month_name = "Heshvan"    # by request of Ithai Meier 2024-11-19
        if date_info.part_of_day in ('Matin','soir'):
            result += "du "
        else:
            result += "de "
        result += f"{date_info.part_of_day}: {date_info.day_of_week} {date_info.hebrew_dom} {heb_month_name} {date_info.hebrew_year}*"
        result += f" / {date_info.secular_dom} {date_info.secular_month} {date_info.secular_year}"

    result += dedent("""\
        \n
        •   •   •
        
        """)

    if lang_code in ['he', 'H1']:
        result += dedent("""\
        לפרסום העסק שלכם לעשרות אלפים בתמצית החדשות לחצו 👇
        https://link.mmb.org.il/mpirsum

        •   •   •
        
        """)
    return result


def make_footer(lang_code: str, date_info: DateInfo) -> str:
    result = dedent("""\
                    
        •   •   •

        """)

    if lang_code in ["he", "H1"]:
        
        if lang_code == "H1":
            # result += dedent("""\
            # ✓ *להצטרפות לתמצית החדשות - המהדורה היומית:*
            #     https://link.mmb.org.il/1news""")
            result += dedent("""\
                ✓ *מזמינים חברים לחסוך זמן וסטרס עם תמצית החדשות!*
                *לשיתוף עם חברים לוחצים כאן👇*
                link.mmb.org.il/share1""")
        elif lang_code == "he":
            # result += dedent("""\
            # ✓ *להצטרפות לתמצית החדשות:*
            #     https://link.mmb.org.il/news""")
            result += dedent("""\
                ✓ *מזמינים חברים לחסוך זמן וסטרס עם תמצית החדשות!*
                *לשיתוף עם חברים לוחצים כאן👇*
                link.mmb.org.il/share""")

        result += dedent("""
                         
            ✓ *בדף הפייסבוק שלנו כבר ביקרת?*
                https://link.mmb.org.il/news_facebook
            
            ✓ *לפניות למוקד הוואטסאפ שלנו:*
                052-439-3118""")
        
    elif lang_code == "YY":
        result += dedent("""\
        ✓ *להצטרפות לקבוצות תמצית החדשות לנוער:*
            https://link.mmb.org.il/newsteen""")
        
    elif lang_code == "en":
        result += dedent("""\
            ✓ *To subscribe to Israel News Highlights:* 
                https://link.mmb.org.il/INH_NEWS 

            ✓ *For suggestions or support via WhatsApp:* 
                +972524393118""")

    elif lang_code == "fr":
        result += dedent("""\
            ✓ *Pour rejoindre News Israel L'essentiel:* 
                https://link.mmb.org.il/news_f 

            ✓ *Pour toute demande ou contact:* 
                +972587815211""")
 
    return result

