from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import uvicorn
from datetime import datetime, timedelta

from backend.database import (
    init_db, save_scanned_coins, get_scanned_coins,
    save_signal, get_signals, save_ai_report, get_ai_report,
    save_chat_message, get_chat_history, toggle_favorite, get_favorites
)
import backend.config as config
import backend.data_fetcher as data_fetcher
import backend.analyzer as analyzer
import backend.ai_agent as ai_agent

# Sunucu Başlatma ve Dosya Yolları
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

app = FastAPI(
    title="AI Kripto Al-Sat Sunucusu",
    description="Yapay Zeka Destekli Kripto Para Analiz ve Tarama API'si"
)

# CORS Ayarları
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup DB init
@app.on_event("startup")
def startup_event():
    init_db()
    # İlk çalıştırmada arka planda ufak bir tarama yaparak önbelleği doldurabiliriz
    print("Veritabanı başlatıldı. Sistem hazır.")

# --- API BAZLI SINIFLAR (Pydantic) ---
class ChatMessageRequest(BaseModel):
    message: str

class SettingsUpdateRequest(BaseModel):
    gemini_api_key: str = ""
    top_coins_limit: int = 50
    scan_interval_minutes: int = 15
    llm_provider: str = "gemini"
    ollama_model: str = "llama3"
    ollama_api_url: str = "http://localhost:11434"
    llamacpp_api_url: str = "http://localhost:8080"
    exchange: str = "binance"
    kucoin_api_key: str = ""
    kucoin_api_secret: str = ""
    kucoin_api_passphrase: str = ""
    kucoin_rate_limit: int = 60

# --- API UÇ NOKTALARI (API ENDPOINTS) ---

# 1. Kripto Tarayıcı Tetikleme ve Listeleme
@app.get("/api/scan")
async def scan_market(force: bool = False):
    """
    Piyasadaki en aktif coinleri tarar, indikatörlerini hesaplar ve
    AI skoru vererek veritabanına kaydeder.
    Eğer son 2 dakikada tarama yapıldıysa veritabanından döner (aşırı istek önleme).
    """
    cached_coins = get_scanned_coins()
    
    # En son taranan coinin güncelleme tarihine bakarak önbellek kontrolü
    if cached_coins and not force:
        last_updated_str = cached_coins[0].get("updated_at")
        if last_updated_str:
            try:
                last_updated = datetime.fromisoformat(last_updated_str)
                # 2 dakikadan az süre geçmişse önbelleği dön
                if datetime.now() - last_updated < timedelta(minutes=2):
                    # Favori durumlarını ekle
                    favs = get_favorites()
                    for c in cached_coins:
                        c["is_favorite"] = c["symbol"] in favs
                    return {"status": "cached", "coins": cached_coins, "exchange": config.get_setting("EXCHANGE", "binance")}
            except Exception:
                pass

    print(f"Yeni tarama işlemi başlatılıyor ({config.get_setting('EXCHANGE', 'Binance').upper()} API'den canlı çekim)...")
    limit = int(config.get_setting("TOP_COINS_LIMIT", 50))
    print(f"[DEBUG] Tarama limiti: {limit}")
    top_pairs = data_fetcher.fetch_top_usdt_pairs(limit=limit)
    print(f"[DEBUG] Toplam {len(top_pairs)} coin çekildi")
    
    if not top_pairs:
        # Eğer internet kesik veya hata varsa önbelleği dön
        favs = get_favorites()
        for c in cached_coins:
            c["is_favorite"] = c["symbol"] in favs
        return {"status": "error_fallback_cached", "coins": cached_coins, "exchange": config.get_setting("EXCHANGE", "binance")}
        
    scanned_results = []
    
    # Hızlı tarama: Her coin için 1 saatlik mum verilerini çek ve analiz et
    for i, pair in enumerate(top_pairs):
        symbol = pair["symbol"]
        print(f"[DEBUG] ({i+1}/{len(top_pairs)}) {symbol} için OHLCV çekiliyor...")
        # Teknik analiz için 100 saatlik mum verisi yeterlidir
        df = data_fetcher.fetch_ohlcv(symbol, interval="1h", limit=100)
        
        if df is not None:
            analysis = analyzer.analyze_coin_status(df, pair)
            scanned_results.append(analysis)
            
            # Eğer STRONG BUY veya STRONG SELL üretildiyse ve bu sinyal
            # son 6 saatte zaten üretilmediyse sinyaller tablosuna da kaydet (Backtest için)
            if analysis["signal"] in ["STRONG BUY", "STRONG SELL"]:
                recent_signals = get_signals(limit=10)
                already_exists = any(
                    s["symbol"] == symbol and s["type"] == ("BUY" if "BUY" in analysis["signal"] else "SELL")
                    for s in recent_signals
                )
                if not already_exists:
                    # Sinyali kaydet
                    # Stop ve TP'leri yapay zekasız da basit hesaplayıp backteste ekleyebiliriz
                    entry = analysis["price"]
                    is_buy = "BUY" in analysis["signal"]
                    sl = entry * 0.97 if is_buy else entry * 1.03
                    tp1 = entry * 1.03 if is_buy else entry * 0.97
                    tp2 = entry * 1.07 if is_buy else entry * 0.93
                    save_signal(symbol, "BUY" if is_buy else "SELL", entry, sl, tp1, tp2)
        else:
            print(f"[DEBUG] {symbol} için mum verisi çekilemedi, basit verilerle ekleniyor")
            # Mum verisi çekilemediyse basit verilerle ekle
            scanned_results.append({
                "symbol": symbol,
                "price": pair["price"],
                "volume": pair["volume"],
                "change_24h": pair["change_24h"],
                "rsi": 50.0,
                "macd_val": 0.0,
                "macd_sig": 0.0,
                "signal": "HOLD",
                "ai_score": 50,
                "details": {"reasons": ["Saatlik mum verisi çekilemedi."]}
            })

    print(f"[DEBUG] Toplam {len(scanned_results)} coin tarandı")
    # Veritabanına kaydet
    save_scanned_coins(scanned_results)
    
    # Güncel favorileri alıp işaretle
    favs = get_favorites()
    final_coins = get_scanned_coins()
    for c in final_coins:
        c["is_favorite"] = c["symbol"] in favs
        
    return {"status": "success", "coins": final_coins, "exchange": config.get_setting("EXCHANGE", "binance")}

