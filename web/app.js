const { createApp } = Vue;

// RPC Client
const RPC_URL = 'https://apollo.loping.net/rpc/soundbot';
const DISCORD_VOICE_CHANNEL_ID = '1033659964457230392';

async function rpcCall(method, params = {}) {
    const response = await fetch(RPC_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            jsonrpc: '2.0',
            method: method,
            params: params,
            id: Date.now()
        })
    });
    const data = await response.json();
    if (data.error) {
        throw new Error(data.error.message || 'RPC Error');
    }
    return data.result;
}

createApp({
    data() {
        return {
            username: localStorage.getItem('username') || '',
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
            queueStatus: {
                connected: false,
                is_playing: false,
                active_streams: [],
                user_queues: [],
                total_queued: 0
            },
            searchQuery: '',
            showSettings: false,
            activeView: 'buttons', // 'buttons', 'recent', 'all'
            editingButton: null,
            buttonColors: ['primary', 'secondary', 'success', 'danger', 'warning', 'info', 'dark'],
            queueRefreshInterval: null,
            sortable: null
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
        filteredSounds() {
            if (!this.searchQuery) return this.allSounds;
            const query = this.searchQuery.toLowerCase();
            return this.allSounds.filter(sound => sound.toLowerCase().includes(query));
        }
    },
    methods: {
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
        
        saveUsername() {
            localStorage.setItem('username', this.username);
            this.loadUserConfig();
        },
        
        async playSound(query) {
            if (!this.username) {
                alert('Please enter a username first');
                return;
            }
            
            try {
                await rpcCall('play', {
                    channelid: DISCORD_VOICE_CHANNEL_ID,
                    user_name: this.username,
                    query: query
                });
                
                // Reload config to get updated recent sounds
                setTimeout(() => this.loadUserConfig(), 500);
                this.refreshQueue();
            } catch (error) {
                console.error('Failed to play sound:', error);
                alert('Failed to play sound: ' + error.message);
            }
        },
        
        async playSearchResult() {
            if (this.searchQuery) {
                await this.playSound(this.searchQuery);
            }
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
                    index: index
                });
                await this.refreshQueue();
            } catch (error) {
                console.error('Failed to remove queue item:', error);
                alert('Failed to remove item: ' + error.message);
            }
        },
        
        addNewButton() {
            this.config.buttons.push({
                id: Date.now(),
                label: 'New Button',
                sound: this.allSounds[0] || '',
                color: 'primary'
            });
            // Open editor for the newly added button
            this.editingButton = this.config.buttons.length - 1;
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
            this.editingButton = index;
        },
        
        saveButtonEdit() {
            this.editingButton = null;
            this.saveConfig();
        },
        
        removeButton(index) {
            if (confirm('Remove this button?')) {
                this.config.buttons.splice(index, 1);
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
                onEnd: (evt) => {
                    // Reorder buttons array
                    const item = this.config.buttons.splice(evt.oldIndex, 1)[0];
                    this.config.buttons.splice(evt.newIndex, 0, item);
                    this.saveConfig();
                }
            });
        },
        
        startQueuePolling() {
            this.queueRefreshInterval = setInterval(() => {
                this.refreshQueue();
            }, 2000);
        },
        
        stopQueuePolling() {
            if (this.queueRefreshInterval) {
                clearInterval(this.queueRefreshInterval);
                this.queueRefreshInterval = null;
            }
        }
    },
    
    mounted() {
        // Load initial data
        this.loadAllSounds();
        
        if (this.username) {
            this.loadUserConfig();
        }
        
        // Start queue polling
        this.refreshQueue();
        this.startQueuePolling();
    },
    
    beforeUnmount() {
        this.stopQueuePolling();
        if (this.sortable) {
            this.sortable.destroy();
        }
    }
}).mount('#app');
