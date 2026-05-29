import pandas as pd
import numpy as np

def calculate_indicators(df):
    """
    Pandas DataFrame üzerinde teknik analiz göstergelerini hesaplar.
    Dış kütüphaneye bağımlılığı en aza indirgemek için saf Pandas kullanılmıştır.
    """
    if df is None or len(df) < 50:
        return None
        
    # Copy to avoid modifying the original dataframe
    df = df.copy()
    
    # 1. EMA (Exponential Moving Average)
    df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()
    
    # 2. RSI (Relative Strength Index) - TradingView Wilder Modeli
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    # Exponential Weighted Moving Average (Wilder's Smoothing)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    
    rs = avg_gain / (avg_loss + 1e-10) # 0'a bölme hatasını engellemek için
    df["rsi"] = 100 - (100 / (1 + rs))
    
    # 3. MACD (Moving Average Convergence Divergence)
    ema_12 = df["close"].ewm(span=12, adjust=False).mean()
    ema_26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema_12 - ema_26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    
    # 4. Bollinger Bands (20, 2)
    df["bb_middle"] = df["close"].rolling(window=20).mean()
    df["bb_std"] = df["close"].rolling(window=20).std()
    df["bb_upper"] = df["bb_middle"] + (2 * df["bb_std"])
    df["bb_lower"] = df["bb_middle"] - (2 * df["bb_std"])
    
    # 5. ATR (Average True Range) - 14 periyot
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = true_range.rolling(window=14).mean()
    
    return df

