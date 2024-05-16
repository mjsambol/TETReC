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

async function notifyServerOfPublish(button_id) {
    published_lang = button_id.substr(-2);
    await fetch("/mark_published?lang=" + published_lang);
}

// var focused = true;
var latest_status = null;

// window.onfocus = function() {
//     focused = true;
// };
// window.onblur = function() {
//     focused = false;
//     stuff_happening = false;
// };

async function updateStatus() {
    if (document.visibilityState == "visible") {
        let obj = await (await fetch("/status")).json();
        latest_status = obj;
        var status_msg = "מצב העבודה נכון ל " + obj['as_of'] + ":";
        lang_order = ['--', 'en', 'fr', 'YY']
        var stuff_happening = false;
        for (lang of lang_order) {
            if (lang in obj['by_lang']) {
                status_msg = status_msg + "<br><br><b>" + obj['by_lang'][lang]['lang'] + ':</b> ';
                if (obj['by_lang'][lang]['elapsed_since_last_edit'] > 3600) {
                    status_msg = status_msg + "לא בתהליך";
                } else {
                    stuff_happening = true;

                    edition_state = getLatestState(obj['by_lang'][lang]["states"]);
                    status_msg = status_msg + edition_state['by_heb'] + " עבד\\ה עד ל" + obj['by_lang'][lang]['last_edit'];

                    if (edition_state["state"] == "WRITING" || edition_state["state"] == "EDIT_READY") {

                        if (lang == '--') {
                            if (edition_state["state"] == "EDIT_READY") {
                                status_msg = status_msg + ' -- <b><font color="#1a9c3b">';
                            } else {
                                status_msg = status_msg + ' -- <b><font color="#d6153c">לא ';
                            }
                            status_msg = status_msg + "מוכן לעריכה</font></b>";
                        }
                    } else if (edition_state["state"] == "EDIT_ONGOING" || edition_state["state"] == "EDIT_NEAR_DONE") {

                        status_msg = status_msg + " -- <b>" + STATE_NAMES_HEBREW[edition_state["state"]] + "</b>";

                    } else if (edition_state["state"] == "PUBLISH_READY" || edition_state["state"] == "PUBLISHED") {
                        status_msg = status_msg + " <b>" + STATE_NAMES_HEBREW[edition_state["state"]] + "</b>";
                        // the variable user_role is passed by the templating engine
                        if (user_role.includes("admin")) {
                            status_msg = status_msg + " <button id=copyText" + lang + ">העתק תוכן</button>";
                        }

                    }


                    // if latest state is PUBLISH_READY show מוכן לשליחה

                    // once published, נשלח

                }
            }
        }
        document.getElementById('translation_status').innerHTML= status_msg; 
        for (lang of lang_order) {
            var thelink = document.getElementById('copyText' + lang);
            if (thelink == null) {
                continue;
            }
            thelink.addEventListener("click", function(event) {copyEditionTextToClipboard(event.target.id);notifyServerOfPublish(event.target.id);});
        }
    } else {
        stuff_happening = false;
    }
    if (stuff_happening) {
        setTimeout(function(){updateStatus()}, 10000);   // update again in 10 seconds
    } else {
        setTimeout(function(){updateStatus()}, 30000);  // update again in 30 seconds
    }

};

async function getLatestStatus(also_call) {
    // this is very similar to updateStatus() 
    // which is specifically meant for updating the main index page's status summary
    // this method is for updating status labels on other pages
    latest_status = await (await fetch("/status")).json();

    // update the heb_status_label
    status_label = document.getElementById("heb_status_label");
    states = latest_status["by_lang"]["--"]["states"];
    status_label.innerHTML = "<b>" + STATE_NAMES[states[states.length - 1]["state"]] + "</b><br>Since " + states[states.length - 1]["at"].substring(9,11) + ":" + states[states.length - 1]["at"].substring(11,13)
    + "<br>Last edit: " + latest_status["by_lang"]["--"]["last_edit"];

    also_call(latest_status);
}


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

const STATE_NAMES = {
    "WRITING": "Writing",
    "EDIT_READY": "Ready for Editing",
    "EDIT_ONGOING": "Being Edited",
    "EDIT_NEAR_DONE": "Mostly Edited",
    "PUBLISH_READY": "Ready to be Sent",
    "PUBLISHED": "Published"
}
const STATE_NAMES_HEBREW = {
    "WRITING": "בכתיבה",
    "EDIT_READY": "מוכן לעריכה",
    "EDIT_ONGOING": "בעריכה",
    "EDIT_NEAR_DONE": "בשלב מתקדם של עריכה",
    "PUBLISH_READY": "מוכן לשליחה",
    "PUBLISHED": "נשלח"
}

function getLatestState(state_arr) {
    for (st of state_arr) {
        if (st["state"] == "PUBLISHED") {
            return st;
        }
    }
    for (st of state_arr) {
        if (st["state"] == "PUBLISH_READY") {
            return st;
        }
    }
    for (st of state_arr) {
        if (st["state"] == "EDIT_NEAR_DONE") {
            return st;
        }
    }
    for (st of state_arr) {
        if (st["state"] == "EDIT_ONGOING") {
            return st;
        }
    }
    for (st of state_arr) {
        if (st["state"] == "EDIT_READY") {
            return st;
        }
    }
    for (st of state_arr) {
        if (st["state"] == "WRITING") {
            return st;
        }
    }
    return st[0];
}