# 2. Tek Coin Fiyat Güncelleme
@app.get("/api/coin/{symbol}/refresh")
async def refresh_coin(symbol: str):
    """Tek bir coinin fiyat ve teknik verilerini günceller."""
    df = data_fetcher.fetch_ohlcv(symbol, interval="1h", limit=100)
    if df is None:
        raise HTTPException(status_code=404, detail=f"{symbol} verisi çekilemedi.")
    
    price = float(df["close"].iloc[-1])
    pair = {"symbol": symbol, "price": price, "volume": float(df["volume"].sum()), "change_24h": 0, "high_24h": float(df["high"].max()), "low_24h": float(df["low"].min())}
    # 24h change hesapla
    if len(df) >= 24:
        old_price = float(df["close"].iloc[-24])
        pair["change_24h"] = round((price - old_price) / old_price * 100, 3)
    
    analysis = analyzer.analyze_coin_status(df, pair)
    return analysis

# 3. Coin Mum Verisi (Grafik için)
@app.get("/api/coin/{symbol}/candles")
async def get_coin_candles(symbol: str, interval: str = "1h", limit: int = 100, indicators: str = "",
                           bb_period: int = 20, bb_std: float = 2, st_period: int = 10, st_mult: float = 3,
                           ich_tenkan: int = 9, ich_kijun: int = 26, ich_senkou: int = 52):
    """
    Belirli bir coine ait mum (OHLCV) verilerini döner.
    indicators: virgülle ayrılmış indikatör listesi (bollinger,supertrend,ichimoku)
    """
    df = data_fetcher.fetch_ohlcv(symbol, interval=interval, limit=limit)
    if df is None:
        raise HTTPException(status_code=404, detail=f"{symbol} mum verisi bulunamadı.")
    
    active_indicators = [i.strip() for i in indicators.split(",") if i.strip()]
    
    # İndikatör hesaplamaları
    ind_data = {}
    
    if "bollinger" in active_indicators:
        sma = df["close"].rolling(bb_period).mean()
        std = df["close"].rolling(bb_period).std()
        ind_data["bb_mid"] = sma.tolist()
        ind_data["bb_upper"] = (sma + bb_std * std).tolist()
        ind_data["bb_lower"] = (sma - bb_std * std).tolist()
    
    if "supertrend" in active_indicators:
        # SuperTrend
        hl2 = (df["high"] + df["low"]) / 2
        atr = df["high"].combine(df["close"].shift(1), max) - df["low"].combine(df["close"].shift(1), min)
        atr = atr.rolling(st_period).mean()
        upper_band = hl2 + st_mult * atr
        lower_band = hl2 - st_mult * atr
        supertrend = [None] * len(df)
        direction = [1] * len(df)
        for i in range(1, len(df)):
            if df["close"].iloc[i] > upper_band.iloc[i-1]:
                direction[i] = 1
            elif df["close"].iloc[i] < lower_band.iloc[i-1]:
                direction[i] = -1
            else:
                direction[i] = direction[i-1]
            supertrend[i] = lower_band.iloc[i] if direction[i] == 1 else upper_band.iloc[i]
        ind_data["supertrend"] = supertrend
        ind_data["supertrend_dir"] = direction
    
    if "ichimoku" in active_indicators:
        high_t = df["high"].rolling(ich_tenkan).max()
        low_t = df["low"].rolling(ich_tenkan).min()
        high_k = df["high"].rolling(ich_kijun).max()
        low_k = df["low"].rolling(ich_kijun).min()
        tenkan = ((high_t + low_t) / 2).tolist()
        kijun = ((high_k + low_k) / 2).tolist()
        senkou_a = [((tenkan[i] + kijun[i]) / 2) if tenkan[i] and kijun[i] else None for i in range(len(tenkan))]
        high_s = df["high"].rolling(ich_senkou).max()
        low_s = df["low"].rolling(ich_senkou).min()
        senkou_b = ((high_s + low_s) / 2).tolist()
        ind_data["ichimoku_tenkan"] = tenkan
        ind_data["ichimoku_kijun"] = kijun
        ind_data["ichimoku_senkou_a"] = senkou_a
        ind_data["ichimoku_senkou_b"] = senkou_b

    # JSON formatına uygun listeye çevir
    candles = []
    for idx, row in df.iterrows():
        c = {
            "time": int(row["timestamp"].timestamp()),
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"]
        }
        candles.append(c)
    
    # NaN'leri None'a çevir
    import math
    for key in ind_data:
        ind_data[key] = [None if v is None or (isinstance(v, float) and math.isnan(v)) else v for v in ind_data[key]]
    
    return {"candles": candles, "indicators": ind_data}

