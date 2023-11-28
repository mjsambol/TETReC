function makeWhatsappPreview(input) {
    result = input.replaceAll(/\*(\S[^\n]+?)\*/g,"<b>$1</b>");
    result = result.replaceAll(/_(\S[^\n]+?)_/g,"<i>$1</i>");
    result = result.replaceAll("\n", "<br>");
    result = result.replaceAll(/(https:\/\/\S+)/g,"<a href=\"$1\">$1</a>");
    return result;
}

function copyToClipboard(from_where) {
    navigator.clipboard.writeText(document.getElementById(from_where).value);
}

