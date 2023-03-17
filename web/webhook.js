function playFile(name) {
    var request = new XMLHttpRequest();
    request.open("POST", "https://discord.com/api/webhooks/1/2");
    request.setRequestHeader('Content-type', 'application/json');
    request.send(JSON.stringify({
        username: "Soundboard",
        avatar_url: "",
        content: `!play ${name}`
    }));
}