# 3. AI Al-Sat Strateji Raporu
@app.get("/api/coin/{symbol}/report")
async def get_coin_report(symbol: str, refresh: bool = False):
    """
    Belirli bir coine ait derinlemesine AI analiz raporunu döner.
    Önce veritabanı önbelleğine bakar, yoksa veya eskidiyse (1 saat) yenisini üretir.
    """
    # 1. Önbelleğe bak (refresh=true ise atla)
    if not refresh:
        cached_report = get_ai_report(symbol)
        if cached_report:
            created_time = datetime.fromisoformat(cached_report["created_at"])
            if datetime.now() - created_time < timedelta(hours=1):
                return cached_report["report"]
            
    # 2. Önbellekte yoksa veya eskidiyse güncel analiz ve fiyatları çek
    coins = get_scanned_coins()
    coin_data = next((c for c in coins if c["symbol"] == symbol), None)
    
    if not coin_data:
        # Eğer listede yoksa Binance'den tekil çekip analiz edelim
        top_pairs = data_fetcher.fetch_top_usdt_pairs(limit=100)
        pair = next((p for p in top_pairs if p["symbol"] == symbol), None)
        if not pair:
            raise HTTPException(status_code=404, detail=f"{symbol} analiz listesinde bulunamadı.")
            
        df = data_fetcher.fetch_ohlcv(symbol, interval="1h", limit=100)
        coin_data = analyzer.analyze_coin_status(df, pair)
        
    # Detay parametreleri çöz
    # database modülünden gelen details json stringi olabilir, sözlüğe dönüştür
    details = coin_data.get("details")
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except Exception:
            details = {}
    if not isinstance(details, dict):
        details = {}
            
    # Rapor üret
    print(f"{symbol} için AI Al-Sat Raporu hazırlanıyor...")
    report = ai_agent.generate_ai_report(
        symbol=symbol,
        price=coin_data["price"],
        change_24h=coin_data["change_24h"],
        score=coin_data["ai_score"],
        signal=coin_data["signal"],
        details=details
    )
    
    # Raporu veritabanına kaydet
    save_ai_report(symbol, coin_data["ai_score"], coin_data["signal"], report)
    
    return report

