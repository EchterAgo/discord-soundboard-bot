// function playFile(name) {
//     var request = new XMLHttpRequest();
//     request.open("POST", "https://discord.com/api/webhooks/1/2");
//     request.setRequestHeader('Content-type', 'application/json');
//     request.send(JSON.stringify({
//         username: "Soundboard",
//         avatar_url: "",
//         content: `!play ${name}`
//     }));
// }

async function playFile(name) {
    var jsonData = {
        jsonrpc: '2.0',
        method: `play`,
        params: {
            'channelid': '1033659964457230392',
            'query': name
        },
        id: 1
    };

    const response = await fetch('https://host/rpc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', },
        mode: 'no-cors',
        body: JSON.stringify(jsonData),
      }
    );

    const { result, error } = await response.json();
}
