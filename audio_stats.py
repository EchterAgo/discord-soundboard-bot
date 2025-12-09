"""Audio pipeline latency statistics tracking."""

import time
import threading
import logging
from collections import deque
from dataclasses import dataclass
from typing import Dict, Optional
import statistics

_log = logging.getLogger(__name__)


@dataclass
class AudioPipelineStats:
    """Statistics for a single audio playback request."""

    user_id: int
    user_name: str
    filepath: str
    request_timestamp: float
    queue_timestamp: Optional[float] = None  # When added to queue
    stream_start_timestamp: Optional[float] = None  # When ffmpeg process started
    first_byte_timestamp: Optional[float] = None  # When first byte was decoded
    stream_end_timestamp: Optional[float] = None  # When playback finished

    # Latency metrics (in milliseconds)
    queue_latency: Optional[float] = None  # Time from request to queue
    processing_latency: Optional[float] = None  # Time from queue to stream start
    decode_latency: Optional[float] = None  # Time from stream start to first byte
    total_latency: Optional[float] = None  # Time from request to first byte
    playback_duration: Optional[float] = None  # Total playback time

    def calculate_latencies(self):
        """Calculate all latency metrics."""
        if self.queue_timestamp:
            self.queue_latency = (self.queue_timestamp - self.request_timestamp) * 1000

        if self.stream_start_timestamp and self.queue_timestamp:
            self.processing_latency = (self.stream_start_timestamp - self.queue_timestamp) * 1000

        if self.first_byte_timestamp and self.stream_start_timestamp:
            self.decode_latency = (self.first_byte_timestamp - self.stream_start_timestamp) * 1000

        if self.first_byte_timestamp:
            self.total_latency = (self.first_byte_timestamp - self.request_timestamp) * 1000

        if self.stream_end_timestamp and self.stream_start_timestamp:
            self.playback_duration = (self.stream_end_timestamp - self.stream_start_timestamp) * 1000

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "filepath": self.filepath.split("/")[-1] if isinstance(self.filepath, str) else str(self.filepath),
            "request_timestamp": self.request_timestamp,
            "queue_timestamp": self.queue_timestamp,
            "stream_start_timestamp": self.stream_start_timestamp,
            "first_byte_timestamp": self.first_byte_timestamp,
            "stream_end_timestamp": self.stream_end_timestamp,
            "queue_latency": round(self.queue_latency, 2) if self.queue_latency else None,
            "processing_latency": round(self.processing_latency, 2) if self.processing_latency else None,
            "decode_latency": round(self.decode_latency, 2) if self.decode_latency else None,
            "total_latency": round(self.total_latency, 2) if self.total_latency else None,
            "playback_duration": round(self.playback_duration, 2) if self.playback_duration else None,
        }


