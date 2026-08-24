"""Small TTL cache so repeated analyse calls do not hit yt-dlp twice."""

import threading
import time


class TTLCache:
    def __init__(self, ttl=300):
        self._ttl = ttl
        self._entries = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None

            value, stamp = entry
            if time.time() - stamp >= self._ttl:
                del self._entries[key]
                return None
            return value

    def set(self, key, value):
        with self._lock:
            self._entries[key] = (value, time.time())

    def clear(self):
        with self._lock:
            self._entries.clear()


metadata_cache = TTLCache(ttl=300)
