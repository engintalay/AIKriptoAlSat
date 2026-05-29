from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import asyncio
import uvicorn
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.database import (
    init_db, save_scanned_coins, get_scanned_coins,
    save_signal, get_signals, save_ai_report, get_ai_report,
    save_chat_message, get_chat_history, toggle_favorite, get_favorites,
    get_pending_signals, update_signal_status, reset_signals
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
async def on_startup():
    init_db()
    print("Veritabanı başlatıldı. Sistem hazır.")
    from backend.ai_logger import set_loop
    set_loop(asyncio.get_event_loop())
    asyncio.create_task(background_scanner())

# --- API BAZLI SINIFLAR (Pydantic) ---
class ChatMessageRequest(BaseModel):
    message: str

class SettingsUpdateRequest(BaseModel):
    gemini_api_key: str = ""
    top_coins_limit: int = 50
    scan_interval_minutes: int = 15
    backtest_amount: float = 1000
    llm_provider: str = "gemini"
    ollama_model: str = "llama3"
    ollama_api_url: str = "http://localhost:11434"
    llamacpp_api_url: str = "http://localhost:8080"
    exchange: str = "binance"
    kucoin_api_key: str = ""
    kucoin_api_secret: str = ""
    kucoin_api_passphrase: str = ""
    kucoin_rate_limit: int = 60

# --- ARKA PLAN ZAMANLAYICI ---

async def background_scanner():
    """Sunucu çalıştığı sürece periyodik tarama yapar."""
    while True:
        interval = int(config.get_setting("SCAN_INTERVAL_MINUTES", 15))
        await asyncio.sleep(interval * 60)
        try:
            print(f"[BG] Arka plan taraması başlatılıyor...")
            result = await run_scan()
            print(f"[BG] Arka plan taraması tamamlandı. Sonraki: {interval} dk sonra.")
            if result:
                from backend.ai_logger import ai_log
                new_signals = [r for r in result if r.get("signal") in ["STRONG BUY", "STRONG SELL", "BUY", "SELL"]]
                ai_log("SCAN", f"Tarama tamamlandı: {len(result)} coin, {len(new_signals)} sinyal")
        except Exception as e:
            print(f"[BG] Arka plan tarama hatası: {e}")

# --- API UÇ NOKTALARI (API ENDPOINTS) ---

def check_pending_signals(scanned_results):
    """Açık sinyallerin TP/SL durumunu kontrol eder."""
    pending = get_pending_signals()
    if not pending:
        return
    
    # Tarama sonuçlarından fiyat haritası oluştur
    prices = {c["symbol"]: c["price"] for c in scanned_results}
    
    for sig in pending:
        symbol = sig["symbol"]
        current_price = prices.get(symbol)
        if not current_price:
            continue
        
        is_buy = sig["type"] == "BUY"
        
        if is_buy:
            if current_price <= sig["stop_loss"]:
                update_signal_status(sig["id"], "SL_HIT", current_price)
                print(f"[SIGNAL] {symbol} SL vurdu: {current_price:.4f} <= {sig['stop_loss']:.4f}")
            elif current_price >= sig["take_profit_2"]:
                update_signal_status(sig["id"], "TP2_HIT", current_price)
                print(f"[SIGNAL] {symbol} TP2 vurdu: {current_price:.4f} >= {sig['take_profit_2']:.4f}")
            elif current_price >= sig["take_profit_1"]:
                update_signal_status(sig["id"], "TP1_HIT", current_price)
                print(f"[SIGNAL] {symbol} TP1 vurdu: {current_price:.4f} >= {sig['take_profit_1']:.4f}")
        else:  # SELL
            if current_price >= sig["stop_loss"]:
                update_signal_status(sig["id"], "SL_HIT", current_price)
                print(f"[SIGNAL] {symbol} SL vurdu: {current_price:.4f} >= {sig['stop_loss']:.4f}")
            elif current_price <= sig["take_profit_2"]:
                update_signal_status(sig["id"], "TP2_HIT", current_price)
                print(f"[SIGNAL] {symbol} TP2 vurdu: {current_price:.4f} <= {sig['take_profit_2']:.4f}")
            elif current_price <= sig["take_profit_1"]:
                update_signal_status(sig["id"], "TP1_HIT", current_price)
                print(f"[SIGNAL] {symbol} TP1 vurdu: {current_price:.4f} <= {sig['take_profit_1']:.4f}")

# 1. Kripto Tarayıcı Tetikleme ve Listeleme

async def run_scan():
    """Tarama mantığı — hem endpoint hem background task tarafından kullanılır."""
    exchange = config.get_setting('EXCHANGE', 'Binance').upper()
    print(f"Yeni tarama işlemi başlatılıyor ({exchange} API'den canlı çekim)...")
    limit = int(config.get_setting("TOP_COINS_LIMIT", 50))
    print(f"[DEBUG] Tarama limiti: {limit}")
    top_pairs = data_fetcher.fetch_top_usdt_pairs(limit=limit)
    print(f"[DEBUG] Toplam {len(top_pairs)} coin çekildi")
    
    if not top_pairs:
        return None
    
    btc_dom = data_fetcher.fetch_btc_dominance()
    scanned_results = []
    
    def scan_single_coin(pair):
        """Tek bir coin için OHLCV çek ve analiz et."""
        symbol = pair["symbol"]
        df = data_fetcher.fetch_ohlcv(symbol, interval="1h", limit=100)
        if df is not None:
            return analyzer.analyze_coin_status(df, pair, btc_dominance=btc_dom)
        else:
            return {
                "symbol": symbol, "price": pair["price"], "volume": pair["volume"],
                "change_24h": pair["change_24h"], "rsi": 50.0, "macd_val": 0.0,
                "macd_sig": 0.0, "signal": "HOLD", "ai_score": 50,
                "details": {"reasons": ["Saatlik mum verisi çekilemedi."]}
            }
    
    # Paralel tarama (max 5 thread)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scan_single_coin, pair): pair for pair in top_pairs}
        for future in as_completed(futures):
            try:
                result = future.result(timeout=30)
                scanned_results.append(result)
            except Exception as e:
                pair = futures[future]
                print(f"[DEBUG] {pair['symbol']} tarama hatası: {e}")
    
    # Sinyal kaydet
    for analysis in scanned_results:
        if analysis["signal"] in ["STRONG BUY", "STRONG SELL"]:
            symbol = analysis["symbol"]
            recent_signals = get_signals(limit=10)
            already_exists = any(
                s["symbol"] == symbol and s["type"] == ("BUY" if "BUY" in analysis["signal"] else "SELL")
                for s in recent_signals
            )
            if not already_exists:
                entry = analysis["price"]
                is_buy = "BUY" in analysis["signal"]
                sl = entry * 0.97 if is_buy else entry * 1.03
                tp1 = entry * 1.03 if is_buy else entry * 0.97
                tp2 = entry * 1.07 if is_buy else entry * 0.93
                save_signal(symbol, "BUY" if is_buy else "SELL", entry, sl, tp1, tp2)

    print(f"[DEBUG] Toplam {len(scanned_results)} coin tarandı")
    save_scanned_coins(scanned_results)
    check_pending_signals(scanned_results)
    return scanned_results

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
                if datetime.now() - last_updated < timedelta(minutes=2):
                    favs = get_favorites()
                    for c in cached_coins:
                        c["is_favorite"] = c["symbol"] in favs
                    return {"status": "cached", "coins": cached_coins, "exchange": config.get_setting("EXCHANGE", "binance")}
            except Exception:
                pass

    result = await run_scan()
    
    if result is None:
        favs = get_favorites()
        for c in cached_coins:
            c["is_favorite"] = c["symbol"] in favs
        return {"status": "error_fallback_cached", "coins": cached_coins, "exchange": config.get_setting("EXCHANGE", "binance")}
    
    favs = get_favorites()
    final_coins = get_scanned_coins()
    for c in final_coins:
        c["is_favorite"] = c["symbol"] in favs
        
    return {"status": "success", "coins": final_coins, "exchange": config.get_setting("EXCHANGE", "binance")}

# 2. Tek Coin Fiyat Güncelleme
@app.get("/api/coin/{symbol}/refresh")
async def refresh_coin(symbol: str):
    """Tek bir coinin fiyat ve teknik verilerini günceller."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: _refresh_coin_sync(symbol))
    if result is None:
        raise HTTPException(status_code=404, detail=f"{symbol} verisi çekilemedi.")
    return result

def _refresh_coin_sync(symbol):
    df = data_fetcher.fetch_ohlcv(symbol, interval="1h", limit=100)
    if df is None:
        return None
    price = float(df["close"].iloc[-1])
    pair = {"symbol": symbol, "price": price, "volume": float(df["volume"].sum()), "change_24h": 0, "high_24h": float(df["high"].max()), "low_24h": float(df["low"].min())}
    if len(df) >= 24:
        old_price = float(df["close"].iloc[-24])
        pair["change_24h"] = round((price - old_price) / old_price * 100, 3)
    return analyzer.analyze_coin_status(df, pair)

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
    details = coin_data.get("details")
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except Exception:
            details = {}
    if not isinstance(details, dict):
        details = {}
        details = {}
    
    # Teknik verileri logla (AI'ya göndermeden önce ekranda göster)
    from backend.ai_logger import ai_log
    reasons = details.get("reasons", [])
    ai_log("INFO", f"[{symbol}] ═══ TEKNİK ANALİZ VERİLERİ ═══")
    ai_log("INFO", f"[{symbol}] Fiyat: {coin_data['price']} | Değişim: {coin_data['change_24h']}%")
    ai_log("INFO", f"[{symbol}] RSI: {coin_data.get('rsi', '-')} | MACD: {coin_data.get('macd_val', '-')} / {coin_data.get('macd_sig', '-')}")
    ai_log("INFO", f"[{symbol}] Sinyal: {coin_data['signal']} | AI Skor: {coin_data['ai_score']}")
    if reasons:
        ai_log("INFO", f"[{symbol}] Nedenler: {' | '.join(reasons)}")
    ai_log("INFO", f"[{symbol}] ═══════════════════════════════")
            
    # Rapor üret (executor'da çalıştır)
    print(f"{symbol} için AI Al-Sat Raporu hazırlanıyor...")
    ai_agent.reset_abort()
    report = await asyncio.get_event_loop().run_in_executor(
        ThreadPoolExecutor(max_workers=1),
        lambda: ai_agent.generate_ai_report(
        symbol=symbol,
        price=coin_data["price"],
        change_24h=coin_data["change_24h"],
        score=coin_data["ai_score"],
        signal=coin_data["signal"],
        details=details
    ))
    
    # Raporu veritabanına kaydet
    save_ai_report(symbol, coin_data["ai_score"], coin_data["signal"], report)
    
    return report

@app.post("/api/ai/abort")
async def abort_ai_request():
    """AI rapor/chat üretimini iptal eder."""
    ai_agent.abort_ai()
    return {"status": "aborted"}

@app.get("/api/ai/logs")
async def ai_logs_sse(request: Request):
    """AI loglarını SSE ile stream eder."""
    from backend.ai_logger import subscribe, unsubscribe, get_logs
    
    async def event_stream():
        queue = subscribe()
        try:
            # Önce mevcut logları gönder
            for log in get_logs():
                yield f"data: {log}\n\n"
            # Yeni logları dinle
            while True:
                if await request.is_disconnected():
                    break
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {entry}\n\n"
                except asyncio.TimeoutError:
                    yield f": keepalive\n\n"
        finally:
            unsubscribe(queue)
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")

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
    """AI tarafından üretilen sinyallerin listesini P&L ile döner."""
    signals = get_signals(limit=50)
    amount = float(config.get_setting("BACKTEST_AMOUNT", "1000"))
    
    for sig in signals:
        sig["investment"] = amount
        if sig["status"] == "PENDING":
            sig["pnl"] = 0
            sig["pnl_pct"] = 0
        else:
            entry = sig["entry_price"]
            closed = sig.get("closed_price") or entry
            is_buy = sig["type"] == "BUY"
            if is_buy:
                pnl_pct = (closed - entry) / entry * 100
            else:
                pnl_pct = (entry - closed) / entry * 100
            sig["pnl_pct"] = round(pnl_pct, 2)
            sig["pnl"] = round(amount * pnl_pct / 100, 2)
    
    return signals

@app.post("/api/signals/reset")
async def reset_trading_signals():
    """Tüm sinyal geçmişini siler."""
    reset_signals()
    return {"status": "ok"}

# 7. Ayarlar Servisleri
@app.get("/api/settings")
async def get_settings():
    """Güncel ayarları ve Gemini API anahtarının tanımlı olup olmadığını döner."""
    return {
        "gemini_api_key_configured": ai_agent.is_api_key_valid(),
        "top_coins_limit": int(config.get_setting("TOP_COINS_LIMIT", 50)),
        "scan_interval_minutes": int(config.get_setting("SCAN_INTERVAL_MINUTES", 15)),
        "backtest_amount": float(config.get_setting("BACKTEST_AMOUNT", 1000)),
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
    config.update_setting("BACKTEST_AMOUNT", str(req.backtest_amount))
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