class AudioStatsCollector:
    """Collects and aggregates audio pipeline statistics."""

    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self.history: deque = deque(maxlen=max_history)
        self.active_stats: Dict[int, AudioPipelineStats] = {}  # user_id -> current stats
        self.lock = threading.Lock()

    def start_request(self, user_id: int, user_name: str, filepath: str, timestamp: Optional[float] = None) -> float:
        """Start tracking a new audio request.

        Args:
            user_id: User ID making the request
            user_name: User name
            filepath: Path to audio file
            timestamp: Optional timestamp (defaults to current time)

        Returns:
            Request timestamp
        """
        if timestamp is None:
            timestamp = time.time()

        with self.lock:
            # Don't overwrite if we're already tracking this user
            if user_id not in self.active_stats:
                stats = AudioPipelineStats(
                    user_id=user_id, user_name=user_name, filepath=filepath, request_timestamp=timestamp
                )
                self.active_stats[user_id] = stats
                _log.debug(f"[STATS] Started tracking request for {user_name} (ID: {user_id})")
            else:
                _log.debug(f"[STATS] Already tracking {user_name} (ID: {user_id}), not overwriting")

        return timestamp

    def mark_queued(self, user_id: int):
        """Mark when a request was added to the queue."""
        with self.lock:
            if user_id in self.active_stats:
                now = time.time()
                # Ensure queue_timestamp is never earlier than request_timestamp
                # (can happen due to clock skew between client and server)
                self.active_stats[user_id].queue_timestamp = max(now, self.active_stats[user_id].request_timestamp)
                _log.debug(f"[STATS] Marked queued for user ID: {user_id}")
            else:
                _log.warning(f"[STATS] Cannot mark queued - user ID {user_id} not in active_stats")

    def mark_stream_start(self, user_id: int):
        """Mark when the ffmpeg stream was started."""
        with self.lock:
            if user_id in self.active_stats:
                self.active_stats[user_id].stream_start_timestamp = time.time()
                _log.debug(f"[STATS] Marked stream start for user ID: {user_id}")
            else:
                _log.warning(f"[STATS] Cannot mark stream start - user ID {user_id} not in active_stats")

    def mark_first_byte(self, user_id: int):
        """Mark when the first audio byte was decoded."""
        with self.lock:
            if user_id in self.active_stats:
                stats = self.active_stats[user_id]
                stats.first_byte_timestamp = time.time()
                stats.calculate_latencies()
                total = f"{stats.total_latency:.2f}" if stats.total_latency is not None else "N/A"
                decode = f"{stats.decode_latency:.2f}" if stats.decode_latency is not None else "N/A"
                _log.info(
                    f"[STATS] First byte for user ID {user_id}: total_latency={total}ms, decode_latency={decode}ms"
                )
            else:
                _log.warning(f"[STATS] Cannot mark first byte - user ID {user_id} not in active_stats")

    def mark_stream_end(self, user_id: int):
        """Mark when the stream finished and archive the stats."""
        with self.lock:
            if user_id in self.active_stats:
                stats = self.active_stats[user_id]
                stats.stream_end_timestamp = time.time()
                stats.calculate_latencies()
                
                # For interrupted streams that never got first byte, calculate partial total latency
                # using stream_end as the endpoint instead of first_byte
                if stats.total_latency is None and stats.stream_end_timestamp:
                    stats.total_latency = (stats.stream_end_timestamp - stats.request_timestamp) * 1000
                    _log.debug(f"[STATS] Stream interrupted before first byte, using end time for total latency")

                total = f"{stats.total_latency:.2f}" if stats.total_latency is not None else "N/A"
                playback = f"{stats.playback_duration:.2f}" if stats.playback_duration is not None else "N/A"
                _log.info(f"[STATS] Archived stats for user ID {user_id}: total={total}ms, playback={playback}ms")

                # Archive to history
                self.history.append(stats)

                # Remove from active
                del self.active_stats[user_id]
            else:
                _log.warning(f"[STATS] Cannot mark stream end - user ID {user_id} not in active_stats")

    def get_summary(self) -> Dict:
        """Get a summary of collected statistics.

        Returns:
            Dictionary containing:
            - recent: List of recent stats (last N entries)
            - averages: Average latency metrics
            - percentiles: 50th, 95th, 99th percentile latencies
            - active: Currently active streams
        """
        with self.lock:
            recent = [stats.to_dict() for stats in list(self.history)[-20:]]

            # Calculate latencies for active stats before converting to dict
            active = []
            for stats in self.active_stats.values():
                stats.calculate_latencies()
                active.append(stats.to_dict())

            # Calculate aggregates
            if self.history:
                total_latencies = [s.total_latency for s in self.history if s.total_latency is not None]
                queue_latencies = [s.queue_latency for s in self.history if s.queue_latency is not None]
                processing_latencies = [s.processing_latency for s in self.history if s.processing_latency is not None]
                decode_latencies = [s.decode_latency for s in self.history if s.decode_latency is not None]

                averages = {}
                percentiles = {}

                if total_latencies:
                    averages["total"] = round(statistics.mean(total_latencies), 2)
                    percentiles["total"] = {
                        "p50": round(statistics.median(total_latencies), 2),
                        "p95": (
                            round(statistics.quantiles(total_latencies, n=20)[18], 2)
                            if len(total_latencies) >= 20
                            else None
                        ),
                        "p99": (
                            round(statistics.quantiles(total_latencies, n=100)[98], 2)
                            if len(total_latencies) >= 100
                            else None
                        ),
                    }

                if queue_latencies:
                    averages["queue"] = round(statistics.mean(queue_latencies), 2)

                if processing_latencies:
                    averages["processing"] = round(statistics.mean(processing_latencies), 2)

                if decode_latencies:
                    averages["decode"] = round(statistics.mean(decode_latencies), 2)
                    percentiles["decode"] = {
                        "p50": round(statistics.median(decode_latencies), 2),
                        "p95": (
                            round(statistics.quantiles(decode_latencies, n=20)[18], 2)
                            if len(decode_latencies) >= 20
                            else None
                        ),
                        "p99": (
                            round(statistics.quantiles(decode_latencies, n=100)[98], 2)
                            if len(decode_latencies) >= 100
                            else None
                        ),
                    }
            else:
                averages = {}
                percentiles = {}

        return {
            "recent": recent,
            "active": active,
            "averages": averages,
            "percentiles": percentiles,
            "total_samples": len(self.history),
        }

    def clear(self):
        """Clear all statistics."""
        with self.lock:
            self.history.clear()
            self.active_stats.clear()


# Global stats collector instance
audio_stats = AudioStatsCollector(max_history=100)
