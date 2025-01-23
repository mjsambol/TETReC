from openai import OpenAI
client = OpenAI()

completion = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are translating news updates from Hebrew to English. The translation may freely restructure sentences to make them more natural for English readers."},
        {"role": "system", "content": "Each item begins with a hyphen at the start of the line; the translation should maintain separation between items, and each should begin with a hyphen at the start of the line."},
        # {"role": "system", "content": "Do not abbreviate anything which is not abbreviated in the Hebrew."""},
        # {"role": "system", "content": "Text which indicates when the news item happened, such as 'last night' or 'this morning', should be minimized in the translation."},
        {"role": "system", "content": "The following python dictionary should be used to enforce some translations. For example, the Hebrew word אזעקות should always be translated as sirens."},
        {"role": "user", "content": [{"type": "text", "text":"{'אזעקות':'sirens', 'אצבע הגליל':'the Galilee Panhandle'}"}]},
        {"role": "system", "content": "In addition, the following python dictionary indicates English words which sometimes appear in the translation results, and alternatives which should be used instead."},
        {"role": "user", "content": [{"type": "text", "text":"{'figher':'soldier'}"}]},
        {
            "role": "user",
#            "content": "what's a nice way to wish someone a happy Jewish new year?"
             "content": "Translate the following Hebrew text to English:" + 
             """- תקיפות צה"ל בביירות נמשכות. מדובר צה"ל נמסר כי הלילה תקף חיל האוויר מפקדות מודיעיניות של חיזבאללה בביירות, וכן מטרות טרור נוספות ברחבי לבנון. 

 - בקרבות בדרום לבנון נפצע קשה לוחם מגדוד 7012 של חטיבת אלכסנדרוני.  

 - בלילה ולפנות בוקר נשמעו אזעקות באצבע הגליל, בגליל העליון ובגליל המערבי. אזעקות נשמעו הלילה גם באזור גוש דן, בעקבות שיגורים מלבנון. שריפה פרצה בבית העלמין בפתח תקווה בעקבות נפילת רסיסים."""
        }
    ]
)

print(completion.choices[0].message)