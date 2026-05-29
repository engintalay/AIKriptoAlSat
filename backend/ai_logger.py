"""AI iletişim log modülü — in-memory, SSE ile frontend'e stream edilir."""
from collections import deque
from datetime import datetime
import asyncio

# Max 500 satır tutar, eski loglar silinir
_log_buffer = deque(maxlen=500)
_subscribers = []  # SSE bağlantıları

def ai_log(level, message):
    """Log ekle ve tüm subscriber'lara bildir."""
    entry = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {message}"
    _log_buffer.append(entry)
    # Subscriber'lara gönder
    for queue in _subscribers[:]:
        try:
            queue.put_nowait(entry)
        except:
            pass

def get_logs():
    return list(_log_buffer)

def subscribe():
    """Yeni SSE subscriber oluştur."""
    queue = asyncio.Queue()
    _subscribers.append(queue)
    return queue

def unsubscribe(queue):
    if queue in _subscribers:
        _subscribers.remove(queue)
