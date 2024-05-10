function makeWhatsappPreview(input) {
    result = input.replaceAll(/\*(\S[^\n]+?)\*/g,"<b>$1</b>");
    result = result.replaceAll(/_(\S[^\n]+?)_/g,"<i>$1</i>");
    result = result.replaceAll("\n", "<br>");
    result = result.replaceAll(/(https:\/\/\S+)/g,"<a href=\"$1\">$1</a>");
    result = result.replaceAll("++++++++++++++++++++++++++", "");
    return result;
}

async function copyToClipboardTrick(textToCopy) {
    // Navigator clipboard api needs a secure context (https)
    if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(textToCopy);
    } else {
        // Use the 'out of viewport hidden text area' trick
        const textArea = document.createElement("textarea");
        textArea.value = textToCopy;
            
        // Move textarea out of the viewport so it's not visible
        textArea.style.position = "absolute";
        textArea.style.left = "-999999px";
            
        document.body.prepend(textArea);
        textArea.select();

        try {
            document.execCommand('copy');
        } catch (error) {
            console.error(error);
        } finally {
            textArea.remove();
        }
    }
}


function copyToClipboard(from_where) {
    the_stuff = document.getElementById(from_where).value;
    the_stuff = the_stuff.replaceAll("++++++++++++++++++++++++++", "");
    copyToClipboardTrick(the_stuff);
}

function copyEditionTextToClipboard(button_id) {
    var txt = latest_status['by_lang'][button_id.substr(-2)]['text'];
    copyToClipboardTrick(txt);
}

var focused = true;
var latest_status = null;

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
        latest_status = obj;
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
                    // if the user is an admin AND the text is in status "done", show a button to copy the text to clipboard
                    if (obj['by_lang'][lang]['done'] && user_role.includes("admin")) {
                        status = status + " -- <b>מוכן לשליחה</b> <button id=copyText" + lang + ">העתק תוכן</button>";
                    }
                }
            }
        }
        document.getElementById('translation_status').innerHTML= status; 
        for (lang of lang_order) {
            var thelink = document.getElementById('copyText' + lang);
            if (thelink == null) {
                continue;
            }
            thelink.addEventListener("click", function(event) {copyEditionTextToClipboard(event.target.id);});
        }
    }
    if (stuff_happening) {
        setTimeout(function(){updateStatus()}, 30000);   // update again in 30 seconds
    } else {
        setTimeout(function(){updateStatus()}, 120000);  // update again in 2 minutes. 
    }

};

var link_to_subscribe = null;

function update_char_count() {
    translated_text = document.getElementById(TEXT_BEING_EDITED).value;
    entry_len = translated_text.length;
    document.getElementById("char_count").innerHTML=LENGTH_LABEL + " " + entry_len + " " + CHARACTERS_LABEL;
    section_divider = "•   •   •\n\n";
    strip_from = translated_text.lastIndexOf(section_divider) + section_divider.length;
    last_chunk = translated_text.substring(strip_from);
    if (entry_len > 4000) {
        document.getElementById("char_count").style.color="#FF0000";
        // remove the link to subscribe, it's not going to be rendered correctly anyway
        if (last_chunk.indexOf("https://") > 0) {
            link_to_subscribe = last_chunk.substring(0, last_chunk.indexOf("\n\n") + 2);            
            translated_text = translated_text.substring(0, strip_from) + last_chunk.substring(last_chunk.indexOf("\n\n") + 2);
            document.getElementById(TEXT_BEING_EDITED).value = translated_text;
        }
    } else {
        document.getElementById("char_count").style.color="#000000";
        if ((last_chunk.indexOf("https://") == -1) && (entry_len + link_to_subscribe < 4000)) {
            // include the link to subscribe
            translated_text = translated_text.substring(0, strip_from) + link_to_subscribe + last_chunk;
            document.getElementById(TEXT_BEING_EDITED).value = translated_text;
        }
    }
}
