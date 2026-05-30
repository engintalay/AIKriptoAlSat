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
        response = requests.get(url, timeout=5)
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
    print(f"[DEBUG] KuCoin API çağrısı: {url}")
    try:
        response = requests.get(url, timeout=5)
        print(f"[DEBUG] KuCoin API response status: {response.status_code}")
        if response.status_code != 200:
            print(f"KuCoin API hatası: {response.status_code}")
            return []
        
        data = response.json()
        if not data.get("data") or not data["data"].get("ticker"):
            print("[DEBUG] KuCoin API'den ticker verisi alınamadı")
            return []
        
        tickers = data["data"]["ticker"]
        print(f"[DEBUG] KuCoin'den {len(tickers)} adet symbol alındı")
        
        # Filtreleme kriterleri:
        # - Sadece USDT çiftleri
        # - Leveraged tokenları hariç
        usdt_pairs = []
        exclude_keywords = ["UP", "DOWN", "HALF", "DOUBLE", "BEAR", "BULL", "USDC", "TUSD", "FDUSD", "BUSD", "DAI", "UST", "USDP", "PYUSD"]
        
        for item in tickers:
            symbol = item["symbol"]
            # KuCoin formatı: BTC-USDT (not /USDT!)
            if not symbol.endswith("-USDT"):
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
                
                # changeRate veya priceChangePercent'i kullan (string olabilir)
                change_rate_str = item.get("changeRate", "0")
                try:
                    change_pct = float(change_rate_str) * 100
                except ValueError:
                    change_pct = 0.0
                
                usdt_pairs.append({
                    "symbol": symbol.replace("-", ""),
                    "symbol_display": symbol,
                    "price": price,
                    "change_24h": change_pct,
                    "volume": usdt_volume,
                    "high_24h": float(item.get("high", 0)),
                    "low_24h": float(item.get("low", 0))
                })
            except (ValueError, KeyError) as e:
                print(f"KuCoin parse hatası: {e}, item: {item.get('symbol', 'unknown')}")
                continue
        
        print(f"[DEBUG] KuCoin'den {len(usdt_pairs)} USDT çifti filtrelendi")
        # Min 1M USDT hacim filtresi (düşük hacimli/yeni coinleri ele)
        usdt_pairs = [p for p in usdt_pairs if p["volume"] >= 1_000_000]
        # Hacme göre azalan sırala ve ilk LIMIT adet coini al
        usdt_pairs.sort(key=lambda x: x["volume"], reverse=True)
        result = usdt_pairs[:limit]
        print(f"[DEBUG] KuCoin'den {len(result)} coin döndürülüyor")
        return result
        
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
    print(f"[DEBUG] KuCoin OHLCV çekiliyor: {symbol}, interval: {interval}")
    # KuCoin formatına çevir: BTCUSDT -> BTC-USDT
    # Sembolde zaten - varsa değiştirmeyelim
    if "-" in symbol:
        symbol_kucoin = symbol
    else:
        symbol_kucoin = symbol.replace("USDT", "-USDT")
    
    # Interval mapping
    interval_map = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "1h": "1hour",
        "2h": "2hour",
        "4h": "4hour",
        "1d": "1day"
    }
    kucoin_interval = interval_map.get(interval, "1hour")
    
    url = f"{KUCOIN_BASE_URL}/api/v1/market/candles"
    params = {
        "symbol": symbol_kucoin,
        "type": kucoin_interval,
        "size": limit
    }
    print(f"[DEBUG] KuCoin OHLCV URL: {url}, params: {params}")
    
    try:
        response = requests.get(url, params=params, timeout=10)
        print(f"[DEBUG] KuCoin OHLCV response status: {response.status_code}")
        if response.status_code != 200:
            print(f"{symbol} mum verisi çekilemedi (KuCoin Kod: {response.status_code})")
            return None
        
        data = response.json()
        if not data.get("data"):
            print("[DEBUG] KuCoin OHLCV'den veri alınamadı")
            return None
        
        candles = data["data"]
        if not candles:
            print("[DEBUG] KuCoin OHLCV'den mum verisi yok")
            return None
        
        print(f"[DEBUG] KuCoin'den {len(candles)} mum verisi alındı")
        # DataFrame oluştur
        columns = ["timestamp", "open", "close", "high", "low", "volume", "amount"]
        df = pd.DataFrame(candles, columns=columns)
        
        # Tipleri dönüştür (KuCoin timestamp saniye cinsinden)
        df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="s")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        
        # KuCoin verileri ters sırada geliyor, düzelt
        df = df.sort_values("timestamp").reset_index(drop=True)
        
        # Sadece ihtiyacımız olan sütunları seçelim
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        return df
        
    except Exception as e:
        print(f"{symbol} için KuCoin mum verisi çekilirken hata: {e}")
        return None

def fetch_btc_dominance():
    """BTC dominance verisini CoinGecko'dan çeker (5dk cache)."""
    global _btc_dom_cache, _btc_dom_time
    now = time.time()
    if _btc_dom_cache is not None and now - _btc_dom_time < 300:
        return _btc_dom_cache
    try:
        url = "https://api.coingecko.com/api/v3/global"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            _btc_dom_cache = data["data"]["market_cap_percentage"].get("btc", 50.0)
            _btc_dom_time = now
            return _btc_dom_cache
    except Exception:
        pass
    return _btc_dom_cache if _btc_dom_cache else 50.0

_btc_dom_cache = None
_btc_dom_time = 0

_fear_greed_cache = None
_fear_greed_time = 0

def fetch_fear_greed():
    """Kripto Fear & Greed Index'i çeker (10dk cache)."""
    global _fear_greed_cache, _fear_greed_time
    now = time.time()
    if _fear_greed_cache and now - _fear_greed_time < 600:
        return _fear_greed_cache
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            entry = data["data"][0]
            _fear_greed_cache = {"value": int(entry["value"]), "label": entry["value_classification"]}
            _fear_greed_time = now
            return _fear_greed_cache
    except Exception:
        pass
    return _fear_greed_cache or {"value": 50, "label": "Neutral"}
