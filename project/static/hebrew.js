const TEXT_BEING_EDITED = "heb_text";
const LENGTH_LABEL = "אורך:";
const CHARACTERS_LABEL = "אותיות";

// *NOTE:* Many variables used here are set via templating, so defined in the html pages which 
//         import this .js rather than here, as that page is filled in by the Flask app that serves it,
//         whereas this file is served statically.

var last_draft_save_result_good = false;

function updatePreview() {
    update_char_count();
    document.getElementById("preview_panel").innerHTML=makeWhatsappPreview(document.getElementById("heb_text").value);
}

function done() {
    disable_done_button();
    saveDraft(force=true);
    is_finished = last_draft_save_result_good;
}

function disable_done_button() {
    document.getElementById("done_button").style.backgroundColor="#66BB66";
    document.getElementById("done_button").disabled = true;
    document.getElementById("heb_text").disabled = true;
//           document.getElementById("back_home").style.visibility = "visible";
    document.getElementById("edit_anyway_button").style.visibility = "visible";
}

function disable_send_to_translators() {
    document.getElementById("to_translation_button").style.backgroundColor="#66BB66";
    document.getElementById("to_translation_button").disabled = true;
    // document.getElementById("done_button").disabled = false;    // why is this here? Commenting this out 2024-05-16
}

function observe_only() {
    document.getElementById("to_translation_button").disabled = true;
    document.getElementById("done_button").disabled = true;
    document.getElementById("heb_text").disabled = true;
//         document.getElementById("back_home").style.visibility = "visible";
    document.getElementById("edit_anyway_button").style.visibility = "visible";
}

function enable_edit() {
    document.getElementById("heb_text").disabled = false;
    document.getElementById("edit_anyway_button").style.visibility = "hidden";
    if (ok_to_translate) { 
        if (user_role.includes("editor") || user_role.includes("admin")) {
            document.getElementById("done_button").style.backgroundColor="#DDDDDD";
            document.getElementById("done_button").disabled = false;
        }
        if (user_role.includes("editor") && document.getElementById("heb_text").value.includes("עריכה לשונית: עוד לא ידוע")) {
            document.getElementById("heb_text").value = 
                document.getElementById("heb_text").value.replace("עריכה לשונית: עוד לא ידוע", "עריכה לשונית: " + editor_name);
        }
    } else {
        document.getElementById("to_translation_button").disabled = false;
        document.getElementById("to_translation_button").style.backgroundColor="#DDDDDD";
    }
//        document.getElementById("back_home").style.visibility = "hidden";
}

function to_translators() {
    disable_send_to_translators();
    observe_only();
    ok_to_translate = true;
    saveDraft(force=true);
    
    if (continue_to_daily_summary) {
        document.location = "/start_daily_summary";
    } else {
        document.location = "/";
    }
}

function translation_changed() {
    if (last_saved_text.localeCompare(document.getElementById('heb_text').value) != 0) {
            document.getElementById("is_saved").innerText = "השינויים עוד לא שמורים!";
            document.getElementById("is_saved").style.color = "#FF0000";
            document.getElementById("finish_button").innerText = "העתק את כל התוכן";
            is_finished = false;
    } 
}

function saveDraft(force=false) {
    if (is_finished && !force) {
        return;
    }
    curr_text = document.getElementById('heb_text').value;
    if (force || last_saved_text.localeCompare(curr_text) != 0) {
        console.log("saving, text was\n\n"+last_saved_text+"\n\ntext is now\n\n" + curr_text);

        try {
            $.post("/saveDraft",
            {
                draft_key: draft_key,
                source_text: curr_text,
                is_finished: is_finished,
                to_translators: ok_to_translate
            },
            function(data,status) {
                console.log("Draft save status: " + status);
                if (status === "success") {
                    document.getElementById("is_saved").innerText = "כל השינויים שמורים";
                    document.getElementById("is_saved").style.color = "#33AA33";
                    last_saved_text = curr_text;
                    last_draft_save_result_good = true;                
                } else {
                    last_draft_save_result_good = false;
                }
            });
        } catch (err) {
            alert("Error communicating with the server, changes NOT saved. Will retry in 30 seconds.");            
        }
    }
}

setInterval(function(){saveDraft()}, 10000);  // automatically save a draft every 30 seconds, if the text has changed
