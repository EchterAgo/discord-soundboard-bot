# Audio Mixing System

## Overview

The Discord soundboard bot now supports **per-user audio mixing**. Each user has their own queue, and multiple users' audio can play simultaneously, mixed together in real-time.

## How It Works

### Architecture

1. **Per-User Queues**: Each user (identified by user_id) has their own queue of sounds to play
2. **Mixed Audio Source**: A custom `MixedAudioSource` class that:
   - Manages multiple FFmpeg subprocess streams (one per active user)
   - Reads PCM audio data from each stream
   - Mixes them together using the `audioop` module
   - Feeds the mixed audio to Discord's voice client

3. **Queue Processing**: An async loop that:
   - Monitors all user queues
   - Starts new audio streams when users don't have an active stream
   - Removes finished streams
   - Stops when all queues are empty

### Key Components

#### `UserAudioStream`
- Represents one user's audio stream
- Runs FFmpeg as a subprocess to decode audio files
- Converts to 48kHz stereo 16-bit PCM (Discord's format)
- Reads audio data in chunks

#### `MixedAudioSource`
- Implements Discord's `AudioSource` interface
- Maintains a dictionary of active streams (user_id -> UserAudioStream)
- Reads from all streams and mixes using `audioop.add()`
- Thread-safe with locking

#### `AudioPlayer` (Updated)
- Now uses `user_queues: Dict[int, deque[QueueItem]]` instead of a single queue
- `queue_sound()` adds sounds to the user's personal queue
- `process_user_queues()` manages starting streams for each user
- `stop_playback()` clears all queues and stops the mixer

## Usage

### From Discord Commands

```
/p sound:ago/hallo.mp3
!play ago/hallo.mp3
```

Each user's sounds go into their own queue and will mix with other users' sounds.

### From Web Interface

```javascript
await playFile('ago/hallo.mp3');
```

The `user_name` cookie determines which queue the sound goes into.

### Queue Behavior

- **Normal queue**: Sounds are added to the end of your personal queue
- **Play next**: Sound is added to the front of your personal queue
- **Interrupt**: Clears YOUR queue only (doesn't affect other users)
- **Stop**: Clears ALL queues and stops all playback (admin function)

## Features

✅ **Simultaneous Playback**: Multiple users can play sounds at the same time
✅ **Per-User Queues**: Each user maintains their own queue
✅ **Real-time Mixing**: Audio streams are mixed on-the-fly
✅ **Automatic Cleanup**: Finished streams are automatically removed
✅ **Error Handling**: Failed streams don't crash the entire system

## Technical Details

### Audio Format
- Sample Rate: 48,000 Hz
- Channels: 2 (stereo)
- Bit Depth: 16-bit
- Format: Signed little-endian PCM

### Chunk Size
- 3,840 bytes per read (20ms of audio at 48kHz stereo 16-bit)

### Mixing Algorithm
- Uses `audioop.add()` to mix audio samples
- Combines all active streams' audio data
- Pads with silence if needed

## Requirements

- **FFmpeg**: Must be installed and available in PATH
- **Python packages**: `audioop` (built-in), `discord.py`, `subprocess`, `threading`

## Limitations

- Audio quality may degrade if too many streams play simultaneously
- CPU usage increases with the number of active streams
- FFmpeg must be installed on the system
- No volume control per stream (yet)
- No audio compression/limiting (clipping may occur with many streams)

## Future Enhancements

Possible improvements:
- Per-user volume control
- Audio compression/limiting to prevent clipping
- Maximum concurrent streams limit
- Priority system for queue processing
- Fade in/out effects
- Spatial audio (different users in different "positions")
