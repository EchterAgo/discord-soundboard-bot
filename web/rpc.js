const WS_URL = 'wss://apollo.loping.net/ws';

// WebSocket connection
let ws = null;
let wsReconnectTimer = null;
let wsReadyPromise = null;
let wsReadyResolve = null;

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

            // Handle JSON-RPC responses
            if (data.result !== undefined || data.error !== undefined) {
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