def analyze_coin_status(df, ticker_info, btc_dominance=None):
    """
    Hesaplanan indikatörler ve ticker bilgilerine dayanarak 
    coine ait 0-100 arasında bir ticaret puanı ve sinyal üretir.
    """
    from backend.data_fetcher import fetch_btc_dominance
    
    df_ind = calculate_indicators(df)
    if df_ind is None or len(df_ind) == 0:
        return {
            "symbol": ticker_info["symbol"],
            "price": ticker_info["price"],
            "volume": ticker_info["volume"],
            "change_24h": ticker_info["change_24h"],
            "rsi": 50.0,
            "macd_val": 0.0,
            "macd_sig": 0.0,
            "signal": "HOLD",
            "ai_score": 50,
            "details": {}
        }
        
    # Son mum değerlerini al
    latest = df_ind.iloc[-1]
    prev_1 = df_ind.iloc[-2]
    prev_2 = df_ind.iloc[-3]
    
    close = latest["close"]
    rsi = latest["rsi"]
    macd = latest["macd"]
    macd_sig = latest["macd_signal"]
    ema_50 = latest["ema_50"]
    ema_200 = latest["ema_200"]
    bb_lower = latest["bb_lower"]
    bb_upper = latest["bb_upper"]
    
    # Başlangıç Skoru
    score = 50
    reasons = []
    
    # --- 1. TREND KRİTERLERİ (30 Puan) ---
    # Uzun vadeli trend kontrolü (EMA 200)
    if close > ema_200:
        score += 10
        reasons.append("Fiyat uzun vadeli yükseliş trendinde (EMA 200 üstünde).")
    else:
        score -= 10
        reasons.append("Fiyat uzun vadeli düşüş trendinde (EMA 200 altında).")
        
    # Kısa/Orta vadeli trend kontrolü (EMA 50)
    if close > ema_50:
        score += 5
    else:
        score -= 5
        
    # Golden Cross / Death Cross Kontrolü
    if ema_50 > ema_200 and prev_1["ema_50"] <= prev_1["ema_200"]:
        score += 15
        reasons.append("Golden Cross (Altın Kesişim) yeni tetiklendi! Güçlü boğa sinyali.")
    elif ema_50 < ema_200 and prev_1["ema_50"] >= prev_1["ema_200"]:
        score -= 15
        reasons.append("Death Cross (Ölüm Kesişim) yeni tetiklendi! Güçlü ayı sinyali.")
        
    # --- 2. MOMENTUM & GÜÇ KRİTERLERİ (35 Puan) ---
    # RSI Seviyeleri
    if rsi < 30:
        score += 15
        reasons.append(f"Aşırı Satım bölgesinde (RSI: {rsi:.1f}). Tepki yükselişi gelebilir.")
    elif rsi > 70:
        score -= 15
        reasons.append(f"Aşırı Alım bölgesinde (RSI: {rsi:.1f}). Kâr realizasyonu riski yüksek.")
    elif 30 <= rsi <= 45:
        score += 5
        reasons.append(f"RSI toparlanma bölgesinde (RSI: {rsi:.1f}). Destekten dönüş olabilir.")
        
    # RSI Uyumsuzluğu veya Kesim Yönü
    if rsi > prev_1["rsi"] and prev_1["rsi"] < 30:
        score += 8
        reasons.append("RSI aşırı satım bölgesinden yukarı yönlü döndü.")
        
    # MACD Kesişimi
    if macd > macd_sig:
        score += 10
        if prev_1["macd"] <= prev_1["macd_signal"]:
            score += 10
            reasons.append("MACD, Sinyal çizgisini yukarı kesti (Bullish Crossover)!")
    else:
        score -= 10
        if prev_1["macd"] >= prev_1["macd_signal"]:
            score -= 10
            reasons.append("MACD, Sinyal çizgisini aşağı kesti (Bearish Crossover)!")
            
    # --- 3. VOLATİLİTE VE SEVİYE KRİTERLERİ (20 Puan) ---
    # Bollinger Bandı Alt / Üst Band Teması
    if close <= bb_lower * 1.005:
        score += 10
        reasons.append("Fiyat Bollinger Alt Bandına temas ediyor. Destek bölgesinde.")
    elif close >= bb_upper * 0.995:
        score -= 5
        reasons.append("Fiyat Bollinger Üst Bandına yakın veya aşmış durumda.")
        
    # --- 4. HACİM VE ANLIK DEĞİŞİM (15 Puan) ---
    # Son mumun hacmi, son 10 mumun ortalama hacminden yüksek mi?
    recent_volumes = df_ind["volume"].iloc[-11:-1]
    avg_vol = recent_volumes.mean()
    if latest["volume"] > avg_vol * 1.5:
        score += 10
        reasons.append("İşlem hacminde belirgin bir artış var (Hacimli kırılım).")
        
    # 24 Saatlik Fiyat Değişimi
    if ticker_info["change_24h"] > 8.0:
        score += 5
        reasons.append(f"Giriş gücü yüksek (24s Değişim: +{ticker_info['change_24h']:.1f}%).")
    elif ticker_info["change_24h"] < -8.0:
        score += 5
        reasons.append(f"Sert düşüş yaşadı, tepki alımı beklenebilir (24s Değişim: {ticker_info['change_24h']:.1f}%).")

    # --- 5. ATR (Volatilite Riski) ---
    atr = latest.get("atr", 0)
    atr_pct = (atr / close * 100) if close > 0 else 0
    if atr_pct > 5:
        score -= 5
        reasons.append(f"Yüksek volatilite (ATR: %{atr_pct:.1f}). Risk yüksek.")
    elif atr_pct < 2:
        score += 3
        reasons.append(f"Düşük volatilite (ATR: %{atr_pct:.1f}). Kırılım bekleniyor.")

    # --- 6. BTC DOMINANCE ---
    btc_dom = btc_dominance if btc_dominance is not None else fetch_btc_dominance()
    if ticker_info["symbol"] != "BTCUSDT":
        if btc_dom > 55:
            score -= 5
            reasons.append(f"BTC Dominance yüksek (%{btc_dom:.1f}). Altcoinler baskı altında.")
        elif btc_dom < 45:
            score += 5
            reasons.append(f"BTC Dominance düşük (%{btc_dom:.1f}). Altcoin sezonu olabilir.")

    # Skoru Sınırla (0-100)
    score = max(0, min(100, int(score)))
    
    # Sinyali Belirle
    if score >= 80:
        signal = "STRONG BUY"
    elif score >= 65:
        signal = "BUY"
    elif score >= 45:
        signal = "HOLD"
    elif score >= 30:
        signal = "SELL"
    else:
        signal = "STRONG SELL"
        
    # Temel Detayları Sözlük Olarak Kaydet
    details = {
        "rsi": float(rsi),
        "macd": float(macd),
        "macd_signal": float(macd_sig),
        "ema_50": float(ema_50),
        "ema_200": float(ema_200),
        "bb_lower": float(bb_lower),
        "bb_upper": float(bb_upper),
        "atr": float(atr),
        "atr_pct": float(atr_pct),
        "btc_dominance": float(btc_dom),
        "reasons": reasons
    }
    
    return {
        "symbol": ticker_info["symbol"],
        "price": ticker_info["price"],
        "volume": ticker_info["volume"],
        "change_24h": ticker_info["change_24h"],
        "rsi": float(rsi),
        "macd_val": float(macd),
        "macd_sig": float(macd_sig),
        "signal": signal,
        "ai_score": score,
        "details": details
    }
