const RPC_URL = 'https://host/rpc';
const DISCORD_VOICE_CHANNEL_ID = '1234567890';

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
    await jsonRpcCall(RPC_URL, 'play', { 'channelid': DISCORD_VOICE_CHANNEL_ID, 'query': name });
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

window.onload = async function () {
    await setupAutoComplete();
};
