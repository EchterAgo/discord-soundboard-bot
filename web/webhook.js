async function playFile(name) {
    const response = await fetch('https://host/rpc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', },
        body: JSON.stringify({
            jsonrpc: '2.0',
            method: `play`,
            params: {
                'channelid': '1033659964457230392',
                'query': name
            },
            id: 1
        }),
      }
    );

    const { result, error } = await response.json();
}

async function playSpecifiedFile() {
    await playFile(document.getElementById('fname').value);
}

async function playIfEnter(event) {
    if(event.keyCode === 13) {
        await playSpecifiedFile();
    }
}

async function listFiles(query) {
    const response = await fetch('https://host/rpc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', },
        body: JSON.stringify({
            jsonrpc: '2.0',
            method: `search`,
            params: {'query': query},
            id: 1
        }),
      }
    );

    const { result, error } = await response.json();

    return result;
}

async function setupAutoComplete() {
    $('#fname').autoComplete({
        resolver: 'custom',
        minLength: 1,
        preventEnter: true,
        events: {
            search: async function (qry, callback) {
                const files = await listFiles(qry);
                callback(files);
            }
        }
    });
}

window.onload = async function() {
    await setupAutoComplete();
};