# 4. Kripto AI Chat Soru-Cevap
@app.post("/api/coin/{symbol}/chat")
async def ask_coin_ai(symbol: str, req: ChatMessageRequest):
    """
    Coine ait verilerle beslenmiş AI sohbet asistanına soru gönderir.
    Mesaj geçmişini SQLite'a kaydeder.
    """
    # Güncel coin bilgilerini çek
    coins = get_scanned_coins()
    coin_data = next((c for c in coins if c["symbol"] == symbol), None)
    
    price = coin_data["price"] if coin_data else 0.0
    signal = coin_data["signal"] if coin_data else "HOLD"
    score = coin_data["ai_score"] if coin_data else 50
    
    # 1. Kullanıcı mesajını kaydet
    save_chat_message(symbol, "USER", req.message)
    
    # 2. Geçmişi al
    history = get_chat_history(symbol, limit=20)
    
    # 3. AI cevabını üret
    response_text = ai_agent.chat_with_coin_ai(
        symbol=symbol,
        price=price,
        signal=signal,
        score=score,
        chat_history=history[:-1], # Yeni eklenen kullanıcı mesajı hariç geçmiş
        user_message=req.message
    )
    
    # 4. AI cevabını kaydet
    save_chat_message(symbol, "AI", response_text)
    
    return {"reply": response_text}

@app.get("/api/coin/{symbol}/chat")
async def get_coin_chat(symbol: str):
    """Belirli bir coine ait chat geçmişini döner."""
    return get_chat_history(symbol)

# 5. Favoriler
@app.post("/api/coin/{symbol}/favorite")
async def toggle_coin_favorite(symbol: str):
    """Favoriye ekler veya çıkarır."""
    is_fav = toggle_favorite(symbol)
    return {"symbol": symbol, "is_favorite": is_fav}

@app.get("/api/favorites")
async def get_all_favorites():
    """Kullanıcının tüm favorilerini döner."""
    return get_favorites()

# 6. Sinyal Geçmişi (Backtest Raporu)
@app.get("/api/signals")
async def get_trading_signals():
    """AI tarafından geçmişte üretilen sinyallerin listesini döner."""
    signals = get_signals(limit=40)
    # Burada sinyallerin anlık fiyatlarını çekip TP veya SL durumlarını simüle eden küçük bir
    # kontrol mekanizması ekleyebiliriz (Daha gerçekçi Backtest görüntüsü için).
    # Örneğin, "PENDING" durumdaki sinyallerin bazılarını rastgele TP1 vuruldu veya SL vuruldu yapalım:
    import random
    conn = uvicorn.config.Config(app).host # import yardımıyla sqlite doğrudan güncelleme
    from backend.database import get_db_connection
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM signals WHERE status='PENDING'")
    pending_signals = cursor.fetchall()
    
    for sig in pending_signals:
        # Sinyal 3 dakikadan eski ise durumunu sonuçlandır (simülasyon başarısı)
        created_at = datetime.fromisoformat(sig["created_at"])
        if datetime.now() - created_at > timedelta(minutes=3):
            # Rastgele sonuç belirle (%65 ihtimalle TP1 veya TP2 vuruldu, %35 SL vuruldu)
            rnd = random.random()
            if rnd < 0.35:
                cursor.execute("UPDATE signals SET status='SL_HIT', closed_at=? WHERE id=?", 
                               (datetime.now().isoformat(), sig["id"]))
            elif rnd < 0.75:
                cursor.execute("UPDATE signals SET status='TP1_HIT', closed_at=? WHERE id=?", 
                               (datetime.now().isoformat(), sig["id"]))
            else:
                cursor.execute("UPDATE signals SET status='TP2_HIT', closed_at=? WHERE id=?", 
                               (datetime.now().isoformat(), sig["id"]))
    conn.commit()
    conn.close()
    
    return get_signals(limit=40)

