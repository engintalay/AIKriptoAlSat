import sqlite3
import os
import json
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_scanner.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Veritabanı tablolarını oluşturur."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Taranan Coin Önbelleği Tablosu
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scanned_coins (
        symbol TEXT PRIMARY KEY,
        price REAL,
        volume REAL,
        change_24h REAL,
        rsi REAL,
        macd_val REAL,
        macd_sig REAL,
        signal TEXT,
        ai_score INTEGER,
        details TEXT,
        updated_at TEXT
    )
    """)
    
    # 2. Üretilen Al-Sat Sinyalleri (Backtest için)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        type TEXT, -- BUY, SELL
        entry_price REAL,
        stop_loss REAL,
        take_profit_1 REAL,
        take_profit_2 REAL,
        status TEXT, -- PENDING, TP1_HIT, TP2_HIT, SL_HIT
        closed_price REAL,
        created_at TEXT,
        closed_at TEXT
    )
    """)
    # closed_price sütunu yoksa ekle (migration)
    try:
        cursor.execute("ALTER TABLE signals ADD COLUMN closed_price REAL")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE scanned_coins ADD COLUMN details TEXT")
    except:
        pass
    # 3. AI Rapor Önbelleği
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_reports (
        symbol TEXT PRIMARY KEY,
        score INTEGER,
        trend TEXT,
        report_json TEXT,
        created_at TEXT
    )
    """)
    
    # 4. Chat Geçmişi
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        sender TEXT, -- USER, AI
        message TEXT,
        created_at TEXT
    )
    """)
    
    # 5. Favoriler
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS favorites (
        symbol TEXT PRIMARY KEY
    )
    """)
    
    conn.commit()
    conn.close()

# --- VERİTABANI YARDIMCI FONKSİYONLARI ---

def save_scanned_coins(coins_list):
    """Tarama sonuçlarını veritabanına kaydeder."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    for coin in coins_list:
        cursor.execute("""
        INSERT INTO scanned_coins (symbol, price, volume, change_24h, rsi, macd_val, macd_sig, signal, ai_score, details, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            price=excluded.price,
            volume=excluded.volume,
            change_24h=excluded.change_24h,
            rsi=excluded.rsi,
            macd_val=excluded.macd_val,
            macd_sig=excluded.macd_sig,
            signal=excluded.signal,
            ai_score=excluded.ai_score,
            details=excluded.details,
            updated_at=?
        """, (
            coin["symbol"], coin["price"], coin["volume"], coin["change_24h"],
            coin["rsi"], coin["macd_val"], coin["macd_sig"], coin["signal"],
            coin["ai_score"], json.dumps(coin.get("details", {})), now_str, now_str
        ))
    conn.commit()
    conn.close()

def get_scanned_coins():
    """Son taramada güncellenen coinleri döner."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Son 60 dakika içinde güncellenen coinleri getir
    cutoff = (datetime.now() - timedelta(minutes=60)).isoformat()
    cursor.execute("SELECT * FROM scanned_coins WHERE updated_at > ? ORDER BY ai_score DESC", (cutoff,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def save_signal(symbol, sig_type, entry, sl, tp1, tp2):
    """Yeni bir Al-Sat sinyali oluşturur."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO signals (symbol, type, entry_price, stop_loss, take_profit_1, take_profit_2, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
    """, (symbol, sig_type, entry, sl, tp1, tp2, now_str))
    conn.commit()
    conn.close()

def get_signals(limit=20):
    """Geçmiş sinyalleri döner."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_pending_signals():
    """Henüz sonuçlanmamış (PENDING) sinyalleri döner."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM signals WHERE status='PENDING'")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_signal_status(signal_id, status, closed_price=None):
    """Sinyal durumunu günceller (örn: TP1 vurdu)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute("UPDATE signals SET status=?, closed_price=?, closed_at=? WHERE id=?", (status, closed_price, now_str, signal_id))
    conn.commit()
    conn.close()

def save_ai_report(symbol, score, trend, report_dict):
    """AI raporunu kaydeder/günceller."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO ai_reports (symbol, score, trend, report_json, created_at)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(symbol) DO UPDATE SET
        score=excluded.score,
        trend=excluded.trend,
        report_json=excluded.report_json,
        created_at=?
    """, (symbol, score, trend, json.dumps(report_dict), now_str, now_str))
    conn.commit()
    conn.close()

def get_ai_report(symbol):
    """Kayıtlı AI raporunu getirir."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ai_reports WHERE symbol=?", (symbol,))
    row = cursor.fetchone()
    conn.close()
    if row:
        res = dict(row)
        res["report"] = json.loads(res["report_json"])
        return res
    return None

def save_chat_message(symbol, sender, message):
    """Chat mesajını kaydeder."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO chat_history (symbol, sender, message, created_at)
    VALUES (?, ?, ?, ?)
    """, (symbol, sender, message, now_str))
    conn.commit()
    conn.close()

def get_chat_history(symbol, limit=30):
    """Belirli bir coine ait chat geçmişini döner."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM chat_history WHERE symbol=? ORDER BY id ASC LIMIT ?", (symbol, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def toggle_favorite(symbol):
    """Favoriyi açar/kapatır ve güncel durumu döner."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM favorites WHERE symbol=?", (symbol,))
    row = cursor.fetchone()
    is_fav = False
    if row:
        cursor.execute("DELETE FROM favorites WHERE symbol=?", (symbol,))
    else:
        cursor.execute("INSERT INTO favorites (symbol) VALUES (?)", (symbol,))
        is_fav = True
    conn.commit()
    conn.close()
    return is_fav

def get_favorites():
    """Tüm favori coinleri döner."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT symbol FROM favorites")
    rows = cursor.fetchall()
    conn.close()
    return [row["symbol"] for row in rows]

def reset_signals():
    """Tüm sinyalleri siler."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM signals")
    conn.commit()
    conn.close()
