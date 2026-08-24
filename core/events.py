"""Tiny fan-out event bus. Each subscriber gets its own bounded queue."""

import queue
import threading


class EventBus:
    def __init__(self, maxsize=512):
        self._subscribers = set()
        self._lock = threading.Lock()
        self._maxsize = maxsize

    def subscribe(self):
        """Register a listener and return its queue."""
        listener = queue.Queue(maxsize=self._maxsize)
        with self._lock:
            self._subscribers.add(listener)
        return listener

    def unsubscribe(self, listener):
        with self._lock:
            self._subscribers.discard(listener)

    def publish(self, event):
        """Broadcast an event. Slow listeners drop their oldest item."""
        with self._lock:
            listeners = list(self._subscribers)

        for listener in listeners:
            try:
                listener.put_nowait(event)
            except queue.Full:
                try:
                    listener.get_nowait()      # drop the stalest event
                    listener.put_nowait(event)
                except (queue.Empty, queue.Full):
                    pass

    @property
    def subscriber_count(self):
        with self._lock:
            return len(self._subscribers)
