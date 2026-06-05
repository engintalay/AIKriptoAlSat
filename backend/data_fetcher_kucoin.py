import requests
import pandas as pd
from datetime import datetime
import time
import hmac
import hashlib
import base64
import json

BINANCE_BASE_URL = "https://api.binance.com"
KUCOIN_BASE_URL = "https://api.kucoin.com"

# KuCoin API credentials (opsiyonel - public endpoint'ler için gerekli değil)
KUCOIN_API_KEY = None
KUCOIN_API_SECRET = None
KUCOIN_API_PASSPHRASE = None

def fetch_top_usdt_pairs_kucoin(limit=50):
    """
    KuCoin'dan en yüksek 24 saatlik işlem hacmine sahip USDT çiftlerini çeker.
    """
    # 1. Önce tüm symbol'leri al
    url = f"{KUCOIN_BASE_URL}/api/v1/market/allTickers"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"KuCoin API hatası: {response.status_code}")
            return []
        
        data = response.json()
        if not data.get("data") or not data["data"].get("ticker"):
            return []
        
        tickers = data["data"]["ticker"]
        
        # Filtreleme kriterleri:
        # - Sadece USDT çiftleri
        # - Leveraged tokenları hariç
        usdt_pairs = []
        exclude_keywords = ["UP", "DOWN", "HALF", "DOUBLE", "BEAR", "BULL"]
        
        for item in tickers:
            try:
                symbol = item.get("symbol")
                if not symbol or not isinstance(symbol, str):
                    continue
                # KuCoin formatı: BTC-USDT
                if not symbol.endswith("/USDT"):
                    continue
                
                # Leveraged tokenları hariç
                is_ignored = False
                for kw in exclude_keywords:
                    if kw in symbol:
                        is_ignored = True
                        break
                
                if is_ignored:
                    continue
                
                # KuCoin'den volume bilgisi gelmiyor, priceChangePercent'i kullan
                base_volume = float(item.get("vol") or 0)  # Base coin cinsinden hacim
                price = float(item.get("last") or 0)
                # Approximate USDT volume
                usdt_volume = base_volume * price
                
                usdt_pairs.append({
                    "symbol": symbol.replace("/", ""),
                    "symbol_display": symbol,
                    "price": price,
                    "change_24h": float(item.get("priceChangePercent") or 0),
                    "volume": usdt_volume,
                    "high_24h": float(item.get("high") or 0),
                    "low_24h": float(item.get("low") or 0)
                })
            except (ValueError, KeyError, TypeError):
                continue
        
        # Hacme göre azalan sırala ve ilk LIMIT adet coini al
        usdt_pairs.sort(key=lambda x: x["volume"], reverse=True)
        return usdt_pairs[:limit]
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"KuCoin hacimli coinleri çekerken hata: {e}")
        return []

def fetch_ohlcv_kucoin(symbol, interval="1h", limit=100):
    """
    KuCoin'dan belirli bir coine ait mum (OHLCV) verilerini çeker.
    Symbol formatı: BTCUSDT (Binance formatında)
    """
    # KuCoin formatına çevir: BTCUSDT -> BTC-USDT
    symbol_kucoin = symbol.replace("USDT", "-USDT")
    
    # Interval mapping
    interval_map = {
        "15m": "15min",
        "1h": "1hour",
        "4h": "4hour",
        "1d": "day"
    }
    kucoin_interval = interval_map.get(interval, "1hour")
    
    url = f"{KUCOIN_BASE_URL}/api/v1/market/candles"
    params = {
        "symbol": symbol_kucoin,
        "type": kucoin_interval,
        "size": limit
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            print(f"{symbol} mum verisi çekilemedi (KuCoin Kod: {response.status_code})")
            return None
        
        data = response.json()
        if not data.get("data"):
            return None
        
        candles = data["data"]
        if not candles:
            return None
        
        # DataFrame oluştur
        columns = ["timestamp", "open", "close", "high", "low", "volume", "amount"]
        df = pd.DataFrame(candles, columns=columns)
        
        # Tipleri dönüştür
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        
        # Sadece ihtiyacımız olan sütunları seçelim
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        return df
        
    except Exception as e:
        print(f"{symbol} için KuCoin mum verisi çekilirken hata: {e}")
        return None
