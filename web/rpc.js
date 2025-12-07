const RPC_URL = 'https://apollo.loping.net/rpc/soundbot';
const DISCORD_VOICE_CHANNEL_ID = '1033659964457230392';

// Cookie management functions
function setCookie(name, value, days = 365) {
    const expires = new Date();
    expires.setTime(expires.getTime() + days * 24 * 60 * 60 * 1000);
    document.cookie = name + '=' + encodeURIComponent(value) + ';expires=' + expires.toUTCString() + ';path=/';
}

function getCookie(name) {
    const nameEQ = name + '=';
    const ca = document.cookie.split(';');
    for (let i = 0; i < ca.length; i++) {
        let c = ca[i];
        while (c.charAt(0) === ' ') c = c.substring(1, c.length);
        if (c.indexOf(nameEQ) === 0) return decodeURIComponent(c.substring(nameEQ.length, c.length));
    }
    return null;
}

function saveUsername() {
    const username = document.getElementById('username').value;
    setCookie('soundboard_username', username);
}

function loadUsername() {
    const username = getCookie('soundboard_username');
    if (username) {
        document.getElementById('username').value = username;
    }
}

async function jsonRpcCall(url, method, params) {
    response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', },
        body: JSON.stringify({ jsonrpc: '2.0', method: method, params: params, id: 1 }),
    })

    const { result, error } = await response.json();

    return result;
}

async function playFile(name) {
    const username = document.getElementById('username').value || 'Anonymous';
    await jsonRpcCall(RPC_URL, 'play', { 'channelid': DISCORD_VOICE_CHANNEL_ID, 'query': name, 'user_name': username });
}

async function stopPlayback() {
    await jsonRpcCall(RPC_URL, 'stop', { 'channelid': DISCORD_VOICE_CHANNEL_ID });
}

async function playSpecifiedFile() {
    await playFile(document.getElementById('fname').value);
}

async function playIfEnter(event) {
    if (event.keyCode === 13) {
        await playSpecifiedFile();
    }
}

async function listFiles() {
    return await jsonRpcCall(RPC_URL, 'list', {});
}

async function searchFiles(query) {
    return await jsonRpcCall(RPC_URL, 'search', { 'query': query });
}

var ALL_FILES;

async function fetchAutoComplete() {
    ALL_FILES = await listFiles();
}

async function setupAutoComplete() {
    await fetchAutoComplete();

    $('#fname').autoComplete({
        resolver: 'custom', minLength: 1, preventEnter: true,
        events: {
            search: async function (query, callback) {
                callback(ALL_FILES.filter(file => file.toLowerCase().includes(query.toLowerCase())));
                // callback(await searchFiles(query));
            }
        }
    });
}



let wakeLock = null;

window.onload = async function () {
    loadUsername();
    await setupAutoComplete();

    wakeLock = await navigator.wakeLock.request('screen');
};
