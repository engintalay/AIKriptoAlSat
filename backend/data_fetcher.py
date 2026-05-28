import requests
import pandas as pd
from datetime import datetime
import time

BINANCE_BASE_URL = "https://api.binance.com"

def fetch_top_usdt_pairs(limit=50):
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

def fetch_ohlcv(symbol, interval="1h", limit=100):
    """
    Belirli bir coine ait mum (OHLCV) verilerini çeker.
    Interval seçenekleri: '15m', '1h', '4h', '1d'
    Dönen değer: pandas.DataFrame
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
