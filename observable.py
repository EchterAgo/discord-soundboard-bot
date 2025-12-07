"""Observable collection wrappers for triggering callbacks on modifications."""

import asyncio
from collections import deque, defaultdict
from typing import Callable, Optional


class ObservableDeque:
    """A deque wrapper that triggers a callback when modified."""
    
    def __init__(self, callback):
        self._deque = deque()
        self._callback = callback
    
    def append(self, item):
        result = self._deque.append(item)
        self._callback()
        return result
    
    def appendleft(self, item):
        result = self._deque.appendleft(item)
        self._callback()
        return result
    
    def pop(self):
        result = self._deque.pop()
        self._callback()
        return result
    
    def popleft(self):
        result = self._deque.popleft()
        self._callback()
        return result
    
    def clear(self):
        result = self._deque.clear()
        self._callback()
        return result
    
    def extend(self, items):
        result = self._deque.extend(items)
        self._callback()
        return result
    
    def __len__(self):
        return len(self._deque)
    
    def __bool__(self):
        return bool(self._deque)
    
    def __iter__(self):
        return iter(self._deque)
    
    def __getitem__(self, index):
        return self._deque[index]


class ObservableDict(dict):
    """A dict wrapper that triggers a callback when modified."""
    
    def __init__(self, callback=None):
        super().__init__()
        self._callback = callback
    
    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if self._callback:
            self._callback()
    
    def __delitem__(self, key):
        super().__delitem__(key)
        if self._callback:
            self._callback()
    
    def clear(self):
        super().clear()
        if self._callback:
            self._callback()
    
    def pop(self, *args):
        result = super().pop(*args)
        if self._callback:
            self._callback()
        return result
    
    def popitem(self):
        result = super().popitem()
        if self._callback:
            self._callback()
        return result
    
    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        if self._callback:
            self._callback()


class ObservableDequeDict(defaultdict):
    """A defaultdict of deques that triggers a callback when modified."""
    
    def __init__(self, on_change_callback=None):
        super().__init__(lambda: ObservableDeque(self._trigger_callback))
        self.on_change_callback = on_change_callback
    
    def _trigger_callback(self):
        """Trigger the change callback if set."""
        if self.on_change_callback:
            asyncio.create_task(self.on_change_callback())
    
    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._trigger_callback()
    
    def __delitem__(self, key):
        super().__delitem__(key)
        self._trigger_callback()
    
    def clear(self):
        super().clear()
        self._trigger_callback()
