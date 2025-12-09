# Client-to-Server Latency Tracking

## Overview

This system tracks end-to-end latency from when a user clicks a button in the web interface to when audio starts playing, including network latency from client to server.

## Clock Synchronization

Since the client and server clocks are not perfectly synchronized, we use a **clock offset estimation** approach based on the existing ping/pong mechanism.

### How It Works

1. **Periodic Ping/Pong** (every 5 seconds):
   - Client sends `ping` message with timestamp `T_client_send`
   - Server receives it and immediately responds with `pong` + `server_time`
   - Client receives pong at `T_client_receive`
   
2. **RTT Calculation**:
   ```
   RTT = T_client_receive - T_client_send
   ```

3. **Clock Offset Estimation**:
   Assuming symmetric network delay (reasonable for most connections):
   ```
   clock_offset ≈ server_time - T_client_send - (RTT / 2)
   ```
   
   This estimates: `server_time - client_time`

4. **Exponential Moving Average**:
   To smooth out network jitter:
   ```javascript
   clockOffset = clockOffset * 0.7 + estimatedOffset * 0.3
   ```

### Timestamp Adjustment

When a user clicks to play audio:
```javascript
client_timestamp = Date.now() / 1000  // Client local time
request_timestamp = client_timestamp + clockOffset  // Adjusted to server time
```

This `request_timestamp` is sent to the server and represents the user's click time in server time coordinates.

## Latency Metrics Tracked

The system now tracks these latencies:

1. **client_to_server_latency**: Network time from user click to server receiving the request
   - `= server_receive_time - client_click_time (adjusted)`
   
2. **queue_latency**: Time from server receive to adding to audio queue
   - `= queue_time - server_receive_time`

3. **processing_latency**: Time from queue to starting ffmpeg
   - `= stream_start_time - queue_time`

4. **decode_latency**: Time from ffmpeg start to first audio byte
   - `= first_byte_time - stream_start_time`

5. **total_latency**: Server-side total (receive to first byte)
   - `= first_byte_time - server_receive_time`

6. **end_to_end_latency**: Complete latency (click to audio)
   - `= first_byte_time - client_click_time (adjusted)`

7. **playback_duration**: Total audio playback time
   - `= stream_end_time - stream_start_time`

## Viewing Statistics

Use the JSON-RPC `get_audio_stats` method to retrieve statistics:

```javascript
await rpcCall('get_audio_stats')
```

Returns:
```json
{
  "recent": [...],  // Last 20 playback events
  "active": [...],  // Currently playing
  "averages": {
    "client_to_server": 45.2,
    "queue": 1.5,
    "processing": 3.2,
    "decode": 25.8,
    "total": 30.5,
    "end_to_end": 75.7
  },
  "percentiles": {
    "client_to_server": { "p50": 42, "p95": 65, "p99": 120 },
    "end_to_end": { "p50": 70, "p95": 95, "p99": 150 },
    ...
  },
  "total_samples": 100
}
```

## Accuracy Considerations

### Clock Offset Accuracy
- **Typical accuracy**: ±5-20ms depending on network jitter
- **Assumptions**: Symmetric network delay (reasonable for most home/office networks)
- **Limitations**: Won't be perfect for highly asymmetric routes (e.g., satellite)

### Network Jitter Mitigation
- Uses exponential moving average over multiple pings
- Pings every 5 seconds to maintain fresh offset estimate
- 70/30 weighting favors stability while adapting to changes

### When Metrics Are Accurate
✅ Client-to-server latency: Very accurate for same-datacenter or low-jitter connections  
✅ Server-side metrics (queue, processing, decode): Always accurate (same clock)  
⚠️ End-to-end latency: Accurate within clock sync precision (typically ±10-20ms)

### When to Be Cautious
- VPN connections (asymmetric routing)
- Mobile/cellular networks (high jitter)
- Cross-continental connections (varying routes)

## Implementation Files

- `web/app.js`: Clock sync logic, ping/pong handling, timestamp adjustment
- `rpc_server.py`: Pong response with server timestamp
- `audio_stats.py`: Enhanced stats tracking with client timestamps
- `audioplayer.py`: Passing client timestamps through the pipeline

## Future Improvements

Potential enhancements:
1. **Multiple RTT samples**: Average over last N pings instead of exponential smoothing
2. **Detect asymmetric routes**: Compare min vs max RTT over time
3. **NTP-style algorithm**: Use multiple timestamp exchanges for better accuracy
4. **Client-side metrics**: Track render delay, audio buffer delay
