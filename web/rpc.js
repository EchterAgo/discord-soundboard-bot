const WS_URL = 'wss://apollo.loping.net/ws';
const DISCORD_VOICE_CHANNEL_ID = '1033659964457230392';

// WebSocket connection
let ws = null;
let wsReconnectTimer = null;
let queueUpdateCallbacks = [];
let wsReadyPromise = null;
let wsReadyResolve = null;

// Register callback for queue updates
function onQueueUpdate(callback) {
    queueUpdateCallbacks.push(callback);
}

// Initialize WebSocket connection
function initWebSocket() {
    if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
        return wsReadyPromise; // Already connected or connecting
    }
    
    // Create a new ready promise
    wsReadyPromise = new Promise((resolve) => {
        wsReadyResolve = resolve;
    });
    
    ws = new WebSocket(WS_URL);
    
    ws.onopen = () => {
        console.log('WebSocket connected');
        if (wsReconnectTimer) {
            clearTimeout(wsReconnectTimer);
            wsReconnectTimer = null;
        }
        // Resolve the ready promise
        if (wsReadyResolve) {
            wsReadyResolve();
            wsReadyResolve = null;
        }
    };
    
    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            
            // Handle queue updates
            if (data.type === 'queue_update') {
                queueUpdateCallbacks.forEach(callback => callback(data));
            }
            // Handle JSON-RPC responses (if we send commands via WebSocket)
            else if (data.result !== undefined || data.error !== undefined) {
                // Handle RPC response
                console.log('RPC response:', data);
            }
        } catch (e) {
            console.error('Error parsing WebSocket message:', e);
        }
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    ws.onclose = () => {
        console.log('WebSocket disconnected');
        ws = null;
        
        // Reset ready promise
        wsReadyPromise = null;
        wsReadyResolve = null;
        
        // Reconnect after 2 seconds
        if (!wsReconnectTimer) {
            wsReconnectTimer = setTimeout(() => {
                wsReconnectTimer = null;
                initWebSocket();
            }, 2000);
        }
    };
    
    return wsReadyPromise;
}

// Send JSON-RPC command via WebSocket
async function jsonRpcCallWs(method, params) {
    // Wait for WebSocket to be ready
    if (wsReadyPromise) {
        await wsReadyPromise;
    }
    
    return new Promise((resolve, reject) => {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            reject(new Error('WebSocket not connected'));
            return;
        }
        
        const id = Math.random().toString(36).substring(7);
        const request = {
            jsonrpc: '2.0',
            method: method,
            params: params,
            id: id
        };
        
        // Set up one-time listener for response
        const messageHandler = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.id === id) {
                    ws.removeEventListener('message', messageHandler);
                    if (data.error) {
                        reject(new Error(data.error.message || 'RPC error'));
                    } else {
                        resolve(data.result);
                    }
                }
            } catch (e) {
                ws.removeEventListener('message', messageHandler);
                reject(e);
            }
        };
        
        ws.addEventListener('message', messageHandler);
        ws.send(JSON.stringify(request));
        
        // Timeout after 10 seconds
        setTimeout(() => {
            ws.removeEventListener('message', messageHandler);
            reject(new Error('RPC timeout'));
        }, 10000);
    });
}

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
    const usernameElement = document.getElementById('username');
    if (username && usernameElement) {
        usernameElement.value = username;
    }
}



async function playFile(name) {
    const username = document.getElementById('username').value || 'Anonymous';
    
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        throw new Error('WebSocket not connected');
    }
    
    await jsonRpcCallWs('play', { 
        'channelid': DISCORD_VOICE_CHANNEL_ID, 
        'query': name, 
        'user_name': username 
    });
}

async function stopPlayback() {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        throw new Error('WebSocket not connected');
    }
    
    await jsonRpcCallWs('stop', { 'channelid': DISCORD_VOICE_CHANNEL_ID });
}

async function removeQueueItem(userId, itemIndex) {
    try {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            throw new Error('WebSocket not connected');
        }
        
        await jsonRpcCallWs('remove_queue_item', { 
            'channelid': DISCORD_VOICE_CHANNEL_ID, 
            'user_id': userId, 
            'item_index': itemIndex 
        });
        // No need to manually refresh - WebSocket will push update
    } catch (error) {
        console.error('Failed to remove queue item:', error);
        alert('Failed to remove queue item: ' + error.message);
    }
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
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        throw new Error('WebSocket not connected');
    }
    return await jsonRpcCallWs('list', {});
}

