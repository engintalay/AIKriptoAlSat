import requests
import pandas as pd
from datetime import datetime
import time
import hmac
import hashlib
import base64
import json

from backend.config import get_setting

BINANCE_BASE_URL = "https://api.binance.com"
KUCOIN_BASE_URL = "https://api.kucoin.com"

# KuCoin API credentials (opsiyonel - public endpoint'ler için gerekli değil)
KUCOIN_API_KEY = None
KUCOIN_API_SECRET = None
KUCOIN_API_PASSPHRASE = None

def fetch_top_usdt_pairs(limit=50):
    """
    Seçilen exchange'e göre en yüksek 24 saatlik işlem hacmine sahip USDT çiftlerini çeker.
    """
    exchange = get_setting("EXCHANGE", "binance").lower()
    
    if exchange == "kucoin":
        return fetch_top_usdt_pairs_kucoin(limit)
    else:
        return fetch_top_usdt_pairs_binance(limit)

def fetch_top_usdt_pairs_binance(limit=50):
    """
    Binance'den en yüksek 24 saatlik işlem hacmine sahip USDT çiftlerini çeker.
    Leveraged tokenları (UP/DOWN) ve stabil coin çiftlerini filtreler.
    """
    url = f"{BINANCE_BASE_URL}/api/v3/ticker/24hr"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"Binance API hatası: {response.status_code}")
            return []
            
        data = response.json()
        
        # Filtreleme kriterleri:
        # - Sadece USDT çiftleri
        # - UP ve DOWN kaldıraçlı tokenlar hariç
        # - Diğer stabil coin eşleşmeleri hariç (USDC, BUSD, EUR, FDUSD vb.)
        usdt_pairs = []
        exclude_keywords = ["UP", "DOWN", "USDC", "FDUSD", "TUSD", "BUSD", "EUR", "DAI", "AEUR"]
        
        for item in data:
            symbol = item["symbol"]
            if symbol.endswith("USDT"):
                # Kaldıraçlı coinleri ve stabil coinleri eliyoruz
                is_ignored = False
                for kw in exclude_keywords:
                    # Sembol tam olarak o anahtar kelimeyi içeriyor mu veya sonuna mı eklenmiş kontrolü
                    if kw in symbol and symbol != "USDCUSDT":
                        is_ignored = True
                        break
                
                # USDCUSDT gibi doğrudan stabil-stabil eşleşmeleri de eleyelim
                if symbol in ["USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "BUSDUSDT", "DAIUSDT", "EURUSDT"]:
                    is_ignored = True
                    
                if not is_ignored:
                    try:
                        usdt_pairs.append({
                            "symbol": symbol,
                            "price": float(item["lastPrice"]),
                            "change_24h": float(item["priceChangePercent"]),
                            "volume": float(item["quoteVolume"]), # USDT cinsinden hacim
                            "high_24h": float(item["highPrice"]),
                            "low_24h": float(item["lowPrice"])
                        })
                    except (ValueError, KeyError):
                        continue
                        
        # Hacme göre azalan sırala ve ilk LIMIT adet coini al
        usdt_pairs.sort(key=lambda x: x["volume"], reverse=True)
        return usdt_pairs[:limit]
        
    except Exception as e:
        print(f"Hacimli coinleri çekerken hata oluştu: {e}")
        return []

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
            symbol = item["symbol"]
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
            
            try:
                # KuCoin'den volume bilgisi gelmiyor, priceChangePercent'i kullan
                base_volume = float(item.get("vol", 0))  # Base coin cinsinden hacim
                price = float(item.get("last", 0))
                # Approximate USDT volume
                usdt_volume = base_volume * price
                
                usdt_pairs.append({
                    "symbol": symbol.replace("/", ""),
                    "symbol_display": symbol,
                    "price": price,
                    "change_24h": float(item.get("priceChangePercent", 0)),
                    "volume": usdt_volume,
                    "high_24h": float(item.get("high", 0)),
                    "low_24h": float(item.get("low", 0))
                })
            except (ValueError, KeyError):
                continue
        
        # Hacme göre azalan sırala ve ilk LIMIT adet coini al
        usdt_pairs.sort(key=lambda x: x["volume"], reverse=True)
        return usdt_pairs[:limit]
        
    except Exception as e:
        print(f"KuCoin hacimli coinleri çekerken hata: {e}")
        return []

def fetch_ohlcv(symbol, interval="1h", limit=100):
    """
    Seçilen exchange'e göre belirli bir coine ait mum (OHLCV) verilerini çeker.
    """
    exchange = get_setting("EXCHANGE", "binance").lower()
    
    if exchange == "kucoin":
        return fetch_ohlcv_kucoin(symbol, interval, limit)
    else:
        return fetch_ohlcv_binance(symbol, interval, limit)

def fetch_ohlcv_binance(symbol, interval="1h", limit=100):
    """
    Binance'dan belirli bir coine ait mum (OHLCV) verilerini çeker.
    """
    url = f"{BINANCE_BASE_URL}/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            print(f"{symbol} mum verisi çekilemedi (Kod: {response.status_code})")
            return None
            
        data = response.json()
        
        # DataFrame oluştur
        columns = [
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "count", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ]
        df = pd.DataFrame(data, columns=columns)
        
        # Tipleri dönüştür
        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
            
        # Sadece ihtiyacımız olan sütunları seçelim
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        return df
        
    except Exception as e:
        print(f"{symbol} için mum verisi çekilirken hata oluştu: {e}")
        return None

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
