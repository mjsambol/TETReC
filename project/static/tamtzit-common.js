function makeWhatsappPreview(input) {
    result = input.replaceAll(/\*(\S[^\n]+?)\*/g,"<b>$1</b>");
    result = result.replaceAll(/_(\S[^\n]+?)_/g,"<i>$1</i>");
    result = result.replaceAll("\n", "<br>");
    result = result.replaceAll(/(https:\/\/\S+)/g,"<a href=\"$1\">$1</a>");
    result = result.replaceAll("++++++++++++++++++++++++++", "");
    return result;
}

function copyToClipboard(from_where) {
    the_stuff = document.getElementById(from_where).value;
    the_stuff = the_stuff.replaceAll("++++++++++++++++++++++++++", "");
    navigator.clipboard.writeText(the_stuff);
}

var focused = true;

window.onfocus = function() {
    focused = true;
};
window.onblur = function() {
    focused = false;
    stuff_happening = false;
};

async function updateStatus() {
    if (focused) {
        let obj = await (await fetch("/status")).json();
        var status = "מצב העבודה נכון ל " + obj['as_of'] + ":";
        lang_order = ['--', 'en', 'fr', 'YY']
        var stuff_happening = false;
        for (lang of lang_order) {
            if (lang in obj['by_lang']) {
                status = status + "<br><br><b>" + obj['by_lang'][lang]['lang'] + ':</b> ';
                if (obj['by_lang'][lang]['elapsed_since_last_edit'] > 3600) {
                    status = status + "לא בתהליך";
                } else {
                    stuff_happening = true;
                    status = status + obj['by_lang'][lang]['who'] + ' התחיל\\ה ' + " ועבד\\ה עד ל" + obj['by_lang'][lang]['last_edit'];
                    if (lang == '--') {
                        if (obj['by_lang'][lang]['ok_to_translate']) {
                            status = status + ' -- <b><font color="#1a9c3b">';
                        } else {
                            status = status + ' -- <b><font color="#d6153c">לא ';
                        }
                        status = status + "מוכן לתרגום</font></b>";
                    }
                }
            }
        }
        document.getElementById('translation_status').innerHTML= status; 
    }
    if (stuff_happening) {
        setTimeout(function(){updateStatus()}, 30000);   // update again in 30 seconds
    } else {
        setTimeout(function(){updateStatus()}, 120000);  // update again in 2 minutes. 
    }

};
