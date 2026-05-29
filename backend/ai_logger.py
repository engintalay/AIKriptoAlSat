"""AI iletişim log modülü — in-memory, SSE ile frontend'e stream edilir."""
from collections import deque
from datetime import datetime
import asyncio
import threading

# Max 500 satır tutar, eski loglar silinir
_log_buffer = deque(maxlen=500)
_subscribers = []  # SSE bağlantıları
_lock = threading.Lock()
_loop = None

def set_loop(loop):
    global _loop
    _loop = loop

def ai_log(level, message):
    """Log ekle ve tüm subscriber'lara bildir."""
    entry = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {message}"
    _log_buffer.append(entry)
    # Subscriber'lara gönder (thread-safe)
    with _lock:
        for queue in _subscribers[:]:
            try:
                if _loop and _loop.is_running():
                    _loop.call_soon_threadsafe(queue.put_nowait, entry)
                else:
                    queue.put_nowait(entry)
            except:
                pass

def get_logs():
    return list(_log_buffer)

def subscribe():
    """Yeni SSE subscriber oluştur."""
    queue = asyncio.Queue()
    with _lock:
        _subscribers.append(queue)
    return queue

def unsubscribe(queue):
    with _lock:
        if queue in _subscribers:
            _subscribers.remove(queue)
