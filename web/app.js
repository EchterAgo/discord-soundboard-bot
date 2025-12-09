const { createApp } = Vue;

// RPC Client
const WS_URL = 'wss://apollo.loping.net/ws';
const DISCORD_VOICE_CHANNEL_ID = '1033659964457230392';

// Predefined colors - always available, not saved to config
const PREDEFINED_COLORS = [
    { name: 'primary', rgb: '' },
    { name: 'secondary', rgb: '' },
    { name: 'success', rgb: '' },
    { name: 'danger', rgb: '' },
    { name: 'warning', rgb: '' },
    { name: 'info', rgb: '' },
    { name: 'dark', rgb: '' }
];

// Default audio filter values
const DEFAULT_AUDIO_FILTERS = {
    volume_boost: 1.0,
    compressor: false,
    bass_boost: 0,
    treble_boost: 0,
    highpass: 0,
    lowpass: 0,
    chorus: false,
    earwax: false,
    rubberband_pitch: 0,
    rubberband_tempo: 1.0,
    silence_remove: false,
    tremolo_freq: 0,
    tremolo_depth: 0,
    vibrato_freq: 0,
    vibrato_depth: 0,
    supereq_bands: [0, 0, 0, 0, 0, 0, 0, 0, 0]
};

// WebSocket connection management
let websocket = null;
let wsReconnectTimer = null;
let wsCallbacks = new Map();
let wsReadyPromise = null;
let wsReadyResolve = null;

// Clock synchronization
let clockOffset = 0; // Estimated offset: server_time - client_time (in seconds)
let lastPingTime = 0;
let lastPingId = 0;
let pingInterval = null;

function initWebSocket(onQueueUpdate, onFileListUpdate, onConfigUpdate, onConnected) {
    if (websocket && (websocket.readyState === WebSocket.CONNECTING || websocket.readyState === WebSocket.OPEN)) {
        return wsReadyPromise;
    }

    // Create a new ready promise
    wsReadyPromise = new Promise((resolve) => {
        wsReadyResolve = resolve;
    });

    websocket = new WebSocket(WS_URL);

    websocket.onopen = () => {
        console.log('[WebSocket] Connected');
        if (wsReconnectTimer) {
            clearTimeout(wsReconnectTimer);
            wsReconnectTimer = null;
        }
        // Resolve the ready promise
        if (wsReadyResolve) {
            wsReadyResolve();
            wsReadyResolve = null;
        }
        // Start periodic ping for clock synchronization
        startPeriodicPing();
        // Call the onConnected callback (for re-registering username on reconnect)
        if (onConnected) {
            onConnected();
        }
    };

    websocket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            // Handle pong responses to calculate RTT and clock offset
            if (data.type === 'pong') {
                const clientReceiveTime = Date.now() / 1000; // Current time in seconds (T4)
                const pongId = data.ping_id;
                
                // Ignore pongs that don't match our last ping (old/delayed responses)
                if (pongId !== lastPingId) {
                    console.log(`[Clock Sync] Ignoring old pong (ID ${pongId}, expected ${lastPingId})`);
                    return;
                }
                
                const clientSendTime = lastPingTime; // When we sent ping (T1)
                const rtt = clientReceiveTime - clientSendTime; // RTT in seconds
                const serverTime = data.server_time; // Server timestamp when pong was sent (T3)
                
                // Discard measurements with abnormally high RTT (> 100ms)
                if (rtt > 0.1) {
                    console.log(`[Clock Sync] High RTT: ${(rtt * 1000).toFixed(1)}ms (network issue or clock drift)`);
                    return;
                }
                
                // Estimate clock offset using midpoint method
                // Assume server captured timestamp at midpoint of round trip
                // clock_offset = server_time - client_midpoint
                const clientMidpoint = (clientSendTime + clientReceiveTime) / 2;
                const estimatedOffset = serverTime - clientMidpoint;
                
                // Use adaptive smoothing: faster convergence when offset is uninitialized or way off
                let alpha; // Weight for new measurement (0-1, higher = faster convergence)
                if (clockOffset === 0) {
                    // First good measurement: use it directly
                    clockOffset = estimatedOffset;
                    const offsetMs = Math.round(clockOffset * 1000);
                    console.log(`[Clock Sync] Initial offset: ${(clockOffset * 1000).toFixed(1)}ms`);
                    if (window.vueApp) window.vueApp.clockOffsetMs = offsetMs;
                    // Send to server
                    if (websocket && websocket.readyState === WebSocket.OPEN) {
                        try {
                            rpcCall('update_clock_offset', { offset_ms: offsetMs }).catch(() => { });
                        } catch (e) { }
                    }
                    return;
                } else if (Math.abs(estimatedOffset - clockOffset) > 0.05) {
                    // Large deviation (>50ms): fast convergence
                    alpha = 0.5;
                } else {
                    // Small deviation: slow smoothing for stability
                    alpha = 0.2;
                }
                
                clockOffset = clockOffset * (1 - alpha) + estimatedOffset * alpha;
                
                const offsetMs = Math.round(clockOffset * 1000);
                
                // Update Vue data for display if app is mounted
                if (window.vueApp) {
                    window.vueApp.clockOffsetMs = offsetMs;
                }
                
                console.log(`[Clock Sync] RTT: ${(rtt * 1000).toFixed(1)}ms, Estimated: ${(estimatedOffset * 1000).toFixed(1)}ms, Smoothed: ${(clockOffset * 1000).toFixed(1)}ms, α=${alpha.toFixed(1)}`);
                
                // Send clock offset to server (throttled to prevent spam)
                if (websocket && websocket.readyState === WebSocket.OPEN) {
                    try {
                        rpcCall('update_clock_offset', { offset_ms: offsetMs }).catch(() => { });
                    } catch (e) {
                        // Silently ignore
                    }
                }
                
                // Send RTT back to server via RPC so other clients see it
                if (websocket && websocket.readyState === WebSocket.OPEN) {
                    try {
                        rpcCall('update_ping', { ping_ms: rtt * 1000 }).catch(() => { });
                    } catch (e) {
                        // Silently ignore ping update failures
                    }
                }
                return; // Don't process as regular message
            }

            // Handle queue updates
            if (data.type === 'queue_update') {
                // Debug log to see active streams with progress
                if (data.active_streams && data.active_streams.length > 0) {
                    console.log('[Queue] Active streams:', data.active_streams.map(s => ({
                        user: s.user_name,
                        file: s.filepath.split('/').pop(),
                        progress: s.progress
                    })));
                }
                if (onQueueUpdate) {
                    onQueueUpdate(data);
                }
                // Update connected users count if available
                if (data.connected_users !== undefined) {
                    // This will be updated via the onQueueUpdate callback
                }
            }
            // Handle file list updates
            else if (data.type === 'file_list_update') {
                if (onFileListUpdate) {
                    onFileListUpdate(data.files);
                }
            }
            // Handle config updates
            else if (data.type === 'config_update') {
                if (onConfigUpdate) {
                    onConfigUpdate(data.user_name);
                }
            }
            // Handle JSON-RPC responses
            else if (data.id && wsCallbacks.has(data.id)) {
                const { resolve, reject } = wsCallbacks.get(data.id);
                wsCallbacks.delete(data.id);

                if (data.error) {
                    reject(new Error(data.error.message || 'RPC Error'));
                } else {
                    resolve(data.result);
                }
            }
        } catch (e) {
            console.error('[WebSocket] Error parsing message:', e);
        }
    };

    websocket.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
    };

    websocket.onclose = () => {
        console.log('[WebSocket] Disconnected');
        websocket = null;

        // Stop periodic ping
        if (pingInterval) {
            clearInterval(pingInterval);
            pingInterval = null;
        }

        // Reset ready promise
        wsReadyPromise = null;
        wsReadyResolve = null;

        // Reconnect after 2 seconds
        if (!wsReconnectTimer) {
            wsReconnectTimer = setTimeout(() => {
                wsReconnectTimer = null;
                initWebSocket(onQueueUpdate, onFileListUpdate, onConfigUpdate, onConnected);
            }, 2000);
        }
    };

    return wsReadyPromise;
}

function startPeriodicPing() {
    // Clear any existing interval
    if (pingInterval) {
        clearInterval(pingInterval);
    }
    
    // Send initial ping immediately
    sendPing();
    
    // Then ping every 5 seconds for clock sync
    pingInterval = setInterval(() => {
        sendPing();
    }, 5000);
}

function sendPing() {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        lastPingTime = Date.now() / 1000; // Store in seconds
        lastPingId++; // Increment ping ID
        websocket.send(JSON.stringify({ type: 'ping', ping_id: lastPingId }));
    }
}

async function rpcCallWs(method, params = {}) {
    return new Promise((resolve, reject) => {
        if (!websocket || websocket.readyState !== WebSocket.OPEN) {
            reject(new Error('WebSocket not connected'));
            return;
        }

        const id = Date.now() + Math.random();
        const request = {
            jsonrpc: '2.0',
            method: method,
            params: params,
            id: id
        };

        wsCallbacks.set(id, { resolve, reject });
        websocket.send(JSON.stringify(request));

        // Timeout after 10 seconds
        setTimeout(() => {
            if (wsCallbacks.has(id)) {
                wsCallbacks.delete(id);
                reject(new Error('RPC timeout'));
            }
        }, 10000);
    });
}

async function rpcCall(method, params = {}) {
    // Wait for WebSocket to be ready
    if (wsReadyPromise) {
        await wsReadyPromise;
    }

    if (!websocket || websocket.readyState !== WebSocket.OPEN) {
        throw new Error('WebSocket not connected');
    }

    return await rpcCallWs(method, params);
}