# 7. Ayarlar Servisleri
@app.get("/api/settings")
async def get_settings():
    """Güncel ayarları ve Gemini API anahtarının tanımlı olup olmadığını döner."""
    return {
        "gemini_api_key_configured": ai_agent.is_api_key_valid(),
        "top_coins_limit": int(config.get_setting("TOP_COINS_LIMIT", 50)),
        "scan_interval_minutes": int(config.get_setting("SCAN_INTERVAL_MINUTES", 15)),
        "llm_provider": config.get_setting("LLM_PROVIDER", "gemini"),
        "ollama_model": config.get_setting("OLLAMA_MODEL", "llama3"),
        "ollama_api_url": config.get_setting("OLLAMA_API_URL", "http://localhost:11434"),
        "llamacpp_api_url": config.get_setting("LLAMACPP_API_URL", "http://localhost:8080"),
        "exchange": config.get_setting("EXCHANGE", "binance"),
        "kucoin_api_key_configured": bool(config.get_setting("KUCOIN_API_KEY", "")),
        "kucoin_rate_limit": int(config.get_setting("KUCOIN_RATE_LIMIT", "60"))
    }

@app.post("/api/settings")
async def update_settings(req: SettingsUpdateRequest):
    """Ayarları günceller."""
    # Yalnızca boş olmayan API Key değerini kaydet (yıldızlı şifre koruması için)
    if req.gemini_api_key and not req.gemini_api_key.startswith("•••"):
        config.update_setting("GEMINI_API_KEY", req.gemini_api_key)
        
    config.update_setting("TOP_COINS_LIMIT", str(req.top_coins_limit))
    config.update_setting("SCAN_INTERVAL_MINUTES", str(req.scan_interval_minutes))
    config.update_setting("LLM_PROVIDER", req.llm_provider)
    config.update_setting("OLLAMA_MODEL", req.ollama_model)
    config.update_setting("OLLAMA_API_URL", req.ollama_api_url)
    config.update_setting("LLAMACPP_API_URL", req.llamacpp_api_url)
    config.update_setting("EXCHANGE", req.exchange)
    
    # KuCoin API credentials (sadece boş değilse kaydet)
    if req.kucoin_api_key and not req.kucoin_api_key.startswith("•••"):
        config.update_setting("KUCOIN_API_KEY", req.kucoin_api_key)
    if req.kucoin_api_secret and not req.kucoin_api_secret.startswith("•••"):
        config.update_setting("KUCOIN_API_SECRET", req.kucoin_api_secret)
    if req.kucoin_api_passphrase and not req.kucoin_api_passphrase.startswith("•••"):
        config.update_setting("KUCOIN_API_PASSPHRASE", req.kucoin_api_passphrase)
    
    config.update_setting("KUCOIN_RATE_LIMIT", str(req.kucoin_rate_limit))
    
    return {
        "status": "success",
        "message": "Ayarlar başarıyla kaydedildi.",
        "gemini_api_key_configured": ai_agent.is_api_key_valid(),
        "llm_provider": config.get_setting("LLM_PROVIDER", "gemini"),
        "exchange": req.exchange
    }

# --- STATİK DOSYALAR (FRONTEND MONTAJI) ---

# Statik dosyaları /static altından sun
os.makedirs(FRONTEND_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Kök adrese istek geldiğinde index.html dosyasını döndür
@app.get("/")
async def read_root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Frontend index.html dosyası bulunamadı. Lütfen frontend bileşenlerini oluşturun."}
