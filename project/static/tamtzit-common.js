/*
    Text Editing, Translation and Review Coordination tool
    Copyright (C) 2023-2025, Moshe Sambol, https://github.com/mjsambol

    Originally created for the Tamtzit Hachadashot / News In Brief project
    of the Lokhim Ahrayut non-profit organization
    Published in English as "Israel News Highlights"

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
*/

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
const lang_order = ['--', 'en', 'fr', 'YY', 'H1'];

async function updateStatus() {
    var stuff_happening = false;
    console.log(document.visibilityState);
    if (document.visibilityState == "visible" || latest_status == null) {  // for some reason it's not executing on the first call on new tab, hopefully this helps
        fetch("/status").then(
            (response) => {return response.json();}
        ).then(
            (obj) => {
                latest_status = obj;
                var status_msg = "מצב העבודה נכון ל " + obj['as_of'] + ":";   
                status_msg += "<br><br><table border=0 cellspacing='10px'>";
                for (lang of lang_order) {
                    if (lang in obj['by_lang']) {
                        status_msg = status_msg + "<tr><td><b>" + obj['by_lang'][lang]['lang'] + ':</b> </td><td>';
                        if (obj['by_lang'][lang]['elapsed_since_last_edit'] > 3600) {
                            status_msg = status_msg + "לא בתהליך";
                        } else {
                            stuff_happening = true;
        
                            edition_state = getLatestState(obj['by_lang'][lang]["states"]);
                            status_msg = status_msg + formatStateHistory(obj['by_lang'][lang]["states"]); 
                            status_msg = status_msg.substring(0, status_msg.length - 4);
                            if (edition_state["state"] == "WRITING" || edition_state["state"] == "EDIT_READY") {
                                status_msg = status_msg + " עד ל " + obj['by_lang'][lang]['last_edit'];
                                if (edition_state["state"] == "EDIT_READY") {
                                    status_msg = status_msg + ' -- <b><font color="#1a9c3b">';
                                } else {
                                    status_msg = status_msg + ' -- <b><font color="#d6153c">לא ';
                                }
                                status_msg = status_msg + "מוכן לעריכה</font></b></td>";
                            } else if (edition_state["state"] == "EDIT_ONGOING" || edition_state["state"] == "EDIT_NEAR_DONE") {
        
                                status_msg = status_msg + " -- <b>" + STATE_NAMES_HEBREW[edition_state["state"]] + "</b>";
                                status_msg = status_msg + " עד ל" + obj['by_lang'][lang]['last_edit'] + "</td>";
        
                            } else if (edition_state["state"] == "PUBLISH_READY" || edition_state["state"] == "PUBLISHED") {
                                status_msg = status_msg + "</td><td> <b>" + STATE_NAMES_HEBREW[edition_state["state"]] + "</b></td><td>";
                                // the variable user_role is passed by the templating engine
                                if (user_role.includes("admin")) {
                                    status_msg = status_msg + " <button id=copyText" + lang + ">העתק תוכן</button>";
                                }
                                status_msg = status_msg + "</td>";
                            }        
                        }
                        status_msg = status_msg + "</tr>";
                    }
                }
                document.getElementById('translation_status').innerHTML= status_msg + "</table>"; 
                for (lang of lang_order) {
                    var thelink = document.getElementById('copyText' + lang);
                    if (thelink == null) {
                        continue;
                    }
                    thelink.addEventListener("click", function(event) {copyEditionTextToClipboard(event.target.id);notifyServerOfPublish(event.target.id);});
                }
            }
        ).catch(function(error) {
            console.log(error);
        });
    } 
    
    if (stuff_happening) {
        setTimeout(function(){updateStatus()}, 10000);   // update again in 10 seconds
    } else {
        setTimeout(function(){updateStatus()}, 30000);  // update again in 30 seconds
    }
}
            

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

    if (typeof dont_remove_footer !== 'undefined' && dont_remove_footer) {  // an override that is defined in hebrew.html and hebrew_mobile.html
        return;
    }
    //
    // I never noticed it before, but suddenly this code is making the cursor jump to the end of the section,
    // which is intolerable if it happens while a user is editing the text
    //
    var curr_cursor_pos = document.getElementById(TEXT_BEING_EDITED).selectionStart;
    section_divider = "•   •   •\n\n";
    strip_from = translated_text.lastIndexOf(section_divider) + section_divider.length;
    last_chunk = translated_text.substring(strip_from);
    var changed = false;
    if (entry_len > 4000) {
        document.getElementById("char_count").style.color="#FF0000";
        // remove the link to subscribe, it's not going to be rendered correctly anyway
        if (last_chunk.indexOf("https://") > 0) {
            link_to_subscribe = last_chunk.substring(0, last_chunk.indexOf("\n\n") + 2);            
            translated_text = translated_text.substring(0, strip_from) + last_chunk.substring(last_chunk.indexOf("\n\n") + 2);
            document.getElementById(TEXT_BEING_EDITED).value = translated_text;
            changed = true;
        }
    } else {
        document.getElementById("char_count").style.color="#000000";
        if ((last_chunk.indexOf("https://") == -1) && (entry_len + link_to_subscribe.length < 4000)) {
            // include the link to subscribe
            translated_text = translated_text.substring(0, strip_from) + link_to_subscribe + last_chunk;
            document.getElementById(TEXT_BEING_EDITED).value = translated_text;
            changed = true;
        }
    }
    if (changed) {
        document.getElementById(TEXT_BEING_EDITED).setSelectionRange(curr_cursor_pos,curr_cursor_pos);
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
    var states_in_order = ["PUBLISHED", "PUBLISH_READY", "EDIT_NEAR_DONE", "EDIT_ONGOING", "EDIT_READY", "WRITING"];
    for (state_step of states_in_order) {
        for (st of state_arr) {
            if (st["state"] == state_step) {
                return st;
            }
        }    
    }
}

function formatStateHistory(state_arr) {
    var result_str = "";
    var states_in_order = ["WRITING", "EDIT_READY", "EDIT_ONGOING", "EDIT_NEAR_DONE", "PUBLISH_READY"];//, "PUBLISHED"];
    var prev_contributor = "";
    for (state_step of states_in_order) {
        for (st of state_arr) {
            if ((st["state"] == state_step) && (st["by_heb"]) != prev_contributor) {
                result_str += st["by_heb"] + " -> ";
                prev_contributor = st["by_heb"];
                break;
            }
        }    
    }
    return result_str;
}