const app = createApp({
    data() {
        return {
            username: localStorage.getItem('username') || '',
            theme: localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
            bootstrapTheme: localStorage.getItem('bootstrapTheme') || '',
            bootswatchThemes: [],
            playMode: localStorage.getItem('playMode') || 'instant', // 'instant', 'queue', 'next'
            config: {
                buttons: [],
                grid_size: { cols: 6, rows: 4 },
                recent_sounds: [],
                favorites: [],
                custom_colors: [],
                queue_list_as_overlay: true,
                version: "1.0",
                created_at: null,
                updated_at: null
            },
            PREDEFINED_COLORS: PREDEFINED_COLORS,
            allSounds: [],
            connectedUsers: 0,
            connectedUserList: [],
            showConnectedUsers: false,
            clockOffsetMs: 0, // Clock offset in milliseconds for display
            queueStatus: {
                connected: false,
                is_playing: false,
                active_streams: [],
                user_queues: [],
                total_queued: 0
            },
            searchQuery: '',
            showSettings: false,
            showHelp: false,
            showQueue: localStorage.getItem('showQueue') === 'true',
            isFullscreen: false,
            activeView: 'buttons', // 'buttons', 'recent', 'all'
            editingButton: null,
            queueRefreshInterval: null,
            sortable: null,
            showSoundDropdown: false,
            selectedSoundIndex: -1,
            editingButtonBackup: null,
            isNewButton: false,
            showSearchDropdown: false,
            selectedSearchIndex: -1,
            wakeLock: null,
            editMode: false,
            expandedQueues: {},
            modifierKeys: {
                ctrl: false,
                shift: false
            },
            focusedButtonIndex: -1,
            iconLibrary: 'bootstrap',
            iconSearchQuery: ''
        };
    },
    computed: {
        buttonColors() {
            // Combine predefined colors with custom colors
            const customColors = this.config.custom_colors || [];
            return [...PREDEFINED_COLORS, ...customColors];
        },
        getColorClassName(color) {
            if (typeof color === 'string') return color;
            return color.name;
        },
        bootstrapIcons() {
            return this.getBootstrapIcons();
        },
        fontAwesomeIcons() {
            return this.getFontAwesomeIcons();
        },
        materialIcons() {
            return this.getMaterialIcons();
        },
        semanticIcons() {
            return this.getSemanticIcons();
        },
        currentIconLibraryTotal() {
            const icons = {
                'bootstrap': this.bootstrapIcons,
                'fontawesome': this.fontAwesomeIcons,
                'material': this.materialIcons,
                'semantic': this.semanticIcons
            };
            return icons[this.iconLibrary]?.length || 0;
        },
        filteredIconList() {
            const icons = {
                'bootstrap': this.bootstrapIcons,
                'fontawesome': this.fontAwesomeIcons,
                'material': this.materialIcons,
                'semantic': this.semanticIcons
            }[this.iconLibrary] || [];

            let filtered = icons;
            if (this.iconSearchQuery) {
                const query = this.iconSearchQuery.toLowerCase();
                filtered = icons.filter(icon => icon.name.toLowerCase().includes(query));
            }

            // If currently editing a button with an icon, place it at the beginning
            let result = [];
            if (this.editingButton !== null && this.config.buttons[this.editingButton].icon) {
                const selectedIcon = this.config.buttons[this.editingButton].icon;
                const selectedIconObj = icons.find(icon => (icon.text || icon.class) === selectedIcon);
                if (selectedIconObj) {
                    result.push(selectedIconObj);
                }
                // Add filtered icons excluding the selected one
                result.push(...filtered.filter(icon => (icon.text || icon.class) !== selectedIcon));
            } else {
                result = filtered;
            }

            return result.slice(0, 200);
        },
        gridStyle() {
            return {
                'grid-template-columns': `repeat(${this.config.grid_size.cols}, 1fr)`,
                'gap': '10px',
                'display': 'grid'
            };
        },
        playModeInfo() {
            const modes = {
                instant: { label: 'Instant', icon: 'bi-play-fill', color: 'danger' },
                queue: { label: 'Queue', icon: 'bi-list-ul', color: 'primary' },
                next: { label: 'Play Next', icon: 'bi-skip-forward-fill', color: 'warning' }
            };

            // Show effective mode based on modifier keys
            let effectiveMode = this.playMode;
            if (this.modifierKeys.ctrl && this.modifierKeys.shift) {
                effectiveMode = 'next';
            } else if (this.modifierKeys.ctrl) {
                effectiveMode = 'instant';
            } else if (this.modifierKeys.shift) {
                effectiveMode = 'queue';
            }

            return modes[effectiveMode];
        },
        filteredSounds() {
            // In 'all' view with no search query, sort alphabetically without prioritizing recent
            if (this.activeView === 'all' && !this.searchQuery) {
                return [...this.allSounds].sort((a, b) => a.localeCompare(b));
            }
            return this.filterAndPrioritize(this.searchQuery, this.allSounds);
        },
        filteredEditSounds() {
            if (this.editingButton === null) return [];
            const currentSound = this.config.buttons[this.editingButton].sound;
            return this.filterAndPrioritize(currentSound, this.allSounds);
        }
    },
    watch: {
        'queueStatus.is_playing'(isPlaying) {
            this.updateFavicon(isPlaying);
        },
        'queueStatus.connected'(isConnected) {
            // Update favicon when connection status changes
            this.updateFavicon(this.queueStatus.is_playing);
        }
    },
    methods: {
        getBootstrapIcons() {
            // Comprehensive list of Bootstrap Icons
            const icons = [
                '123', 'alarm-fill', 'alarm', 'align-bottom', 'align-center', 'align-end', 'align-middle', 'align-start', 'align-top', 'alt', 'app-indicator', 'app', 'archive-fill', 'archive', 'arrow-90deg-down', 'arrow-90deg-left', 'arrow-90deg-right', 'arrow-90deg-up', 'arrow-bar-down', 'arrow-bar-left', 'arrow-bar-right', 'arrow-bar-up', 'arrow-clockwise', 'arrow-counterclockwise', 'arrow-down-circle-fill', 'arrow-down-circle', 'arrow-down-left-circle-fill', 'arrow-down-left-circle', 'arrow-down-left-square-fill', 'arrow-down-left-square', 'arrow-down-left', 'arrow-down-right-circle-fill', 'arrow-down-right-circle', 'arrow-down-right-square-fill', 'arrow-down-right-square', 'arrow-down-right', 'arrow-down-short', 'arrow-down-square-fill', 'arrow-down-square', 'arrow-down-up', 'arrow-down', 'arrow-left-circle-fill', 'arrow-left-circle', 'arrow-left-right', 'arrow-left-short', 'arrow-left-square-fill', 'arrow-left-square', 'arrow-left', 'arrow-repeat', 'arrow-return-left', 'arrow-return-right', 'arrow-right-circle-fill', 'arrow-right-circle', 'arrow-right-short', 'arrow-right-square-fill', 'arrow-right-square', 'arrow-right', 'arrow-up-circle-fill', 'arrow-up-circle', 'arrow-up-left-circle-fill', 'arrow-up-left-circle', 'arrow-up-left-square-fill', 'arrow-up-left-square', 'arrow-up-left', 'arrow-up-right-circle-fill', 'arrow-up-right-circle', 'arrow-up-right-square-fill', 'arrow-up-right-square', 'arrow-up-right', 'arrow-up-short', 'arrow-up-square-fill', 'arrow-up-square', 'arrow-up', 'asterisk', 'at', 'award-fill', 'award', 'back', 'backspace-fill', 'backspace-reverse-fill', 'backspace-reverse', 'backspace', 'badge-3d-fill', 'badge-3d', 'badge-4k-fill', 'badge-4k', 'badge-8k-fill', 'badge-8k', 'badge-ad-fill', 'badge-ad', 'badge-ar-fill', 'badge-ar', 'badge-cc-fill', 'badge-cc', 'badge-hd-fill', 'badge-hd', 'badge-tm-fill', 'badge-tm', 'badge-vo-fill', 'badge-vo', 'badge-vr-fill', 'badge-vr', 'badge-wc-fill', 'badge-wc', 'bag-check-fill', 'bag-check', 'bag-dash-fill', 'bag-dash', 'bag-fill', 'bag-plus-fill', 'bag-plus', 'bag-x-fill', 'bag-x', 'bag', 'balloon-fill', 'balloon-heart-fill', 'balloon-heart', 'balloon', 'bank', 'bank2', 'bar-chart-fill', 'bar-chart-line-fill', 'bar-chart-line', 'bar-chart-steps', 'bar-chart', 'basket-fill', 'basket', 'basket2-fill', 'basket2', 'basket3-fill', 'basket3', 'battery-charging', 'battery-full', 'battery-half', 'battery', 'bell-fill', 'bell-slash-fill', 'bell-slash', 'bell', 'bezier', 'bezier2', 'bicycle', 'binoculars-fill', 'binoculars', 'blockquote-left', 'blockquote-right', 'book-fill', 'book-half', 'book', 'bookmark-check-fill', 'bookmark-check', 'bookmark-dash-fill', 'bookmark-dash', 'bookmark-fill', 'bookmark-heart-fill', 'bookmark-heart', 'bookmark-plus-fill', 'bookmark-plus', 'bookmark-star-fill', 'bookmark-star', 'bookmark-x-fill', 'bookmark-x', 'bookmark', 'bookmarks-fill', 'bookmarks', 'bookshelf', 'bootstrap-fill', 'bootstrap-reboot', 'bootstrap', 'border-all', 'border-bottom', 'border-center', 'border-inner', 'border-left', 'border-middle', 'border-outer', 'border-right', 'border-style', 'border-top', 'border-width', 'border', 'bounding-box-circles', 'bounding-box', 'box-arrow-down-left', 'box-arrow-down-right', 'box-arrow-down', 'box-arrow-in-down-left', 'box-arrow-in-down-right', 'box-arrow-in-down', 'box-arrow-in-left', 'box-arrow-in-right', 'box-arrow-in-up-left', 'box-arrow-in-up-right', 'box-arrow-in-up', 'box-arrow-left', 'box-arrow-right', 'box-arrow-up-left', 'box-arrow-up-right', 'box-arrow-up', 'box-seam', 'box', 'box2-fill', 'box2-heart-fill', 'box2-heart', 'box2', 'boxes', 'braces-asterisk', 'braces', 'bricks', 'briefcase-fill', 'briefcase', 'brightness-alt-high-fill', 'brightness-alt-high', 'brightness-alt-low-fill', 'brightness-alt-low', 'brightness-high-fill', 'brightness-high', 'brightness-low-fill', 'brightness-low', 'broadcast-pin', 'broadcast', 'brush-fill', 'brush', 'bucket-fill', 'bucket', 'bug-fill', 'bug', 'building', 'bullseye', 'calculator-fill', 'calculator', 'calendar-check-fill', 'calendar-check', 'calendar-date-fill', 'calendar-date', 'calendar-day-fill', 'calendar-day', 'calendar-event-fill', 'calendar-event', 'calendar-fill', 'calendar-minus-fill', 'calendar-minus', 'calendar-month-fill', 'calendar-month', 'calendar-plus-fill', 'calendar-plus', 'calendar-range-fill', 'calendar-range', 'calendar-week-fill', 'calendar-week', 'calendar-x-fill', 'calendar-x', 'calendar', 'calendar2-check-fill', 'calendar2-check', 'calendar2-date-fill', 'calendar2-date', 'calendar2-day-fill', 'calendar2-day', 'calendar2-event-fill', 'calendar2-event', 'calendar2-fill', 'calendar2-minus-fill', 'calendar2-minus', 'calendar2-month-fill', 'calendar2-month', 'calendar2-plus-fill', 'calendar2-plus', 'calendar2-range-fill', 'calendar2-range', 'calendar2-week-fill', 'calendar2-week', 'calendar2-x-fill', 'calendar2-x', 'calendar2', 'calendar3-event-fill', 'calendar3-event', 'calendar3-fill', 'calendar3-range-fill', 'calendar3-range', 'calendar3-week-fill', 'calendar3-week', 'calendar3', 'calendar4-event', 'calendar4-range', 'calendar4-week', 'calendar4', 'camera-fill', 'camera-reels-fill', 'camera-reels', 'camera-video-fill', 'camera-video-off-fill', 'camera-video-off', 'camera-video', 'camera', 'camera2', 'capslock-fill', 'capslock', 'card-checklist', 'card-heading', 'card-image', 'card-list', 'card-text', 'caret-down-fill', 'caret-down-square-fill', 'caret-down-square', 'caret-down', 'caret-left-fill', 'caret-left-square-fill', 'caret-left-square', 'caret-left', 'caret-right-fill', 'caret-right-square-fill', 'caret-right-square', 'caret-right', 'caret-up-fill', 'caret-up-square-fill', 'caret-up-square', 'caret-up', 'cart-check-fill', 'cart-check', 'cart-dash-fill', 'cart-dash', 'cart-fill', 'cart-plus-fill', 'cart-plus', 'cart-x-fill', 'cart-x', 'cart', 'cart2', 'cart3', 'cart4', 'cash-coin', 'cash-stack', 'cash', 'cast', 'chat-dots-fill', 'chat-dots', 'chat-fill', 'chat-left-dots-fill', 'chat-left-dots', 'chat-left-fill', 'chat-left-quote-fill', 'chat-left-quote', 'chat-left-text-fill', 'chat-left-text', 'chat-left', 'chat-quote-fill', 'chat-quote', 'chat-right-dots-fill', 'chat-right-dots', 'chat-right-fill', 'chat-right-quote-fill', 'chat-right-quote', 'chat-right-text-fill', 'chat-right-text', 'chat-right', 'chat-square-dots-fill', 'chat-square-dots', 'chat-square-fill', 'chat-square-quote-fill', 'chat-square-quote', 'chat-square-text-fill', 'chat-square-text', 'chat-square', 'chat-text-fill', 'chat-text', 'chat', 'check-all', 'check-circle-fill', 'check-circle', 'check-square-fill', 'check-square', 'check', 'check2-all', 'check2-circle', 'check2-square', 'check2', 'chevron-bar-contract', 'chevron-bar-down', 'chevron-bar-expand', 'chevron-bar-left', 'chevron-bar-right', 'chevron-bar-up', 'chevron-compact-down', 'chevron-compact-left', 'chevron-compact-right', 'chevron-compact-up', 'chevron-contract', 'chevron-double-down', 'chevron-double-left', 'chevron-double-right', 'chevron-double-up', 'chevron-down', 'chevron-expand', 'chevron-left', 'chevron-right', 'chevron-up', 'circle-fill', 'circle-half', 'circle-square', 'circle', 'clipboard-check-fill', 'clipboard-check', 'clipboard-data-fill', 'clipboard-data', 'clipboard-fill', 'clipboard-minus-fill', 'clipboard-minus', 'clipboard-plus-fill', 'clipboard-plus', 'clipboard-x-fill', 'clipboard-x', 'clipboard', 'clipboard2-check-fill', 'clipboard2-check', 'clipboard2-data-fill', 'clipboard2-data', 'clipboard2-fill', 'clipboard2-minus-fill', 'clipboard2-minus', 'clipboard2-plus-fill', 'clipboard2-plus', 'clipboard2-x-fill', 'clipboard2-x', 'clipboard2', 'clock-fill', 'clock-history', 'clock', 'cloud-arrow-down-fill', 'cloud-arrow-down', 'cloud-arrow-up-fill', 'cloud-arrow-up', 'cloud-check-fill', 'cloud-check', 'cloud-download-fill', 'cloud-download', 'cloud-drizzle-fill', 'cloud-drizzle', 'cloud-fill', 'cloud-fog-fill', 'cloud-fog', 'cloud-fog2-fill', 'cloud-fog2', 'cloud-hail-fill', 'cloud-hail', 'cloud-haze-fill', 'cloud-haze', 'cloud-haze2-fill', 'cloud-lightning-fill', 'cloud-lightning-rain-fill', 'cloud-lightning-rain', 'cloud-lightning', 'cloud-minus-fill', 'cloud-minus', 'cloud-moon-fill', 'cloud-moon', 'cloud-plus-fill', 'cloud-plus', 'cloud-rain-fill', 'cloud-rain-heavy-fill', 'cloud-rain-heavy', 'cloud-rain', 'cloud-slash-fill', 'cloud-slash', 'cloud-sleet-fill', 'cloud-sleet', 'cloud-snow-fill', 'cloud-snow', 'cloud-sun-fill', 'cloud-sun', 'cloud-upload-fill', 'cloud-upload', 'cloud', 'clouds-fill', 'clouds', 'cloudy-fill', 'cloudy', 'code-slash', 'code-square', 'code', 'coin', 'collection-fill', 'collection-play-fill', 'collection-play', 'collection', 'columns-gap', 'columns', 'command', 'compass-fill', 'compass', 'cone-striped', 'cone', 'controller', 'cpu-fill', 'cpu', 'credit-card-2-back-fill', 'credit-card-2-back', 'credit-card-2-front-fill', 'credit-card-2-front', 'credit-card-fill', 'credit-card', 'crop', 'cup-fill', 'cup-straw', 'cup', 'cursor-fill', 'cursor-text', 'cursor', 'dash-circle-dotted', 'dash-circle-fill', 'dash-circle', 'dash-square-dotted', 'dash-square-fill', 'dash-square', 'dash', 'device-hdd-fill', 'device-hdd', 'device-ssd-fill', 'device-ssd', 'diagram-2-fill', 'diagram-2', 'diagram-3-fill', 'diagram-3', 'diamond-fill', 'diamond-half', 'diamond', 'dice-1-fill', 'dice-1', 'dice-2-fill', 'dice-2', 'dice-3-fill', 'dice-3', 'dice-4-fill', 'dice-4', 'dice-5-fill', 'dice-5', 'dice-6-fill', 'dice-6', 'disc-fill', 'disc', 'discord', 'display-fill', 'display', 'distribute-horizontal', 'distribute-vertical', 'door-closed-fill', 'door-closed', 'door-open-fill', 'door-open', 'dot', 'download', 'droplet-fill', 'droplet-half', 'droplet', 'earbuds', 'easel-fill', 'easel', 'egg-fill', 'egg-fried', 'egg', 'eject-fill', 'eject', 'emoji-angry-fill', 'emoji-angry', 'emoji-dizzy-fill', 'emoji-dizzy', 'emoji-expressionless-fill', 'emoji-expressionless', 'emoji-frown-fill', 'emoji-frown', 'emoji-heart-eyes-fill', 'emoji-heart-eyes', 'emoji-laughing-fill', 'emoji-laughing', 'emoji-neutral-fill', 'emoji-neutral', 'emoji-smile-fill', 'emoji-smile-upside-down-fill', 'emoji-smile-upside-down', 'emoji-smile', 'emoji-sunglasses-fill', 'emoji-sunglasses', 'emoji-wink-fill', 'emoji-wink', 'envelope-fill', 'envelope-open-fill', 'envelope-open', 'envelope', 'eraser-fill', 'eraser', 'exclamation-circle-fill', 'exclamation-circle', 'exclamation-diamond-fill', 'exclamation-diamond', 'exclamation-octagon-fill', 'exclamation-octagon', 'exclamation-square-fill', 'exclamation-square', 'exclamation-triangle-fill', 'exclamation-triangle', 'exclamation', 'exclude', 'eye-fill', 'eye-slash-fill', 'eye-slash', 'eye', 'eyedropper', 'eyeglasses', 'file-arrow-down-fill', 'file-arrow-down', 'file-arrow-up-fill', 'file-arrow-up', 'file-bar-graph-fill', 'file-bar-graph', 'file-binary-fill', 'file-binary', 'file-break-fill', 'file-break', 'file-check-fill', 'file-check', 'file-code-fill', 'file-code', 'file-diff-fill', 'file-diff', 'file-earmark-arrow-down-fill', 'file-earmark-arrow-down', 'file-earmark-arrow-up-fill', 'file-earmark-arrow-up', 'file-earmark-bar-graph-fill', 'file-earmark-bar-graph', 'file-earmark-binary-fill', 'file-earmark-binary', 'file-earmark-break-fill', 'file-earmark-break', 'file-earmark-check-fill', 'file-earmark-check', 'file-earmark-code-fill', 'file-earmark-code', 'file-earmark-diff-fill', 'file-earmark-diff', 'file-earmark-easel-fill', 'file-earmark-easel', 'file-earmark-excel-fill', 'file-earmark-excel', 'file-earmark-fill', 'file-earmark-font-fill', 'file-earmark-font', 'file-earmark-image-fill', 'file-earmark-image', 'file-earmark-lock-fill', 'file-earmark-lock', 'file-earmark-lock2-fill', 'file-earmark-lock2', 'file-earmark-medical-fill', 'file-earmark-medical', 'file-earmark-minus-fill', 'file-earmark-minus', 'file-earmark-music-fill', 'file-earmark-music', 'file-earmark-pdf-fill', 'file-earmark-pdf', 'file-earmark-person-fill', 'file-earmark-person', 'file-earmark-play-fill', 'file-earmark-play', 'file-earmark-plus-fill', 'file-earmark-plus', 'file-earmark-post-fill', 'file-earmark-post', 'file-earmark-ppt-fill', 'file-earmark-ppt', 'file-earmark-richtext-fill', 'file-earmark-richtext', 'file-earmark-ruled-fill', 'file-earmark-ruled', 'file-earmark-slides-fill', 'file-earmark-slides', 'file-earmark-spreadsheet-fill', 'file-earmark-spreadsheet', 'file-earmark-text-fill', 'file-earmark-text', 'file-earmark-word-fill', 'file-earmark-word', 'file-earmark-x-fill', 'file-earmark-x', 'file-earmark-zip-fill', 'file-earmark-zip', 'file-earmark', 'file-easel-fill', 'file-easel', 'file-excel-fill', 'file-excel', 'file-fill', 'file-font-fill', 'file-font', 'file-image-fill', 'file-image', 'file-lock-fill', 'file-lock', 'file-lock2-fill', 'file-lock2', 'file-medical-fill', 'file-medical', 'file-minus-fill', 'file-minus', 'file-music-fill', 'file-music', 'file-pdf-fill', 'file-pdf', 'file-person-fill', 'file-person', 'file-play-fill', 'file-play', 'file-plus-fill', 'file-plus', 'file-post-fill', 'file-post', 'file-ppt-fill', 'file-ppt', 'file-richtext-fill', 'file-richtext', 'file-ruled-fill', 'file-ruled', 'file-slides-fill', 'file-slides', 'file-spreadsheet-fill', 'file-spreadsheet', 'file-text-fill', 'file-text', 'file-word-fill', 'file-word', 'file-x-fill', 'file-x', 'file-zip-fill', 'file-zip', 'file', 'files-alt', 'files', 'film', 'filter-circle-fill', 'filter-circle', 'filter-left', 'filter-right', 'filter-square-fill', 'filter-square', 'filter', 'fire', 'flag-fill', 'flag', 'flower1', 'flower2', 'flower3', 'folder-check', 'folder-fill', 'folder-minus', 'folder-plus', 'folder-symlink-fill', 'folder-symlink', 'folder-x', 'folder', 'folder2-open', 'folder2', 'fonts', 'forward-fill', 'forward', 'front', 'fuel-pump-diesel-fill', 'fuel-pump-diesel', 'fuel-pump-fill', 'fuel-pump', 'fullscreen-exit', 'fullscreen', 'funnel-fill', 'funnel', 'gear-fill', 'gear-wide-connected', 'gear-wide', 'gear', 'gem', 'geo-alt-fill', 'geo-alt', 'geo-fill', 'geo', 'gift-fill', 'gift', 'git', 'github', 'globe', 'globe2', 'google', 'graph-down', 'graph-up', 'grid-1x2-fill', 'grid-1x2', 'grid-3x2-gap-fill', 'grid-3x2-gap', 'grid-3x2', 'grid-3x3-gap-fill', 'grid-3x3-gap', 'grid-3x3', 'grid-fill', 'grid', 'grip-horizontal', 'grip-vertical', 'hammer', 'hand-index-fill', 'hand-index-thumb-fill', 'hand-index-thumb', 'hand-index', 'hand-thumbs-down-fill', 'hand-thumbs-down', 'hand-thumbs-up-fill', 'hand-thumbs-up', 'handbag-fill', 'handbag', 'hash', 'hdd-fill', 'hdd-network-fill', 'hdd-network', 'hdd-rack-fill', 'hdd-rack', 'hdd-stack-fill', 'hdd-stack', 'hdd', 'headphones', 'headset', 'heart-fill', 'heart-half', 'heart', 'heptagon-fill', 'heptagon-half', 'heptagon', 'hexagon-fill', 'hexagon-half', 'hexagon', 'hourglass-bottom', 'hourglass-split', 'hourglass-top', 'hourglass', 'house-door-fill', 'house-door', 'house-fill', 'house', 'hr', 'hurricane', 'image-alt', 'image-fill', 'image', 'images', 'inbox-fill', 'inbox', 'inboxes-fill', 'inboxes', 'info-circle-fill', 'info-circle', 'info-square-fill', 'info-square', 'info', 'input-cursor-text', 'input-cursor', 'instagram', 'intersect', 'journal-album', 'journal-arrow-down', 'journal-arrow-up', 'journal-bookmark-fill', 'journal-bookmark', 'journal-check', 'journal-code', 'journal-medical', 'journal-minus', 'journal-plus', 'journal-richtext', 'journal-text', 'journal-x', 'journal', 'journals', 'joystick', 'justify-left', 'justify-right', 'justify', 'kanban-fill', 'kanban', 'key-fill', 'key', 'keyboard-fill', 'keyboard', 'ladder', 'lamp-fill', 'lamp', 'laptop-fill', 'laptop', 'layer-backward', 'layer-forward', 'layers-fill', 'layers-half', 'layers', 'layout-sidebar-inset-reverse', 'layout-sidebar-inset', 'layout-sidebar-reverse', 'layout-sidebar', 'layout-split', 'layout-text-sidebar-reverse', 'layout-text-sidebar', 'layout-text-window-reverse', 'layout-text-window', 'layout-three-columns', 'layout-wtf', 'life-preserver', 'lightbulb-fill', 'lightbulb-off-fill', 'lightbulb-off', 'lightbulb', 'lightning-charge-fill', 'lightning-charge', 'lightning-fill', 'lightning', 'link-45deg', 'link', 'linkedin', 'list-check', 'list-nested', 'list-ol', 'list-stars', 'list-task', 'list-ul', 'list', 'lock-fill', 'lock', 'mailbox', 'mailbox2', 'map-fill', 'map', 'markdown-fill', 'markdown', 'mask', 'megaphone-fill', 'megaphone', 'menu-app-fill', 'menu-app', 'menu-button-fill', 'menu-button-wide-fill', 'menu-button-wide', 'menu-button', 'menu-down', 'menu-up', 'mic-fill', 'mic-mute-fill', 'mic-mute', 'mic', 'minecart-loaded', 'minecart', 'moisture', 'moon-fill', 'moon-stars-fill', 'moon-stars', 'moon', 'mouse-fill', 'mouse', 'mouse2-fill', 'mouse2', 'mouse3-fill', 'mouse3', 'music-note-beamed', 'music-note-list', 'music-note', 'music-player-fill', 'music-player', 'newspaper', 'node-minus-fill', 'node-minus', 'node-plus-fill', 'node-plus', 'nut-fill', 'nut', 'octagon-fill', 'octagon-half', 'octagon', 'option', 'outlet', 'paint-bucket', 'palette-fill', 'palette', 'palette2', 'paperclip', 'paragraph', 'patch-check-fill', 'patch-check', 'patch-exclamation-fill', 'patch-exclamation', 'patch-minus-fill', 'patch-minus', 'patch-plus-fill', 'patch-plus', 'patch-question-fill', 'patch-question', 'pause-btn-fill', 'pause-btn', 'pause-circle-fill', 'pause-circle', 'pause-fill', 'pause', 'peace-fill', 'peace', 'pen-fill', 'pen', 'pencil-fill', 'pencil-square', 'pencil', 'pentagon-fill', 'pentagon-half', 'pentagon', 'people-fill', 'people', 'percent', 'person-badge-fill', 'person-badge', 'person-bounding-box', 'person-check-fill', 'person-check', 'person-circle', 'person-dash-fill', 'person-dash', 'person-fill', 'person-lines-fill', 'person-plus-fill', 'person-plus', 'person-square', 'person-x-fill', 'person-x', 'person', 'phone-fill', 'phone-landscape-fill', 'phone-landscape', 'phone-vibrate-fill', 'phone-vibrate', 'phone', 'pie-chart-fill', 'pie-chart', 'piggy-bank-fill', 'piggy-bank', 'pin-angle-fill', 'pin-angle', 'pin-fill', 'pin', 'pip-fill', 'pip', 'play-btn-fill', 'play-btn', 'play-circle-fill', 'play-circle', 'play-fill', 'play', 'plug-fill', 'plug', 'plus-circle-dotted', 'plus-circle-fill', 'plus-circle', 'plus-square-dotted', 'plus-square-fill', 'plus-square', 'plus', 'power', 'printer-fill', 'printer', 'puzzle-fill', 'puzzle', 'question-circle-fill', 'question-circle', 'question-diamond-fill', 'question-diamond', 'question-octagon-fill', 'question-octagon', 'question-square-fill', 'question-square', 'question', 'rainbow', 'receipt-cutoff', 'receipt', 'reception-0', 'reception-1', 'reception-2', 'reception-3', 'reception-4', 'record-btn-fill', 'record-btn', 'record-circle-fill', 'record-circle', 'record-fill', 'record', 'record2-fill', 'record2', 'recycle', 'reddit', 'reply-all-fill', 'reply-all', 'reply-fill', 'reply', 'rss-fill', 'rss', 'rulers', 'safe-fill', 'safe', 'safe2-fill', 'safe2', 'save-fill', 'save', 'save2-fill', 'save2', 'scissors', 'screwdriver', 'search', 'segmented-nav', 'server', 'share-fill', 'share', 'shield-check', 'shield-exclamation', 'shield-fill-check', 'shield-fill-exclamation', 'shield-fill-minus', 'shield-fill-plus', 'shield-fill-x', 'shield-fill', 'shield-lock-fill', 'shield-lock', 'shield-minus', 'shield-plus', 'shield-shaded', 'shield-slash-fill', 'shield-slash', 'shield-x', 'shield', 'shift-fill', 'shift', 'shop-window', 'shop', 'shuffle', 'signpost-2-fill', 'signpost-2', 'signpost-fill', 'signpost-split-fill', 'signpost-split', 'signpost', 'sim-fill', 'sim', 'skip-backward-btn-fill', 'skip-backward-btn', 'skip-backward-circle-fill', 'skip-backward-circle', 'skip-backward-fill', 'skip-backward', 'skip-end-btn-fill', 'skip-end-btn', 'skip-end-circle-fill', 'skip-end-circle', 'skip-end-fill', 'skip-end', 'skip-forward-btn-fill', 'skip-forward-btn', 'skip-forward-circle-fill', 'skip-forward-circle', 'skip-forward-fill', 'skip-forward', 'skip-start-btn-fill', 'skip-start-btn', 'skip-start-circle-fill', 'skip-start-circle', 'skip-start-fill', 'skip-start', 'slack', 'slash-circle-fill', 'slash-circle', 'slash-square-fill', 'slash-square', 'slash', 'sliders', 'smartwatch', 'snow', 'snow2', 'snow3', 'sort-alpha-down-alt', 'sort-alpha-down', 'sort-alpha-up-alt', 'sort-alpha-up', 'sort-down-alt', 'sort-down', 'sort-numeric-down-alt', 'sort-numeric-down', 'sort-numeric-up-alt', 'sort-numeric-up', 'sort-up-alt', 'sort-up', 'soundwave', 'speaker-fill', 'speaker', 'speedometer', 'speedometer2', 'spellcheck', 'square-fill', 'square-half', 'square', 'stack', 'star-fill', 'star-half', 'star', 'stars', 'stickies-fill', 'stickies', 'sticky-fill', 'sticky', 'stop-btn-fill', 'stop-btn', 'stop-circle-fill', 'stop-circle', 'stop-fill', 'stop', 'stoplights-fill', 'stoplights', 'stopwatch-fill', 'stopwatch', 'subtract', 'suit-club-fill', 'suit-club', 'suit-diamond-fill', 'suit-diamond', 'suit-heart-fill', 'suit-heart', 'suit-spade-fill', 'suit-spade', 'sun-fill', 'sun', 'sunglasses', 'sunrise-fill', 'sunrise', 'sunset-fill', 'sunset', 'symmetry-horizontal', 'symmetry-vertical', 'table', 'tablet-fill', 'tablet-landscape-fill', 'tablet-landscape', 'tablet', 'tag-fill', 'tag', 'tags-fill', 'tags', 'telegram', 'telephone-fill', 'telephone-forward-fill', 'telephone-forward', 'telephone-inbound-fill', 'telephone-inbound', 'telephone-minus-fill', 'telephone-minus', 'telephone-outbound-fill', 'telephone-outbound', 'telephone-plus-fill', 'telephone-plus', 'telephone-x-fill', 'telephone-x', 'telephone', 'terminal-fill', 'terminal', 'text-center', 'text-indent-left', 'text-indent-right', 'text-left', 'text-paragraph', 'text-right', 'textarea-resize', 'textarea-t', 'textarea', 'thermometer-half', 'thermometer-high', 'thermometer-low', 'thermometer-snow', 'thermometer-sun', 'thermometer', 'three-dots-vertical', 'three-dots', 'toggle-off', 'toggle-on', 'toggle2-off', 'toggle2-on', 'toggles', 'toggles2', 'tools', 'tornado', 'trash-fill', 'trash', 'trash2-fill', 'trash2', 'tree-fill', 'tree', 'triangle-fill', 'triangle-half', 'triangle', 'trophy-fill', 'trophy', 'truck-flatbed', 'truck', 'tsunami', 'tv-fill', 'tv', 'twitch', 'twitter', 'type-bold', 'type-h1', 'type-h2', 'type-h3', 'type-italic', 'type-strikethrough', 'type-underline', 'type', 'ui-checks-grid', 'ui-checks', 'ui-radios-grid', 'ui-radios', 'umbrella-fill', 'umbrella', 'union', 'unlock-fill', 'unlock', 'upc-scan', 'upc', 'upload', 'vector-pen', 'view-list', 'view-stacked', 'vinyl-fill', 'vinyl', 'voicemail', 'volume-down-fill', 'volume-down', 'volume-mute-fill', 'volume-mute', 'volume-off-fill', 'volume-off', 'volume-up-fill', 'volume-up', 'vr', 'wallet-fill', 'wallet', 'wallet2', 'watch', 'water', 'whatsapp', 'wifi-1', 'wifi-2', 'wifi-off', 'wifi', 'wind', 'window-dock', 'window-sidebar', 'window', 'wrench', 'x-circle-fill', 'x-circle', 'x-diamond-fill', 'x-diamond', 'x-lg', 'x-octagon-fill', 'x-octagon', 'x-square-fill', 'x-square', 'x', 'youtube', 'zoom-in', 'zoom-out'
            ];
            return icons.map(icon => ({ name: icon.replace(/-/g, ' '), class: 'bi bi-' + icon }));
        },
        getFontAwesomeIcons() {
            // Comprehensive list of popular Font Awesome icons
            const solidIcons = [
                'home', 'user', 'heart', 'star', 'search', 'envelope', 'gear', 'bell', 'calendar', 'image', 'music', 'video', 'camera', 'file', 'folder', 'book', 'bookmark', 'print', 'tag', 'tags', 'thumbs-up', 'thumbs-down', 'comment', 'comments', 'share', 'globe', 'map', 'location-dot', 'phone', 'circle-info', 'circle-question', 'circle-exclamation', 'circle-check', 'circle-xmark', 'triangle-exclamation', 'ban', 'lock', 'unlock', 'key', 'cloud', 'download', 'upload', 'inbox', 'trash', 'trash-can', 'clock', 'hourglass', 'stop', 'play', 'pause', 'forward', 'backward', 'step-forward', 'step-backward', 'eject', 'volume-high', 'volume-low', 'volume-off', 'volume-xmark', 'microphone', 'headphones', 'bars', 'list', 'table', 'th', 'th-large', 'th-list', 'grid', 'chart-bar', 'chart-line', 'chart-pie', 'trophy', 'award', 'medal', 'gift', 'rocket', 'fire', 'bomb', 'bolt', 'sun', 'moon', 'cloud-sun', 'cloud-moon', 'snowflake', 'tree', 'leaf', 'bug', 'hospital', 'plus', 'minus', 'times', 'check', 'xmark', 'arrow-up', 'arrow-down', 'arrow-left', 'arrow-right', 'arrow-rotate-right', 'arrow-rotate-left', 'expand', 'compress', 'magnifying-glass', 'magnifying-glass-plus', 'magnifying-glass-minus', 'sliders', 'cog', 'wrench', 'hammer', 'screwdriver', 'paint-brush', 'palette', 'eye', 'eye-slash', 'pencil', 'pen', 'highlighter', 'eraser', 'font', 'text-height', 'text-width', 'align-left', 'align-center', 'align-right', 'align-justify', 'bold', 'italic', 'underline', 'strikethrough', 'link', 'unlink', 'paperclip', 'scissors', 'copy', 'paste', 'save', 'floppy-disk', 'folder-open', 'box', 'cube', 'cubes', 'database', 'server', 'laptop', 'desktop', 'mobile', 'tablet', 'keyboard', 'mouse', 'gamepad', 'headset', 'wifi', 'signal', 'battery-full', 'battery-half', 'battery-quarter', 'battery-empty', 'plug', 'lightbulb', 'crown', 'gem', 'birthday-cake', 'glass-cheers', 'pizza-slice', 'burger', 'ice-cream', 'coffee', 'mug-hot', 'wine-glass', 'beer', 'utensils', 'dumbbell', 'basketball', 'football', 'baseball', 'volleyball', 'bowling-ball', 'table-tennis', 'hockey-puck', 'dice', 'chess', 'puzzle-piece', 'car', 'bus', 'truck', 'bicycle', 'motorcycle', 'plane', 'helicopter', 'ship', 'train', 'subway', 'taxi', 'gas-pump', 'graduation-cap', 'school', 'book-open', 'pencil-alt', 'chalkboard', 'flask', 'atom', 'brain', 'dna', 'microscope', 'briefcase', 'suitcase', 'id-card', 'address-card', 'wallet', 'credit-card', 'money-bill', 'dollar-sign', 'euro-sign', 'pound-sign', 'yen-sign', 'shopping-cart', 'shopping-bag', 'store', 'cash-register', 'percent', 'calculator', 'shield', 'shield-halved', 'building', 'city', 'landmark', 'house', 'igloo', 'tent', 'campground', 'smile', 'grin', 'laugh', 'smile-beam', 'grin-hearts', 'kiss-wink-heart', 'grin-tongue', 'sad-tear', 'angry', 'surprise', 'meh', 'frown', 'tired', 'dizzy', 'face-flushed', 'face-grimace', 'ghost', 'skull', 'dragon', 'cat', 'dog', 'dove', 'fish', 'frog', 'hippo', 'horse', 'kiwi-bird', 'otter', 'paw', 'spider', 'feather'
            ];
            const regularIcons = ['circle', 'square', 'heart', 'star', 'user', 'clock', 'calendar', 'comment', 'envelope', 'file', 'folder', 'bookmark', 'image', 'bell', 'lightbulb', 'moon', 'sun', 'flag', 'thumbs-up', 'thumbs-down'];
            const brandIcons = ['facebook', 'twitter', 'instagram', 'youtube', 'linkedin', 'github', 'discord', 'reddit', 'twitch', 'tiktok', 'spotify', 'apple', 'google', 'microsoft', 'amazon', 'paypal', 'stripe', 'steam', 'playstation', 'xbox', 'android', 'windows', 'linux'];

            const icons = [
                ...solidIcons.map(icon => ({ name: icon.replace(/-/g, ' ') + ' (solid)', class: 'fas fa-' + icon })),
                ...regularIcons.map(icon => ({ name: icon.replace(/-/g, ' ') + ' (regular)', class: 'far fa-' + icon })),
                ...brandIcons.map(icon => ({ name: icon.replace(/-/g, ' ') + ' (brand)', class: 'fab fa-' + icon }))
            ];
            return icons;
        },
        getMaterialIcons() {
            // Comprehensive list of Material Icons
            const icons = [
                'home', 'person', 'settings', 'favorite', 'star', 'star_border', 'search', 'info', 'help', 'delete', 'done', 'close', 'add', 'remove', 'check', 'clear', 'cancel', 'arrow_back', 'arrow_forward', 'arrow_upward', 'arrow_downward', 'expand_more', 'expand_less', 'chevron_left', 'chevron_right', 'menu', 'more_vert', 'more_horiz', 'refresh', 'cached', 'autorenew', 'sync', 'loop', 'trending_up', 'trending_down', 'thumb_up', 'thumb_down', 'share', 'send', 'mail', 'inbox', 'drafts', 'flag', 'bookmark', 'bookmark_border', 'label', 'loyalty', 'grade', 'store', 'shopping_cart', 'shopping_basket', 'receipt', 'credit_card', 'account_balance', 'account_circle', 'verified_user', 'lock', 'lock_open', 'vpn_key', 'visibility', 'visibility_off', 'alarm', 'alarm_on', 'alarm_off', 'schedule', 'event', 'event_note', 'today', 'update', 'history', 'access_time', 'watch_later', 'hourglass_empty', 'hourglass_full', 'flight', 'hotel', 'location_on', 'location_off', 'my_location', 'explore', 'directions', 'map', 'place', 'public', 'language', 'cloud', 'cloud_upload', 'cloud_download', 'cloud_done', 'cloud_queue', 'folder', 'folder_open', 'create_new_folder', 'file_copy', 'description', 'insert_drive_file', 'attach_file', 'attachment', 'phone', 'phone_iphone', 'phone_android', 'phonelink', 'laptop', 'computer', 'desktop_windows', 'tablet', 'tablet_android', 'keyboard', 'mouse', 'tv', 'videocam', 'camera', 'camera_alt', 'photo_camera', 'photo', 'image', 'collections', 'crop', 'brightness_high', 'brightness_low', 'brightness_medium', 'brightness_auto', 'wb_sunny', 'wb_cloudy', 'wb_incandescent', 'volume_up', 'volume_down', 'volume_mute', 'volume_off', 'mic', 'mic_off', 'headset', 'headset_mic', 'speaker', 'speaker_notes', 'equalizer', 'graphic_eq', 'library_music', 'music_note', 'queue_music', 'playlist_add', 'playlist_play', 'play_arrow', 'play_circle_filled', 'play_circle_outline', 'pause', 'pause_circle_filled', 'pause_circle_outline', 'stop', 'skip_next', 'skip_previous', 'fast_forward', 'fast_rewind', 'replay', 'repeat', 'repeat_one', 'shuffle', 'videogame_asset', 'sports_esports', 'casino', 'wifi', 'wifi_off', 'signal_wifi_4_bar', 'network_wifi', 'bluetooth', 'bluetooth_disabled', 'battery_full', 'battery_alert', 'battery_charging_full', 'power', 'power_settings_new', 'lightbulb', 'lightbulb_outline', 'build', 'settings_applications', 'settings_phone', 'tune', 'dashboard', 'speed', 'notifications', 'notifications_active', 'notifications_off', 'chat', 'chat_bubble', 'message', 'textsms', 'forum', 'comment', 'mode_comment', 'print', 'save', 'save_alt', 'file_download', 'file_upload', 'content_copy', 'content_cut', 'content_paste', 'link', 'insert_link', 'edit', 'create', 'mode_edit', 'brush', 'color_lens', 'format_paint', 'format_bold', 'format_italic', 'format_underlined', 'format_size', 'format_align_left', 'format_align_center', 'format_align_right', 'format_list_bulleted', 'format_list_numbered', 'format_quote', 'text_fields', 'insert_emoticon', 'mood', 'mood_bad', 'sentiment_satisfied', 'sentiment_dissatisfied', 'group', 'people', 'person_add', 'person_outline', 'supervisor_account', 'work', 'business', 'business_center', 'school', 'local_library', 'book', 'menu_book', 'chrome_reader_mode', 'assignment', 'assessment', 'timeline', 'show_chart', 'pie_chart', 'bar_chart', 'insert_chart', 'table_chart', 'bug_report', 'error', 'error_outline', 'warning', 'report_problem', 'priority_high', 'check_circle', 'check_circle_outline', 'cancel_presentation', 'highlight_off', 'filter_list', 'sort', 'filter', 'bug_report', 'extension', 'developer_mode', 'code', 'view_list', 'view_module', 'view_quilt', 'grid_on', 'grid_off', 'apps', 'widgets', 'launch', 'open_in_new', 'open_in_browser', 'crop_free', 'fullscreen', 'fullscreen_exit', 'zoom_in', 'zoom_out', 'layers', 'layers_clear', 'emoji_emotions', 'emoji_events', 'emoji_flags', 'emoji_food_beverage', 'emoji_nature', 'emoji_objects', 'emoji_people', 'emoji_symbols', 'emoji_transportation', 'sports_basketball', 'sports_baseball', 'sports_football', 'sports_soccer', 'sports_tennis', 'fitness_center', 'pool', 'restaurant', 'local_cafe', 'local_pizza', 'local_bar', 'cake', 'celebration', 'card_giftcard', 'redeem', 'favorite_border', 'volunteer_activism', 'flight_takeoff', 'flight_land', 'directions_car', 'directions_bike', 'directions_bus', 'directions_subway', 'directions_railway', 'directions_boat', 'local_shipping', 'local_taxi', 'eco', 'nature', 'nature_people', 'park', 'terrain', 'pets', 'child_friendly', 'smoking_rooms', 'smoke_free', 'ac_unit', 'beach_access', 'kitchen', 'balcony', 'bathtub', 'spa', 'hot_tub', 'microwave', 'fireplace', 'garage', 'grass', 'local_florist', 'local_fire_department', 'local_hospital', 'local_pharmacy', 'medical_services', 'vaccines', 'coronavirus', 'masks', 'sanitizer'
            ];
            // Store as "mi:icon_name" to identify Material Icons
            return icons.map(icon => ({ name: icon.replace(/_/g, ' '), class: 'material-icons', text: 'mi:' + icon }));
        },
        getSemanticIcons() {
            // Comprehensive list of Semantic UI Icons
            const icons = [
                'home', 'user', 'users', 'settings', 'cog', 'heart', 'star', 'star outline', 'search', 'info', 'info circle', 'question', 'question circle', 'help', 'help circle', 'trash', 'delete', 'check', 'checkmark', 'close', 'remove', 'times', 'plus', 'add', 'minus', 'arrow left', 'arrow right', 'arrow up', 'arrow down', 'chevron left', 'chevron right', 'chevron up', 'chevron down', 'angle left', 'angle right', 'angle up', 'angle down', 'bars', 'content', 'sidebar', 'ellipsis horizontal', 'ellipsis vertical', 'refresh', 'sync', 'redo', 'undo', 'repeat', 'random', 'thumbs up', 'thumbs down', 'thumbs up outline', 'thumbs down outline', 'share', 'share alternate', 'mail', 'envelope', 'envelope outline', 'inbox', 'flag', 'flag outline', 'bookmark', 'bookmark outline', 'tag', 'tags', 'label', 'shopping cart', 'shopping basket', 'shop', 'payment', 'credit card', 'dollar', 'euro', 'pound', 'yen', 'lock', 'unlock', 'key', 'eye', 'eye slash', 'low vision', 'alarm', 'bell', 'bell outline', 'bell slash', 'calendar', 'calendar outline', 'calendar alternate', 'calendar check', 'calendar times', 'calendar plus', 'calendar minus', 'clock', 'clock outline', 'time', 'hourglass', 'hourglass half', 'location arrow', 'map', 'map marker', 'map marker alternate', 'map pin', 'compass', 'globe', 'world', 'plane', 'car', 'taxi', 'bus', 'ship', 'bicycle', 'motorcycle', 'train', 'subway', 'cloud', 'cloud upload', 'cloud download', 'download', 'upload', 'folder', 'folder open', 'folder outline', 'file', 'file outline', 'file alternate', 'copy', 'paste', 'cut', 'save', 'print', 'phone', 'mobile', 'tablet', 'laptop', 'desktop', 'tv', 'video', 'camera', 'camera retro', 'photo', 'image', 'images', 'file image', 'crop', 'sun', 'moon', 'cloud sun', 'cloud moon', 'snowflake', 'fire', 'lightning', 'umbrella', 'volume up', 'volume down', 'volume off', 'volume mute', 'microphone', 'microphone slash', 'headphones', 'music', 'film', 'play', 'play circle', 'pause', 'pause circle', 'stop', 'stop circle', 'forward', 'backward', 'step forward', 'step backward', 'fast forward', 'fast backward', 'eject', 'video play', 'gamepad', 'game', 'wifi', 'signal', 'rss', 'bluetooth', 'battery full', 'battery half', 'battery empty', 'plug', 'power', 'lightbulb', 'wrench', 'cogs', 'hammer', 'magic', 'filter', 'dashboard', 'tachometer', 'chart bar', 'chart line', 'chart pie', 'chart area', 'table', 'list', 'list ul', 'list ol', 'th', 'th large', 'th list', 'comment', 'comments', 'comment outline', 'comments outline', 'chat', 'save outline', 'edit', 'edit outline', 'pencil', 'pencil alternate', 'paint brush', 'palette', 'font', 'bold', 'italic', 'underline', 'strikethrough', 'text height', 'text width', 'align left', 'align center', 'align right', 'align justify', 'list', 'indent', 'outdent', 'link', 'unlink', 'paperclip', 'smile', 'frown', 'meh', 'laugh', 'grin', 'angry', 'dizzy', 'surprise', 'user circle', 'user plus', 'user times', 'user check', 'user secret', 'address book', 'address card', 'id card', 'briefcase', 'suitcase', 'building', 'industry', 'warehouse', 'hospital', 'university', 'graduation', 'book', 'newspaper', 'pencil square', 'trophy', 'gift', 'birthday cake', 'certificate', 'winner', 'bug', 'code', 'terminal', 'database', 'server', 'sitemap', 'fork', 'circle', 'square', 'square outline', 'check circle', 'check circle outline', 'times circle', 'times circle outline', 'exclamation circle', 'exclamation triangle', 'asterisk', 'attention', 'warning', 'announcement', 'grid layout', 'block layout', 'zoom', 'zoom in', 'zoom out', 'expand', 'compress', 'external', 'external alternate', 'window maximize', 'window minimize', 'window restore', 'window close', 'arrows alternate', 'arrows alternate horizontal', 'arrows alternate vertical', 'sign in', 'sign out', 'coffee', 'food', 'utensils', 'pizza', 'beer', 'glass martini', 'cocktail', 'apple', 'lemon', 'leaf', 'tree', 'paw', 'bug', 'spider', 'baseball', 'basketball', 'bowling ball', 'football', 'futbol', 'golf ball', 'hockey puck', 'table tennis', 'volleyball', 'dumbbell', 'running', 'biking', 'swimming', 'medkit', 'first aid', 'pills', 'syringe', 'thermometer', 'heartbeat', 'stethoscope', 'ambulance', 'wheelchair', 'blind'
            ];
            return icons.map(icon => ({ name: icon, class: 'icon ' + icon }));
        },
        filterIcons() {
            // Computed property will handle filtering
        },
        updateFavicon(isPlaying) {
            // Create SVG favicon with dynamic color
            const color = isPlaying ? '#22c55e' : '#5865F2'; // Green when playing, Discord blue otherwise
            const svg = `
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
                  <circle cx="32" cy="32" r="32" fill="${color}"/>
                  <path d="M 22 22 L 22 42 L 28 42 L 38 50 L 38 14 L 28 22 Z" fill="#FFFFFF"/>
                  <path d="M 42 24 Q 46 28, 46 32 Q 46 36, 42 40" stroke="#FFFFFF" stroke-width="2.5" fill="none" stroke-linecap="round"/>
                  <path d="M 46 20 Q 52 26, 52 32 Q 52 38, 46 44" stroke="#FFFFFF" stroke-width="2.5" fill="none" stroke-linecap="round"/>
                </svg>
            `;

            // Convert SVG to data URL
            const svgBlob = new Blob([svg], { type: 'image/svg+xml' });
            const url = URL.createObjectURL(svgBlob);

            // Update favicon
            let link = document.querySelector('link[rel="icon"]');
            if (!link) {
                link = document.createElement('link');
                link.rel = 'icon';
                document.head.appendChild(link);
            }
            link.href = url;
        },
        cleanSoundName(soundPath) {
            // Split the path into parts
            const parts = soundPath.split('/');

            // Get the filename (last part)
            let filename = parts[parts.length - 1];

            // Remove .sync-conflict-* suffixes (e.g., .sync-conflict-20231215-123456)
            filename = filename.replace(/\.sync-conflict-[0-9-]+/g, '');

            // Remove common audio file extensions
            filename = filename.replace(/\.(mp3|wav|ogg|flac|m4a|aac|wma|opus)$/i, '');

            // Put it back together with the folder path
            parts[parts.length - 1] = filename;
            return parts.join('/');
        },

        truncateHostname(hostname) {
            if (!hostname) return '';

            // Check if it's an IPv6 address (contains colons)
            if (hostname.includes(':')) {
                // IPv6 address - show first and last segment
                const parts = hostname.split(':');
                if (parts.length <= 3) {
                    return hostname; // Short enough, show as-is
                }
                // Show first::last
                return `${parts[0]}:...:${parts[parts.length - 1]}`;
            }

            // Check if it's an IPv4 address (only digits and dots, no letters)
            if (/^[\d.]+$/.test(hostname)) {
                // IPv4 address - show as-is (already short)
                return hostname;
            }

            // Hostname - show last 2 DNS parts
            const parts = hostname.split('.');

            // If 2 or fewer parts, show as-is
            if (parts.length <= 2) {
                return hostname;
            }

            // Show [...].lastTwoParts
            const lastTwo = parts.slice(-2).join('.');
            return `[...].${lastTwo}`;
        },

        handleKeyDown(event) {
            if (event.key === 'Control') {
                this.modifierKeys.ctrl = true;
            } else if (event.key === 'Shift') {
                this.modifierKeys.shift = true;
            }
        },

        handleButtonKeydown(event, sound, index) {
            console.log('handleButtonKeydown called:', event.key, 'sound:', sound, 'index:', index);

            const isCustomView = this.activeView === 'buttons';
            const isRecentView = this.activeView === 'recent';
            const isAllView = this.activeView === 'all';

            // Get the total number of buttons in current view
            let totalButtons;
            if (isCustomView) {
                totalButtons = this.config.buttons.length;
            } else if (isRecentView) {
                totalButtons = this.config.recent_sounds.length;
            } else {
                totalButtons = this.filteredSounds.length;
            }

            console.log('Total buttons:', totalButtons, 'cols:', this.config.grid_size.cols);

            const cols = this.config.grid_size.cols;

            // Handle Enter and Space to play sound
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                event.stopPropagation();
                console.log('Playing sound:', sound);
                this.playSound(sound, event);
                return;
            }

            // Handle arrow key navigation
            let newIndex = index;
            let handled = false;

            switch (event.key) {
                case 'ArrowRight':
                    event.preventDefault();
                    newIndex = index < totalButtons - 1 ? index + 1 : index;
                    handled = true;
                    break;
                case 'ArrowLeft':
                    event.preventDefault();
                    newIndex = index > 0 ? index - 1 : index;
                    handled = true;
                    break;
                case 'ArrowDown':
                    event.preventDefault();
                    newIndex = index + cols < totalButtons ? index + cols : index;
                    handled = true;
                    break;
                case 'ArrowUp':
                    event.preventDefault();
                    newIndex = index - cols >= 0 ? index - cols : index;
                    handled = true;
                    break;
                case 'Home':
                    event.preventDefault();
                    newIndex = 0;
                    handled = true;
                    break;
                case 'End':
                    event.preventDefault();
                    newIndex = totalButtons - 1;
                    handled = true;
                    break;
            }

            // Focus the new button if we handled a navigation key
            if (handled) {
                console.log('Moving from index', index, 'to', newIndex);
                if (newIndex !== index) {
                    this.$nextTick(() => {
                        const buttons = document.querySelectorAll('[data-button-index]');
                        console.log('Found', buttons.length, 'buttons with data-button-index');
                        if (buttons[newIndex]) {
                            buttons[newIndex].focus();
                            this.focusedButtonIndex = newIndex;
                            console.log('Focused button at index', newIndex);
                        } else {
                            console.log('Could not find button at index', newIndex);
                        }
                    });
                }
            }
        },

        handleKeyUp(event) {
            if (event.key === 'Control') {
                this.modifierKeys.ctrl = false;
            } else if (event.key === 'Shift') {
                this.modifierKeys.shift = false;
            }
        },

        resetModifiers() {
            this.modifierKeys.ctrl = false;
            this.modifierKeys.shift = false;
        },

        filterAndPrioritize(query, sounds) {
            const lowerQuery = query ? query.toLowerCase() : '';
            const filtered = query ? sounds.filter(sound => sound.toLowerCase().includes(lowerQuery)) : sounds;
            return this.prioritizeRecentSounds(filtered);
        },

        prioritizeRecentSounds(sounds) {
            const recentSet = new Set(this.config.recent_sounds);
            const recentSounds = [];
            const otherSounds = [];

            sounds.forEach(sound => {
                if (recentSet.has(sound)) {
                    recentSounds.push(sound);
                } else {
                    otherSounds.push(sound);
                }
            });

            // Return recent sounds first, maintaining their order from recent_sounds
            // Then append other sounds
            const orderedRecent = this.config.recent_sounds.filter(sound => recentSet.has(sound) && sounds.includes(sound));
            return [...orderedRecent, ...otherSounds];
        },

        async loadAllSounds() {
            try {
                this.allSounds = await rpcCall('list', {});
            } catch (error) {
                console.error('Failed to load sounds:', error);
                alert('Failed to load sound list: ' + error.message);
            }
        },

        async loadUserConfig() {
            if (!this.username) return;

            try {
                const config = await rpcCall('get_user_config', { user_name: this.username });
                if (config) {
                    this.config = config;
                    // Set default for queue_list_as_overlay if not present
                    if (this.config.queue_list_as_overlay === undefined) {
                        this.config.queue_list_as_overlay = true;
                    }
                    // Remove predefined colors from custom_colors if they were migrated
                    if (this.config.custom_colors) {
                        this.config.custom_colors = this.config.custom_colors.filter(c =>
                            !PREDEFINED_COLORS.some(p => p.name === c.name)
                        );
                    }
                } else {
                    // Use default config
                    this.config = {
                        buttons: [],
                        grid_size: { cols: 6, rows: 4 },
                        recent_sounds: [],
                        favorites: [],
                        custom_colors: [],
                        queue_list_as_overlay: true,
                        version: "1.0",
                        created_at: new Date().toISOString(),
                        updated_at: new Date().toISOString()
                    };
                }

                // Initialize sortable after config loads
                this.$nextTick(() => {
                    this.initSortable();
                });
            } catch (error) {
                console.error('Failed to load user config:', error);
            }
        },

        async saveConfig() {
            if (!this.username) {
                alert('Please enter a username first');
                return;
            }

            try {
                this.config.updated_at = new Date().toISOString();
                await rpcCall('save_user_config', {
                    user_name: this.username,
                    config: this.config
                });
            } catch (error) {
                console.error('Failed to save config:', error);
                alert('Failed to save configuration: ' + error.message);
            }
        },

        async saveUsername() {
            localStorage.setItem('username', this.username);
            await this.registerUser();
            this.loadUserConfig();
        },

        saveQueueDisplayMode() {
            this.saveConfig();
        },

        toggleQueue() {
            this.showQueue = !this.showQueue;
            localStorage.setItem('showQueue', this.showQueue);
        },

        async registerUser() {
            if (!this.username) return;

            try {
                await rpcCall('register_user', {
                    user_name: this.username,
                    channelid: DISCORD_VOICE_CHANNEL_ID
                });
                console.log('[User] Registered as', this.username);
            } catch (error) {
                console.error('[User] Failed to register username:', error);
            }
        },

        saveTheme() {
            localStorage.setItem('theme', this.theme);
            document.body.setAttribute('data-bs-theme', this.theme);
        },

        toggleTheme() {
            this.theme = this.theme === 'dark' ? 'light' : 'dark';
            this.saveTheme();
        },

        changeBootstrapTheme() {
            localStorage.setItem('bootstrapTheme', this.bootstrapTheme);
            const themeLink = document.getElementById('bootstrap-theme-css');
            
            if (this.bootstrapTheme === 'dark') {
                // Use Bootstrap's built-in dark mode
                themeLink.href = 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css';
                this.theme = 'dark';
                document.body.setAttribute('data-bs-theme', 'dark');
            } else if (this.bootstrapTheme) {
                // Load Bootswatch theme
                themeLink.href = `https://bootswatch.com/5/${this.bootstrapTheme}/bootstrap.min.css`;
                this.theme = 'light';
                document.body.setAttribute('data-bs-theme', 'light');
            } else {
                // Load default Bootstrap
                themeLink.href = 'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css';
                this.theme = 'light';
                document.body.setAttribute('data-bs-theme', 'light');
            }
            localStorage.setItem('theme', this.theme);
        },

        async fetchBootswatchThemes() {
            try {
                const response = await fetch('https://bootswatch.com/api/5.json');
                const data = await response.json();
                this.bootswatchThemes = data.themes || [];
                console.log('[Bootswatch] Loaded', this.bootswatchThemes.length, 'themes');
            } catch (error) {
                console.error('[Bootswatch] Failed to fetch themes:', error);
                // Fallback to some popular themes if API fails
                this.bootswatchThemes = [
                    { name: 'Cerulean' },
                    { name: 'Cosmo' },
                    { name: 'Cyborg' },
                    { name: 'Darkly' },
                    { name: 'Flatly' },
                    { name: 'Slate' },
                    { name: 'Superhero' }
                ];
            }
        },

        getLatencyBadgeClass(latency) {
            // Color-code latency badges based on performance
            // Good: < 50ms, Warning: 50-150ms, Danger: > 150ms
            if (!latency) return 'bg-secondary';
            if (latency < 50) return 'bg-success';
            if (latency < 150) return 'bg-warning';
            return 'bg-danger';
        },

        togglePlayMode() {
            const modes = ['instant', 'queue', 'next'];
            const currentIndex = modes.indexOf(this.playMode);
            this.playMode = modes[(currentIndex + 1) % modes.length];
            localStorage.setItem('playMode', this.playMode);
        },

        toggleFullscreen() {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(err => {
                    console.error('Error attempting to enable fullscreen:', err);
                });
            } else {
                document.exitFullscreen();
            }
        },

        prepareAudioFilters(audioFilters) {
            // Merge with defaults and create a deep copy
            const merged = {
                ...JSON.parse(JSON.stringify(DEFAULT_AUDIO_FILTERS)),
                ...JSON.parse(JSON.stringify(audioFilters || {}))
            };
            return merged;
        },

        async playSound(query, event = null, audio_filters = null) {
            if (!this.username) {
                alert('Please enter a username first');
                return;
            }

            // Capture timestamp at the moment of button press for latency tracking
            // Adjust for clock offset to get server-equivalent time
            const client_timestamp = Date.now() / 1000; // Client time in seconds
            const request_timestamp = client_timestamp + clockOffset; // Adjusted to server time
            
            console.log(`[Play] Client time: ${client_timestamp.toFixed(3)}, Clock offset: ${(clockOffset * 1000).toFixed(1)}ms, Adjusted: ${request_timestamp.toFixed(3)}`);

            try {
                const params = {
                    channelid: DISCORD_VOICE_CHANNEL_ID,
                    user_name: this.username,
                    query: query,
                    audio_filters: this.prepareAudioFilters(audio_filters),
                    request_timestamp: request_timestamp
                };

                // Determine play mode based on modifier keys or current playMode
                // Ctrl = instant, Shift = queue, Ctrl+Shift = next
                let effectiveMode = this.playMode;
                if (event) {
                    if (event.ctrlKey && event.shiftKey) {
                        effectiveMode = 'next';
                    } else if (event.ctrlKey) {
                        effectiveMode = 'instant';
                    } else if (event.shiftKey) {
                        effectiveMode = 'queue';
                    }
                }

                // Set interrupt and play_next based on effective mode
                if (effectiveMode === 'instant') {
                    params.interrupt = true;
                } else if (effectiveMode === 'next') {
                    params.play_next = true;
                }
                // Default (queue mode) sets neither flag

                await rpcCall('play', params);

                // Queue and config updates are pushed via WebSocket
            } catch (error) {
                console.error('Failed to play sound:', error);
                alert('Failed to play sound: ' + error.message);
            }
        },

        async playSearchResult() {
            if (this.searchQuery) {
                await this.playSound(this.searchQuery);
                this.showSearchDropdown = false;
                this.selectedSearchIndex = -1;
            }
        },

        selectSearchSound(sound) {
            this.searchQuery = sound;
            this.showSearchDropdown = false;
            this.selectedSearchIndex = -1;
        },

        handleSearchKeydown(event) {
            if (!this.showSearchDropdown || this.filteredSounds.length === 0) {
                if (event.key === 'Enter') {
                    this.playSearchResult();
                }
                return;
            }

            const maxIndex = Math.min(this.filteredSounds.length, 100) - 1;

            switch (event.key) {
                case 'ArrowDown':
                    event.preventDefault();
                    this.selectedSearchIndex = this.selectedSearchIndex < maxIndex ? this.selectedSearchIndex + 1 : 0;
                    this.scrollToSearchSelected();
                    break;
                case 'ArrowUp':
                    event.preventDefault();
                    this.selectedSearchIndex = this.selectedSearchIndex > 0 ? this.selectedSearchIndex - 1 : maxIndex;
                    this.scrollToSearchSelected();
                    break;
                case 'Enter':
                    event.preventDefault();
                    if (this.selectedSearchIndex >= 0 && this.selectedSearchIndex <= maxIndex) {
                        this.selectSearchSound(this.filteredSounds[this.selectedSearchIndex]);
                        this.playSearchResult();
                    } else {
                        this.playSearchResult();
                    }
                    break;
                case 'Escape':
                    event.preventDefault();
                    this.showSearchDropdown = false;
                    this.selectedSearchIndex = -1;
                    break;
            }
        },

        handleSearchBlur(event) {
            // Use setTimeout to allow click events on dropdown items and buttons to fire first
            setTimeout(() => {
                this.showSearchDropdown = false;
            }, 150);
        },

        scrollToSearchSelected() {
            this.$nextTick(() => {
                const dropdown = document.querySelector('.search-dropdown');
                const selected = dropdown?.querySelector('.search-dropdown-item.selected');
                if (selected && dropdown) {
                    const dropdownRect = dropdown.getBoundingClientRect();
                    const selectedRect = selected.getBoundingClientRect();

                    if (selectedRect.bottom > dropdownRect.bottom) {
                        selected.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                    } else if (selectedRect.top < dropdownRect.top) {
                        selected.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                    }
                }
            });
        },

        async stopPlayback() {
            try {
                await rpcCall('stop', {
                    channelid: DISCORD_VOICE_CHANNEL_ID
                });
                this.refreshQueue();
            } catch (error) {
                console.error('Failed to stop playback:', error);
            }
        },

        async skipCurrent() {
            if (!this.username) {
                alert('Please enter a username first');
                return;
            }
            try {
                await rpcCall('skip', {
                    channelid: DISCORD_VOICE_CHANNEL_ID,
                    user_name: this.username
                });
                this.refreshQueue();
            } catch (error) {
                console.error('Failed to skip:', error);
                alert('Failed to skip: ' + error.message);
            }
        },

        async refreshQueue() {
            try {
                this.queueStatus = await rpcCall('queue_status', {
                    channelid: DISCORD_VOICE_CHANNEL_ID
                });
            } catch (error) {
                console.error('Failed to refresh queue:', error);
            }
        },

        async removeQueueItem(userId, index) {
            try {
                await rpcCall('remove_queue_item', {
                    channelid: DISCORD_VOICE_CHANNEL_ID,
                    user_id: userId,
                    item_index: index
                });
                // No need to manually refresh - WebSocket will push update
            } catch (error) {
                console.error('Failed to remove queue item:', error);
                alert('Failed to remove item: ' + error.message);
            }
        },

        async clearUserQueue(userId) {
            // Find the user queue to get the user name for confirmation
            const userQueue = this.queueStatus.user_queues.find(q => q.user_id === userId);
            const userName = userQueue ? userQueue.user_name : 'this user';

            if (!confirm(`Clear all ${userQueue.count} items from ${userName}'s queue?`)) {
                return;
            }

            try {
                // Remove items from the end to avoid index shifting issues
                for (let i = userQueue.items.length - 1; i >= 0; i--) {
                    await rpcCall('remove_queue_item', {
                        channelid: DISCORD_VOICE_CHANNEL_ID,
                        user_id: userId,
                        item_index: i
                    });
                }
                // No need to manually refresh - WebSocket will push updates
            } catch (error) {
                console.error('Failed to clear user queue:', error);
                alert('Failed to clear queue: ' + error.message);
            }
        },

        addNewButton() {
            const newButton = {
                id: Date.now(),
                label: 'New Button',
                sound: '',
                color: 'primary',
                icon: '',
                audio_filters: {}
            };
            this.config.buttons.push(newButton);
            // Merge with defaults so UI always has all filter fields
            this.config.buttons[this.config.buttons.length - 1].audio_filters = {
                ...JSON.parse(JSON.stringify(DEFAULT_AUDIO_FILTERS)),
                ...this.config.buttons[this.config.buttons.length - 1].audio_filters
            };
            // Store backup of the new button
            this.editingButtonBackup = JSON.parse(JSON.stringify(this.config.buttons[this.config.buttons.length - 1]));
            this.isNewButton = true;
            // Open editor for the newly added button
            this.editingButton = this.config.buttons.length - 1;
            // Focus and select label input
            this.$nextTick(() => {
                if (this.$refs.labelInput) {
                    this.$refs.labelInput.focus();
                    this.$refs.labelInput.select();
                }
                // Setup focus trap in modal
                this.setupModalFocusTrap();
            });
        },

        addButtonFromSound(sound) {
            this.config.buttons.push({
                id: Date.now(),
                label: sound,
                sound: sound,
                color: 'primary',
                icon: ''
            });
            this.saveConfig();
            this.activeView = 'buttons';
        },

        editButton(index) {
            // Ensure the button has an icon field for backwards compatibility
            if (!this.config.buttons[index].hasOwnProperty('icon')) {
                this.config.buttons[index].icon = '';
            }
            // Merge with defaults so UI always has all filter fields
            if (!this.config.buttons[index].hasOwnProperty('audio_filters')) {
                this.config.buttons[index].audio_filters = {};
            }
            // Merge with defaults (defaults take precedence for missing keys)
            this.config.buttons[index].audio_filters = {
                ...JSON.parse(JSON.stringify(DEFAULT_AUDIO_FILTERS)),
                ...this.config.buttons[index].audio_filters
            };
            // Migrate old volume_boost if present
            if (this.config.buttons[index].hasOwnProperty('volume_boost') &&
                !this.config.buttons[index].audio_filters.hasOwnProperty('volume_boost')) {
                this.config.buttons[index].audio_filters.volume_boost = this.config.buttons[index].volume_boost;
            }
            this.editingButtonBackup = JSON.parse(JSON.stringify(this.config.buttons[index]));
            this.isNewButton = false;
            this.editingButton = index;
            // Focus and select label input
            this.$nextTick(() => {
                if (this.$refs.labelInput) {
                    this.$refs.labelInput.focus();
                    this.$refs.labelInput.select();
                }
                // Setup focus trap in modal
                this.setupModalFocusTrap();
            });
            this.showSoundDropdown = false;
            this.selectedSoundIndex = -1;
        },

        setupModalFocusTrap() {
            const modal = document.querySelector('.modal-content');
            if (!modal) return;

            const focusableElements = modal.querySelectorAll(
                'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
            );
            const firstFocusable = focusableElements[0];
            const lastFocusable = focusableElements[focusableElements.length - 1];

            const handleTabKey = (e) => {
                if (e.key !== 'Tab') return;

                if (e.shiftKey) {
                    if (document.activeElement === firstFocusable) {
                        e.preventDefault();
                        lastFocusable.focus();
                    }
                } else {
                    if (document.activeElement === lastFocusable) {
                        e.preventDefault();
                        firstFocusable.focus();
                    }
                }
            };

            // Store handler reference for cleanup
            modal._focusTrapHandler = handleTabKey;
            modal.addEventListener('keydown', handleTabKey);
        },

        cleanupModalFocusTrap() {
            const modal = document.querySelector('.modal-content');
            if (modal && modal._focusTrapHandler) {
                modal.removeEventListener('keydown', modal._focusTrapHandler);
                delete modal._focusTrapHandler;
            }
        },

        selectSound(sound) {
            if (this.editingButton !== null) {
                this.config.buttons[this.editingButton].sound = sound;
                this.showSoundDropdown = false;
                this.selectedSoundIndex = -1;
            }
        },

        handleSoundInputKeydown(event) {
            if (!this.showSoundDropdown || this.filteredEditSounds.length === 0) {
                return;
            }

            const maxIndex = Math.min(this.filteredEditSounds.length, 100) - 1;

            switch (event.key) {
                case 'ArrowDown':
                    event.preventDefault();
                    this.selectedSoundIndex = this.selectedSoundIndex < maxIndex ? this.selectedSoundIndex + 1 : 0;
                    this.scrollToSelected();
                    break;
                case 'ArrowUp':
                    event.preventDefault();
                    this.selectedSoundIndex = this.selectedSoundIndex > 0 ? this.selectedSoundIndex - 1 : maxIndex;
                    this.scrollToSelected();
                    break;
                case 'Enter':
                    event.preventDefault();
                    if (this.selectedSoundIndex >= 0 && this.selectedSoundIndex <= maxIndex) {
                        this.selectSound(this.filteredEditSounds[this.selectedSoundIndex]);
                    }
                    break;
                case 'Escape':
                    event.preventDefault();
                    this.showSoundDropdown = false;
                    this.selectedSoundIndex = -1;
                    break;
            }
        },

        scrollToSelected() {
            this.$nextTick(() => {
                const dropdown = document.querySelector('.sound-dropdown');
                const selected = dropdown?.querySelector('.sound-dropdown-item.selected');
                if (selected && dropdown) {
                    const dropdownRect = dropdown.getBoundingClientRect();
                    const selectedRect = selected.getBoundingClientRect();

                    if (selectedRect.bottom > dropdownRect.bottom) {
                        selected.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                    } else if (selectedRect.top < dropdownRect.top) {
                        selected.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                    }
                }
            });
        },

        cleanAudioFilters(button) {
            // Remove default values from audio_filters, keeping only non-default values
            if (!button.audio_filters) return;

            const cleanedFilters = {};
            let hasNonDefault = false;

            for (const [key, value] of Object.entries(button.audio_filters)) {
                const defaultValue = DEFAULT_AUDIO_FILTERS[key];

                // Keep the value if it differs from default
                if (JSON.stringify(value) !== JSON.stringify(defaultValue)) {
                    cleanedFilters[key] = value;
                    hasNonDefault = true;
                }
            }

            // Only keep audio_filters if there are non-default values
            if (hasNonDefault) {
                button.audio_filters = cleanedFilters;
            } else {
                delete button.audio_filters;
            }
        },

        saveButtonEdit() {
            // Clean audio_filters before saving
            if (this.editingButton !== null) {
                this.cleanAudioFilters(this.config.buttons[this.editingButton]);
            }

            this.cleanupModalFocusTrap();
            this.editingButtonBackup = null;
            this.isNewButton = false;
            this.editingButton = null;
            this.saveConfig();
        },

        saveButtonEditAsCopy() {
            if (this.editingButton === null) return;

            const currentButton = this.config.buttons[this.editingButton];
            const originalLabel = this.editingButtonBackup.label;
            const newLabel = currentButton.label;

            // Check if the label is new (different from original)
            if (newLabel === originalLabel) {
                alert('Please change the label to create a copy');
                return;
            }

            // Check if the new label already exists
            const labelExists = this.config.buttons.some((btn, idx) =>
                idx !== this.editingButton && btn.label === newLabel
            );

            if (labelExists) {
                alert('A button with this label already exists');
                return;
            }

            // Create a copy by adding the current button as a new button
            const buttonCopy = JSON.parse(JSON.stringify(currentButton));
            // Clean audio_filters before adding the copy
            this.cleanAudioFilters(buttonCopy);
            this.config.buttons.push(buttonCopy);

            // Restore the original button to its backup state (so only the copy has the new name)
            this.config.buttons[this.editingButton] = JSON.parse(JSON.stringify(this.editingButtonBackup));

            // Close the edit dialog
            this.cleanupModalFocusTrap();
            this.editingButtonBackup = null;
            this.isNewButton = false;
            this.editingButton = null;
            this.saveConfig();
        },

        testCurrentSound(instant = false) {
            if (this.editingButton === null) return;

            // Ensure we're reading the absolute latest values from the config
            this.$nextTick(() => {
                const button = this.config.buttons[this.editingButton];
                if (!button.sound) {
                    alert('Please select a sound first');
                    return;
                }

                // Create a mock event with instant mode if requested
                const event = instant ? { ctrlKey: true } : null;

                // Play the sound with current settings
                this.playSound(
                    button.sound,
                    event,
                    button.audio_filters
                );
            });
        },

        cancelButtonEdit() {
            if (this.editingButton !== null && this.editingButtonBackup !== null) {
                // Check if this was a new button (empty sound in backup)
                if (this.editingButtonBackup.sound === '' && this.editingButtonBackup.label === 'New Button') {
                    // Remove the button that was just added
                    this.config.buttons.splice(this.editingButton, 1);
                } else {
                    // Restore the original button state
                    this.config.buttons[this.editingButton] = this.editingButtonBackup;
                }
            }
            this.cleanupModalFocusTrap();
            this.editingButtonBackup = null;
            this.isNewButton = false;
            this.editingButton = null;
            this.showSoundDropdown = false;
            this.selectedSoundIndex = -1;
        },

        removeButton(index) {
            if (confirm('Remove this button?')) {
                this.config.buttons.splice(index, 1);
                this.saveConfig();
            }
        },

        removeRecentSound(index) {
            if (confirm('Remove this sound from recent?')) {
                this.config.recent_sounds.splice(index, 1);
                this.saveConfig();
            }
        },

        exportConfig() {
            const dataStr = JSON.stringify(this.config, null, 2);
            const dataBlob = new Blob([dataStr], { type: 'application/json' });
            const url = URL.createObjectURL(dataBlob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `soundboard-config-${this.username}.json`;
            link.click();
            URL.revokeObjectURL(url);
        },

        async importConfig(event) {
            const file = event.target.files[0];
            if (!file) return;

            try {
                const text = await file.text();
                const imported = JSON.parse(text);

                // Validate basic structure
                if (!imported.buttons || !imported.grid_size) {
                    throw new Error('Invalid configuration file format');
                }

                this.config = {
                    ...imported,
                    updated_at: new Date().toISOString()
                };

                await this.saveConfig();
                alert('Configuration imported successfully!');

                // Reinitialize sortable
                this.$nextTick(() => {
                    this.initSortable();
                });
            } catch (error) {
                console.error('Failed to import config:', error);
                alert('Failed to import configuration: ' + error.message);
            }

            // Reset file input
            event.target.value = '';
        },

        async resetConfig() {
            if (!confirm('Reset configuration to default? This will remove all custom buttons.')) {
                return;
            }

            if (!this.username) {
                alert('Please enter a username first');
                return;
            }

            try {
                await rpcCall('reset_user_config', { user_name: this.username });
                await this.loadUserConfig();
                alert('Configuration reset successfully!');
            } catch (error) {
                console.error('Failed to reset config:', error);
                alert('Failed to reset configuration: ' + error.message);
            }
        },

        getColorClassName(color) {
            if (typeof color === 'string') return color;
            return color.name || color;
        },

        addColor() {
            if (!this.config.custom_colors) {
                this.config.custom_colors = [];
            }
            // Generate unique name
            let colorName = 'custom';
            let counter = 1;
            while (this.buttonColors.some(c => c.name === colorName)) {
                colorName = `custom${counter++}`;
            }
            this.config.custom_colors.push({ name: colorName, rgb: '#000000' });
            this.saveConfig();
        },

        removeColor(index) {
            if (!this.config.custom_colors) return;

            const customStartIndex = PREDEFINED_COLORS.length;
            const customIndex = index - customStartIndex;

            if (customIndex >= 0 && customIndex < this.config.custom_colors.length) {
                this.config.custom_colors.splice(customIndex, 1);
                this.saveConfig();
            }
        },
        isPredefinedColor(colorName) {
            return PREDEFINED_COLORS.some(c => c.name === colorName);
        },
        getColorStyle(colorName) {
            // Find the color object with custom RGB
            const colorObj = this.buttonColors.find(c => c.name === colorName);
            if (colorObj?.rgb) {
                return {
                    backgroundColor: colorObj.rgb,
                    color: this.getTextColor(colorObj.rgb),
                    border: 'none'
                };
            }
            return {};
        },
        getTextColor(rgbString) {
            // Parse RGB/HEX string and calculate relative luminance for WCAG contrast
            let r, g, b;

            if (rgbString.startsWith('#')) {
                const hex = rgbString.replace('#', '');
                r = parseInt(hex.substring(0, 2), 16);
                g = parseInt(hex.substring(2, 4), 16);
                b = parseInt(hex.substring(4, 6), 16);
            } else if (rgbString.startsWith('rgb')) {
                const match = rgbString.match(/\d+/g);
                if (!match || match.length < 3) return '#fff';
                [r, g, b] = match.slice(0, 3).map(Number);
            } else {
                return '#fff';
            }

            // WCAG relative luminance calculation
            const luminance = this.getRelativeLuminance(r, g, b);

            // Use white if background is dark (luminance < 0.4), black if light
            return luminance < 0.4 ? '#fff' : '#000';
        },
        getRelativeLuminance(r, g, b) {
            // Normalize to 0-1
            r = r / 255;
            g = g / 255;
            b = b / 255;

            // Apply gamma correction
            r = r <= 0.03928 ? r / 12.92 : Math.pow((r + 0.055) / 1.055, 2.4);
            g = g <= 0.03928 ? g / 12.92 : Math.pow((g + 0.055) / 1.055, 2.4);
            b = b <= 0.03928 ? b / 12.92 : Math.pow((b + 0.055) / 1.055, 2.4);

            // Calculate luminance
            return 0.2126 * r + 0.7152 * g + 0.0722 * b;
        },

        initSortable() {
            if (this.sortable) {
                this.sortable.destroy();
            }

            const grid = this.$refs.buttonGrid;
            if (!grid) return;

            this.sortable = Sortable.create(grid, {
                animation: 150,
                ghostClass: 'sortable-ghost',
                chosenClass: 'sortable-chosen',
                dragClass: 'sortable-drag',
                disabled: !this.editMode,
                onEnd: (evt) => {
                    // Reorder buttons array
                    const item = this.config.buttons.splice(evt.oldIndex, 1)[0];
                    this.config.buttons.splice(evt.newIndex, 0, item);
                    this.saveConfig();
                }
            });
        },

        toggleEditMode() {
            this.editMode = !this.editMode;
            if (this.sortable) {
                this.sortable.option('disabled', !this.editMode);
            }
        },

        toggleQueueExpanded(userId) {
            this.expandedQueues[userId] = !this.expandedQueues[userId];
        },

        startQueuePolling() {
            // Keep polling as backup (every 5 seconds) if WebSocket fails
            this.queueRefreshInterval = setInterval(() => {
                if (!websocket || websocket.readyState !== WebSocket.OPEN) {
                    this.refreshQueue();
                }
            }, 5000);
        },

        stopQueuePolling() {
            if (this.queueRefreshInterval) {
                clearInterval(this.queueRefreshInterval);
                this.queueRefreshInterval = null;
            }

            // Close WebSocket
            if (websocket) {
                websocket.close();
                websocket = null;
            }
        },

        async requestWakeLock() {
            try {
                if ('wakeLock' in navigator) {
                    this.wakeLock = await navigator.wakeLock.request('screen');
                    console.log('Wake lock acquired');

                    this.wakeLock.addEventListener('release', () => {
                        console.log('Wake lock released');
                    });
                }
            } catch (err) {
                console.error('Wake lock request failed:', err);
            }
        },

        releaseWakeLock() {
            if (this.wakeLock) {
                this.wakeLock.release();
                this.wakeLock = null;
            }
        }
    },

    async mounted() {
        // Apply theme
        document.body.setAttribute('data-bs-theme', this.theme);
        
        // Fetch available Bootswatch themes
        await this.fetchBootswatchThemes();
        
        // Apply Bootstrap theme
        this.changeBootstrapTheme();

        // Listen for theme changes from other tabs/windows
        window.addEventListener('storage', (e) => {
            if (e.key === 'bootstrapTheme' && e.newValue !== null) {
                this.bootstrapTheme = e.newValue;
                this.changeBootstrapTheme();
            } else if (e.key === 'theme' && e.newValue !== null) {
                this.theme = e.newValue;
                document.body.setAttribute('data-bs-theme', this.theme);
            }
        });

        // Set initial favicon
        this.updateFavicon(false);

        // Initialize WebSocket with queue update handler and wait for it to be ready
        const wsReady = initWebSocket(
            (data) => {
                this.queueStatus = data;
                if (data.connected_users !== undefined) {
                    this.connectedUsers = data.connected_users;
                }
                if (data.connected_user_list !== undefined) {
                    this.connectedUserList = data.connected_user_list;
                }
            },
            (files) => {
                console.log('[File List] Updated with', files.length, 'files');
                this.allSounds = files;
            },
            async (user_name) => {
                // Only fetch and update if the config is for the current user
                if (this.username && user_name === this.username) {
                    // Don't reload config if we're currently editing a button
                    if (this.editingButton !== null) {
                        console.log('[Config] Update notification received but ignoring because button is being edited');
                        return;
                    }
                    console.log('[Config] Update notification for current user, fetching config...');
                    try {
                        const config = await rpcCall('get_user_config', { user_name: this.username });
                        // Merge the config, preserving local-only state like editingButton
                        this.config = {
                            ...this.config,
                            ...config
                        };
                        console.log('[Config] Configuration reloaded from server');
                    } catch (error) {
                        console.error('[Config] Failed to fetch updated config:', error);
                    }
                }
            },
            // onConnected callback - re-register username on reconnect
            async () => {
                if (this.username) {
                    console.log('[WebSocket] Re-registering username after reconnect:', this.username);
                    await this.registerUser();
                }
            }
        );

        // Start polling interval
        this.startQueuePolling();

        // Wait for WebSocket to connect before loading data
        try {
            await wsReady;

            // Register username if available
            if (this.username) {
                await this.registerUser();
            }

            // Load initial data
            this.loadAllSounds();

            if (this.username) {
                this.loadUserConfig();
            }

            // Get initial queue status
            this.refreshQueue();
        } catch (error) {
            console.error('Failed to initialize WebSocket:', error);
        }

        // Request wake lock to keep screen on
        this.requestWakeLock();

        // Re-request wake lock when page becomes visible again
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                this.requestWakeLock();
            }
        });

        // Track fullscreen state changes
        document.addEventListener('fullscreenchange', () => {
            this.isFullscreen = !!document.fullscreenElement;
        });

        // Track fullscreen state changes
        document.addEventListener('fullscreenchange', () => {
            this.isFullscreen = !!document.fullscreenElement;
        });

        // Add Ctrl+F keyboard shortcut
        document.addEventListener('keydown', (e) => {
            // Ctrl+F for search
            if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
                e.preventDefault();
                this.$refs.searchInput?.focus();
                this.$refs.searchInput?.select();
                this.showSearchDropdown = true;
                this.selectedSearchIndex = -1;
            }

            // Don't handle shortcuts when typing in inputs
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                return;
            }

            // ? for help
            if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                this.showHelp = !this.showHelp;
            }

            // S for settings
            if (e.key === 's' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                this.showSettings = !this.showSettings;
            }

            // Q for queue
            if (e.key === 'q' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                this.toggleQueue();
            }

            // D for debug stats
            if (e.key === 'd' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                window.open('debug.html', '_blank');
            }

            // U for users
            if (e.key === 'u' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                this.showConnectedUsers = !this.showConnectedUsers;
            }

            // F for fullscreen
            if (e.key === 'f' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                this.toggleFullscreen();
            }

            // M for toggle play mode
            if (e.key === 'm' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                this.togglePlayMode();
            }

            // 1, 2, 3 for view switching
            if (e.key === '1' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                this.activeView = 'buttons';
            }
            if (e.key === '2' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                this.activeView = 'recent';
            }
            if (e.key === '3' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                e.preventDefault();
                this.activeView = 'all';
            }

            // Escape to close modals and panels
            if (e.key === 'Escape') {
                if (this.editingButton !== null) {
                    this.cancelButtonEdit();
                } else if (this.showConnectedUsers) {
                    this.showConnectedUsers = false;
                } else if (this.showHelp) {
                    this.showHelp = false;
                } else if (this.showSettings) {
                    this.showSettings = false;
                } else if (this.showQueue) {
                    this.toggleQueue();
                }
            }
        });

        // Track modifier keys globally for play mode indication
        window.addEventListener('keydown', this.handleKeyDown);
        window.addEventListener('keyup', this.handleKeyUp);
        window.addEventListener('blur', this.resetModifiers);
    },

    beforeUnmount() {
        this.stopQueuePolling();
        if (this.sortable) {
            this.sortable.destroy();
        }
        this.releaseWakeLock();

        // Clean up modifier key listeners
        window.removeEventListener('keydown', this.handleKeyDown);
        window.removeEventListener('keyup', this.handleKeyUp);
        window.removeEventListener('blur', this.resetModifiers);
    }
});

// Store app instance globally so clock sync can update it
window.vueApp = app;
app.mount('#app');
