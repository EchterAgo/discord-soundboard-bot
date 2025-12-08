const { createApp } = Vue;

// RPC Client
const WS_URL = 'wss://apollo.loping.net/ws';
const DISCORD_VOICE_CHANNEL_ID = '1033659964457230392';

// WebSocket connection management
let websocket = null;
let wsReconnectTimer = null;
let wsCallbacks = new Map();
let wsReadyPromise = null;
let wsReadyResolve = null;

function initWebSocket(onQueueUpdate, onFileListUpdate, onConfigUpdate) {
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
    };
    
    websocket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            
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
        
        // Reset ready promise
        wsReadyPromise = null;
        wsReadyResolve = null;
        
        // Reconnect after 2 seconds
        if (!wsReconnectTimer) {
            wsReconnectTimer = setTimeout(() => {
                wsReconnectTimer = null;
                initWebSocket(onQueueUpdate, onFileListUpdate, onConfigUpdate);
            }, 2000);
        }
    };
    
    return wsReadyPromise;
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

createApp({
    data() {
        return {
            username: localStorage.getItem('username') || '',
            theme: localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
            playMode: localStorage.getItem('playMode') || 'instant', // 'instant', 'queue', 'next'
            config: {
                buttons: [],
                grid_size: { cols: 6, rows: 4 },
                recent_sounds: [],
                favorites: [],
                version: "1.0",
                created_at: null,
                updated_at: null
            },
            allSounds: [],
            connectedUsers: 0,
            connectedUserList: [],
            showConnectedUsers: false,
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
            showQueue: false,
            isFullscreen: false,
            activeView: 'buttons', // 'buttons', 'recent', 'all'
            editingButton: null,
            buttonColors: ['primary', 'secondary', 'success', 'danger', 'warning', 'info', 'dark'],
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
            focusedButtonIndex: -1
        };
    },
    computed: {
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
            
            switch(event.key) {
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
                } else {
                    // Use default config
                    this.config = {
                        buttons: [],
                        grid_size: { cols: 6, rows: 4 },
                        recent_sounds: [],
                        favorites: [],
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
        
        async playSound(query, event = null) {
            if (!this.username) {
                alert('Please enter a username first');
                return;
            }
            
            try {
                const params = {
                    channelid: DISCORD_VOICE_CHANNEL_ID,
                    user_name: this.username,
                    query: query
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
            
            switch(event.key) {
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
                color: 'primary'
            };
            this.config.buttons.push(newButton);
            // Store backup of the new button
            this.editingButtonBackup = JSON.parse(JSON.stringify(newButton));
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
                color: 'primary'
            });
            this.saveConfig();
            this.activeView = 'buttons';
        },
        
        editButton(index) {
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
            
            switch(event.key) {
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
        
        saveButtonEdit() {
            this.cleanupModalFocusTrap();
            this.editingButtonBackup = null;
            this.isNewButton = false;
            this.editingButton = null;
            this.saveConfig();
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
                this.showQueue = !this.showQueue;
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
                    this.showQueue = false;
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
}).mount('#app');