async function searchFiles(query) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        throw new Error('WebSocket not connected');
    }
    return await jsonRpcCallWs('search', { 'query': query });
}

async function getQueueStatus() {
    try {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            throw new Error('WebSocket not connected');
        }
        return await jsonRpcCallWs('queue_status', { 'channelid': DISCORD_VOICE_CHANNEL_ID });
    } catch (error) {
        console.error('Failed to get queue status:', error);
        return null;
    }
}

function updateQueueDisplay(status) {
    if (!status) {
        document.getElementById('status-badge').textContent = 'Error';
        document.getElementById('status-badge').className = 'badge badge-danger float-right';
        document.getElementById('queue-container').innerHTML = '<p class="text-danger">Failed to fetch queue status</p>';
        return;
    }

    // Update status badge
    const statusBadge = document.getElementById('status-badge');
    if (!status.connected) {
        statusBadge.textContent = 'Not Connected';
        statusBadge.className = 'badge badge-secondary float-right';
    } else if (status.is_playing) {
        statusBadge.textContent = 'Playing';
        statusBadge.className = 'badge badge-success float-right';
    } else {
        statusBadge.textContent = 'Connected (Idle)';
        statusBadge.className = 'badge badge-info float-right';
    }

    // Build queue HTML
    let html = '';

    // Show active streams
    if (status.active_streams && status.active_streams.length > 0) {
        html += '<div class="mb-3"><h6>🎵 Currently Playing:</h6>';
        status.active_streams.forEach(stream => {
            const filename = stream.filepath.split('/').pop();
            html += `
                <div class="alert alert-success mb-2" role="alert">
                    <strong>${escapeHtml(stream.user_name)}</strong>: ${escapeHtml(filename)}
                </div>
            `;
        });
        html += '</div>';
    }

    // Show queued items
    if (status.user_queues && status.user_queues.length > 0) {
        html += '<div><h6>📋 Queued Sounds:</h6>';
        html += `<p class="text-muted small">Total: ${status.total_queued} item(s) from ${status.user_queues.length} user(s)</p>`;
        
        status.user_queues.forEach(userQueue => {
            html += `
                <div class="card mb-2">
                    <div class="card-header py-1">
                        <strong>${escapeHtml(userQueue.user_name)}</strong>
                        <span class="badge badge-primary float-right">${userQueue.count}</span>
                    </div>
                    <div class="card-body py-2">
                        <ul class="list-unstyled mb-0">
            `;
            
            userQueue.items.forEach((item, index) => {
                html += `
                    <li class="queue-item d-flex justify-content-between align-items-center mb-1">
                        <span class="small"><span class="text-muted">${index + 1}.</span> ${escapeHtml(item.query)}</span>
                        <button class="btn btn-sm btn-outline-danger" onclick="removeQueueItem(${userQueue.user_id}, ${index})" title="Remove">
                            ✕
                        </button>
                    </li>
                `;
            });
            
            html += `
                        </ul>
                    </div>
                </div>
            `;
        });
        html += '</div>';
    } else if (!status.active_streams || status.active_streams.length === 0) {
        html = '<p class="text-muted">Queue is empty</p>';
    }

    document.getElementById('queue-container').innerHTML = html;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

let queueUpdateInterval = null;

async function startQueuePolling() {
    // Set up WebSocket listener for real-time updates
    onQueueUpdate((status) => {
        updateQueueDisplay(status);
    });
    
    // Initialize WebSocket connection
    initWebSocket();
}

function stopQueuePolling() {
    if (queueUpdateInterval) {
        clearInterval(queueUpdateInterval);
        queueUpdateInterval = null;
    }
    
    // Close WebSocket connection
    if (ws) {
        ws.close();
        ws = null;
    }
}

async function refreshQueue() {
    const status = await getQueueStatus();
    updateQueueDisplay(status);
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
    await startQueuePolling();

    wakeLock = await navigator.wakeLock.request('screen');
};

// Stop polling when page is hidden to save resources
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopQueuePolling();
    } else {
        startQueuePolling();
    }
});
