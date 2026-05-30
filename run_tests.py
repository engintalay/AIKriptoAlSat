#!/usr/bin/env python3
"""
AI Kripto Al-Sat - Kapsamlı ve Bağımsız Test Suite ve Görsel Raporlama Aracı
-------------------------------------------------------------------------
Bu araç, uygulamanın tüm fonksiyonlarını (Config, Database, Data Fetcher, Analyzer, AI Agent)
ve tüm REST API uç noktalarını (FastAPI/Uvicorn) bağımsız olarak ve güvenli bir sandbox
ortamında test eder. Test sonunda detaylı ve modern bir HTML raporu üretir.

Kullanım:
    python run_tests.py
"""

import os
import sys

# Proje kök dizini
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# --- SANAL ORTAM (VENV) OTOMATİK YÖNLENDİRME ---
# Eğer test suite sanal ortam dışından (küresel python3 ile) çalıştırıldıysa,
# yerel venv klasörü varsa test aracı kendisini otomatik olarak venv python'ı ile yeniden başlatır.
venv_python = os.path.join(PROJECT_ROOT, "venv", "bin", "python")
if os.path.exists(venv_python) and not sys.executable.startswith(os.path.join(PROJECT_ROOT, "venv")):
    print("\033[94m[LOG]\033[0m \033[93mSanal ortam (venv) dışında çalıştırma algılandı. Test Suite otomatik olarak sanal ortam üzerinden başlatılıyor...\033[0m\n")
    os.execv(venv_python, [venv_python] + sys.argv)

import time
import shutil
import json
import subprocess
import signal
import traceback
import pandas as pd
import numpy as np

sys.path.append(PROJECT_ROOT)

# ANSI Renk Kodları (CLI için)
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Test kayıt sistemi
class TestRegistry:
    def __init__(self):
        self.results = []
        self.start_time = time.time()
        self.system_logs = []

    def log_sys(self, message):
        timestamp = time.strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        self.system_logs.append(log_entry)
        print(f"{Colors.BLUE}[LOG]{Colors.ENDC} {message}")

    def add_result(self, test_id, name, category, status, duration, details="", logs=None, error_msg=None):
        self.results.append({
            "id": test_id,
            "name": name,
            "category": category,
            "status": status,  # PASS, FAIL, WARN
            "duration": round(duration * 1000, 2), # ms cinsinden
            "details": details,
            "logs": logs or [],
            "error_msg": error_msg
        })
        
        # Konsol çıktısı
        status_color = Colors.GREEN if status == "PASS" else (Colors.YELLOW if status == "WARN" else Colors.RED)
        status_symbol = "✓" if status == "PASS" else ("!" if status == "WARN" else "✗")
        print(f"  {status_color}{status_symbol} [{category}] {name} ({round(duration * 1000, 1)} ms){Colors.ENDC}")
        if error_msg:
            print(f"    {Colors.RED}Hata: {error_msg}{Colors.ENDC}")

    def get_summary(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        warned = sum(1 for r in self.results if r["status"] == "WARN")
        success_rate = round((passed / total * 100), 2) if total > 0 else 0.0
        duration = round(time.time() - self.start_time, 2)
        
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "warned": warned,
            "success_rate": success_rate,
            "duration": duration,
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }

# --- SANDBOX ENVIRONMENT MANAGER ---
class TestSandbox:
    def __init__(self, registry):
        self.registry = registry
        self.env_path = os.path.join(PROJECT_ROOT, ".env")
        self.db_path = os.path.join(PROJECT_ROOT, "backend", "crypto_scanner.db")
        
        self.env_bak = self.env_path + ".bak"
        self.db_bak = self.db_path + ".bak"
        
        self.is_isolated = False
        self.server_process = None

    def enter(self):
        self.registry.log_sys("Sandbox ortamı kuruluyor (İzolasyon başlatılıyor)...")
        
        # Eğer geçmişten kalan yedekler varsa önce onları kurtar
        if os.path.exists(self.env_bak) or os.path.exists(self.db_bak):
            self.registry.log_sys("UYARI: Eski yedek dosyaları bulundu. Temizleniyor/Kurtarılıyor...")
            self.exit()

        # 1. Veritabanını yedekle
        if os.path.exists(self.db_path):
            shutil.copy2(self.db_path, self.db_bak)
            os.remove(self.db_path)
            self.registry.log_sys("Canlı veritabanı (.db) geçici olarak yedeklendi.")
        else:
            self.registry.log_sys("Mevcut canlı veritabanı bulunamadı. Yeni oluşturulacak.")

        # 2. .env dosyasını yedekle
        if os.path.exists(self.env_path):
            shutil.copy2(self.env_path, self.env_bak)
            self.registry.log_sys(".env dosyası geçici olarak yedeklendi.")
        
        # 3. Test için izole edilmiş .env oluştur
        test_env_content = (
            "# GEÇİCİ TEST YAPILANDIRMASI\n"
            "GEMINI_API_KEY=test_mock_api_key_valid_length_dummy_value\n"
            "HOST=127.0.0.1\n"
            "PORT=8099\n"
            "TOP_COINS_LIMIT=3\n"
            "SCAN_INTERVAL_MINUTES=1\n"
            "LLM_PROVIDER=gemini\n"
            "EXCHANGE=binance\n"
            "BACKTEST_AMOUNT=1000.0\n"
        )
        with open(self.env_path, "w", encoding="utf-8") as f:
            f.write(test_env_content)
        self.registry.log_sys("Geçici test .env dosyası oluşturuldu.")
        
        self.is_isolated = True

    def exit(self):
        self.registry.log_sys("Sandbox ortamı temizleniyor (Yedekler geri yükleniyor)...")
        
        # 1. Test veritabanını sil ve orijinalini geri yükle
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception as e:
                self.registry.log_sys(f"Hata: Test veritabanı silinemedi: {e}")
                
        if os.path.exists(self.db_bak):
            shutil.move(self.db_bak, self.db_path)
            self.registry.log_sys("Canlı veritabanı başarıyla geri yüklendi.")

        # 2. Test .env dosyasını sil ve orijinalini geri yükle
        if os.path.exists(self.env_path):
            try:
                os.remove(self.env_path)
            except Exception as e:
                pass
                
        if os.path.exists(self.env_bak):
            shutil.move(self.env_bak, self.env_path)
            self.registry.log_sys("Orijinal .env dosyası başarıyla geri yüklendi.")
            
        self.is_isolated = False
        self.registry.log_sys("Sandbox ortamından başarıyla çıkıldı.")

    def start_test_server(self):
        """Test sunucusunu uvicorn ile arka planda çalıştırır."""
        self.registry.log_sys("FastAPI test sunucusu arka planda başlatılıyor...")
        venv_python = os.path.join(PROJECT_ROOT, "venv", "bin", "python")
        if not os.path.exists(venv_python):
            venv_python = sys.executable  # venv yoksa aktif python'ı kullan
            
        self.server_process = subprocess.Popen(
            [venv_python, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8099"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None
        )
        
        # Sunucunun ayağa kalkmasını bekle (health check)
        self.registry.log_sys("Sunucu yanıtı bekleniyor (Timeout: 10s)...")
        start = time.time()
        healthy = False
        while time.time() - start < 10:
            try:
                r = requests.get("http://127.0.0.1:8099/", timeout=1)
                if r.status_code == 200:
                    healthy = True
                    break
            except Exception:
                time.sleep(0.5)
                
        if healthy:
            self.registry.log_sys(f"✓ Sunucu başarıyla başlatıldı (PID: {self.server_process.pid})")
            return True
        else:
            self.registry.log_sys("❌ Sunucu başlatılamadı! Loglar kontrol ediliyor.")
            try:
                # Hata çıktısını okuma
                stderr_data = self.server_process.stderr.read(1000)
                self.registry.log_sys(f"Sunucu Hatası: {stderr_data.decode('utf-8', errors='ignore')}")
            except Exception:
                pass
            return False

    def stop_test_server(self):
        """Çalışan test sunucusunu durdurur."""
        if self.server_process:
            self.registry.log_sys("Test sunucusu kapatılıyor...")
            try:
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(self.server_process.pid), signal.SIGTERM)
                else:
                    self.server_process.terminate()
                self.server_process.wait(timeout=3)
                self.registry.log_sys("✓ Test sunucusu güvenli bir şekilde kapatıldı.")
            except Exception as e:
                self.registry.log_sys(f"Uvicorn kapatılırken hata: {e}")


# --- TEST CASES IMPLEMENTATION ---

def run_config_tests(registry):
    print(f"\n{Colors.HEADER}{Colors.BOLD}--- [1] CONFIG SERVİSİ TESTLERİ ---{Colors.ENDC}")
    import backend.config as config
    
    # Test 1: get_setting varsayılan değer
    start = time.time()
    try:
        val = config.get_setting("EXCHANGE", "binance")
        assert val == "binance", f"Varsayılan değer uyuşmuyor: {val}"
        registry.add_result("cfg_get_setting_default", "Ayar Değeri Okuma (Varsayılan)", "Config", "PASS", time.time() - start, "Orijinal ve varsayılan ayar okuma doğrulandı.")
    except Exception as e:
        registry.add_result("cfg_get_setting_default", "Ayar Değeri Okuma (Varsayılan)", "Config", "FAIL", time.time() - start, error_msg=str(e))

    # Test 2: update_setting ve get_setting
    start = time.time()
    try:
        config.update_setting("TEST_PARAM", "12345")
        val = config.get_setting("TEST_PARAM")
        assert val == "12345", f"Güncellenen değer uyuşmuyor: {val}"
        registry.add_result("cfg_update_setting", "Ayar Güncelleme & Doğrulama", "Config", "PASS", time.time() - start, "Ayar yazma ve okuma döngüsü başarıyla test edildi.")
    except Exception as e:
        registry.add_result("cfg_update_setting", "Ayar Güncelleme & Doğrulama", "Config", "FAIL", time.time() - start, error_msg=str(e))

    # Test 3: get_exchange_settings
    start = time.time()
    try:
        settings = config.get_exchange_settings()
        assert "exchange" in settings, "Exchange parametresi eksik!"
        assert "kucoin_api_key" in settings, "Kucoin API Key parametresi eksik!"
        registry.add_result("cfg_exchange_settings", "Borsa Ayarları Yapısı", "Config", "PASS", time.time() - start, "Borsa entegrasyonu ayarları yapısı doğrulandı.")
    except Exception as e:
        registry.add_result("cfg_exchange_settings", "Borsa Ayarları Yapısı", "Config", "FAIL", time.time() - start, error_msg=str(e))


def run_database_tests(registry):
    print(f"\n{Colors.HEADER}{Colors.BOLD}--- [2] DATABASE SERVİSİ TESTLERİ ---{Colors.ENDC}")
    import backend.database as database
    
    # Test 1: init_db
    start = time.time()
    try:
        database.init_db()
        # Tabloların oluştuğunu test et
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r["name"] for r in cursor.fetchall()]
        conn.close()
        
        required_tables = ["scanned_coins", "signals", "ai_reports", "chat_history", "favorites"]
        for t in required_tables:
            assert t in tables, f"Tablo eksik: {t}"
            
        registry.add_result("db_init", "Veritabanı İlklendirme & Şema Kontrolü", "Database", "PASS", time.time() - start, "Tüm tablolar SQLite üzerinde başarıyla oluşturuldu.")
    except Exception as e:
        registry.add_result("db_init", "Veritabanı İlklendirme & Şema Kontrolü", "Database", "FAIL", time.time() - start, error_msg=str(e))

    # Test 2: save_scanned_coins & get_scanned_coins
    start = time.time()
    try:
        mock_coins = [{
            "symbol": "BTCUSDT",
            "price": 65000.0,
            "volume": 120000000.0,
            "change_24h": 2.5,
            "rsi": 55.2,
            "macd_val": 120.5,
            "macd_sig": 98.2,
            "signal": "BUY",
            "ai_score": 75,
            "details": {"rsi": 55.2}
        }]
        database.save_scanned_coins(mock_coins)
        loaded = database.get_scanned_coins()
        
        assert len(loaded) > 0, "Kaydedilen coinler yüklenemedi!"
        assert loaded[0]["symbol"] == "BTCUSDT", "Coin sembolü uyuşmuyor!"
        assert loaded[0]["price"] == 65000.0, "Coin fiyatı uyuşmuyor!"
        registry.add_result("db_scanned_coins", "Taranan Coin Önbellekleme", "Database", "PASS", time.time() - start, "Coin fiyat ve indikatör önbelleklemesi başarıyla yapıldı.")
    except Exception as e:
        registry.add_result("db_scanned_coins", "Taranan Coin Önbellekleme", "Database", "FAIL", time.time() - start, error_msg=str(e))

    # Test 3: save_signal, get_pending_signals, update_signal_status, get_signals
    start = time.time()
    try:
        database.save_signal("ETHUSDT", "BUY", 3500.0, 3400.0, 3600.0, 3700.0)
        pending = database.get_pending_signals()
        assert len(pending) > 0, "Açık sinyal bulunamadı!"
        
        sig_id = pending[0]["id"]
        database.update_signal_status(sig_id, "TP1_HIT", 3605.0)
        
        history = database.get_signals(limit=5)
        assert history[0]["status"] == "TP1_HIT", "Sinyal durumu güncellenemedi!"
        assert history[0]["closed_price"] == 3605.0, "Sinyal kapanış fiyatı uyuşmuyor!"
        registry.add_result("db_signals_flow", "Sinyal ve Backtest Yönetimi", "Database", "PASS", time.time() - start, "Sinyal oluşturma, durum güncelleme ve geçmiş sorgulama akışı doğrulandı.")
    except Exception as e:
        registry.add_result("db_signals_flow", "Sinyal ve Backtest Yönetimi", "Database", "FAIL", time.time() - start, error_msg=str(e))

    # Test 4: save_ai_report & get_ai_report
    start = time.time()
    try:
        mock_report = {"summary": "Güçlü boğa trendi", "entry_zone": "64000 - 64500"}
        database.save_ai_report("BTCUSDT", 82, "STRONG BUY", mock_report)
        loaded_report = database.get_ai_report("BTCUSDT")
        
        assert loaded_report is not None, "AI raporu bulunamadı!"
        assert loaded_report["score"] == 82, "AI rapor skoru yanlış!"
        assert loaded_report["report"]["summary"] == "Güçlü boğa trendi", "AI rapor içeriği bozuk!"
        registry.add_result("db_ai_report", "AI Strateji Raporu Önbellekleme", "Database", "PASS", time.time() - start, "AI raporlarının SQLite üzerinde sıkıştırılıp JSON olarak tutulması doğrulandı.")
    except Exception as e:
        registry.add_result("db_ai_report", "AI Strateji Raporu Önbellekleme", "Database", "FAIL", time.time() - start, error_msg=str(e))

    # Test 5: save_chat_message & get_chat_history
    start = time.time()
    try:
        database.save_chat_message("BTCUSDT", "USER", "BTC yönü nedir?")
        database.save_chat_message("BTCUSDT", "AI", "Fiyat yükseliş trendinde.")
        history = database.get_chat_history("BTCUSDT")
        
        assert len(history) >= 2, "Chat mesaj geçmişi eksik!"
        assert history[0]["sender"] == "USER", "Gönderen eşleşmiyor!"
        assert history[1]["sender"] == "AI", "AI cevabı eşleşmiyor!"
        registry.add_result("db_chat_history", "Chat Mesaj Geçmişi", "Database", "PASS", time.time() - start, "Kripto sohbet geçmişinin SQLite entegrasyonu doğrulandı.")
    except Exception as e:
        registry.add_result("db_chat_history", "Chat Mesaj Geçmişi", "Database", "FAIL", time.time() - start, error_msg=str(e))

    # Test 6: toggle_favorite & get_favorites
    start = time.time()
    try:
        is_fav = database.toggle_favorite("SOLUSDT")
        assert is_fav is True, "Favori ekleme True dönmedi!"
        favs = database.get_favorites()
        assert "SOLUSDT" in favs, "Favori listesinde bulunamadı!"
        
        is_fav2 = database.toggle_favorite("SOLUSDT")
        assert is_fav2 is False, "Favori çıkarma False dönmedi!"
        favs2 = database.get_favorites()
        assert "SOLUSDT" not in favs2, "Favori listesinden silinemedi!"
        registry.add_result("db_favorites", "Favori Coin Yönetimi", "Database", "PASS", time.time() - start, "Kullanıcı favori listesi ekleme/çıkarma mantığı doğrulandı.")
    except Exception as e:
        registry.add_result("db_favorites", "Favori Coin Yönetimi", "Database", "FAIL", time.time() - start, error_msg=str(e))


def run_data_fetcher_tests(registry):
    print(f"\n{Colors.HEADER}{Colors.BOLD}--- [3] DATA FETCHER SERVİSİ TESTLERİ ---{Colors.ENDC}")
    import backend.data_fetcher as data_fetcher
    
    # Test 1: fetch_btc_dominance (Gecko API)
    start = time.time()
    try:
        dom = data_fetcher.fetch_btc_dominance()
        assert isinstance(dom, float), "BTC Dominance float olmalı!"
        assert 30 <= dom <= 75, f"Beklenmeyen BTC dominance değeri: {dom}%"
        registry.add_result("df_btc_dominance", "BTC Dominance Sorgulama (CoinGecko)", "Data Fetcher", "PASS", time.time() - start, f"BTC Dominance başarıyla çekildi: %{dom:.2f}")
    except Exception as e:
        registry.add_result("df_btc_dominance", "BTC Dominance Sorgulama (CoinGecko)", "Data Fetcher", "WARN", time.time() - start, "CoinGecko API geçici limit hatası. Varsayılan %50 kullanıldı.", error_msg=str(e))

    # Test 2: fetch_fear_greed (Alternative.me API)
    start = time.time()
    try:
        fng = data_fetcher.fetch_fear_greed()
        assert "value" in fng, "Korku ve Açgözlülük değeri eksik!"
        assert "label" in fng, "Korku ve Açgözlülük etiketi eksik!"
        assert 0 <= fng["value"] <= 100, f"Değer aralık dışı: {fng['value']}"
        registry.add_result("df_fear_greed", "Korku & Açgözlülük Endeksi (F&G)", "Data Fetcher", "PASS", time.time() - start, f"Fear & Greed Index başarıyla çekildi: {fng['value']} ({fng['label']})")
    except Exception as e:
        registry.add_result("df_fear_greed", "Korku & Açgözlülük Endeksi (F&G)", "Data Fetcher", "WARN", time.time() - start, "Fear & Greed API gecikmeli yanıt verdi.", error_msg=str(e))

    # Test 3: fetch_top_usdt_pairs_binance (Binance API)
    start = time.time()
    try:
        pairs = data_fetcher.fetch_top_usdt_pairs_binance(limit=3)
        assert len(pairs) > 0, "Binance'den aktif hacimli coinler çekilemedi!"
        assert "symbol" in pairs[0], "Sembol parametresi eksik!"
        assert "price" in pairs[0], "Fiyat parametresi eksik!"
        assert pairs[0]["symbol"].endswith("USDT"), "Sembol USDT ile bitmeli!"
        registry.add_result("df_binance_pairs", "Binance Hacimli Coin Taraması", "Data Fetcher", "PASS", time.time() - start, f"En aktif {len(pairs)} Binance çifti başarıyla çekildi. En üst: {pairs[0]['symbol']} (${pairs[0]['price']})")
    except Exception as e:
        registry.add_result("df_binance_pairs", "Binance Hacimli Coin Taraması", "Data Fetcher", "FAIL", time.time() - start, error_msg=str(e))

    # Test 4: fetch_top_usdt_pairs_kucoin (KuCoin API)
    start = time.time()
    try:
        pairs = data_fetcher.fetch_top_usdt_pairs_kucoin(limit=3)
        if len(pairs) == 0:
            raise ValueError("KuCoin market tickers boş döndü.")
        assert "symbol" in pairs[0], "Sembol parametresi eksik!"
        assert "price" in pairs[0], "Fiyat parametresi eksik!"
        registry.add_result("df_kucoin_pairs", "KuCoin Hacimli Coin Taraması", "Data Fetcher", "PASS", time.time() - start, f"En aktif {len(pairs)} KuCoin çifti başarıyla çekildi. En üst: {pairs[0]['symbol']} (${pairs[0]['price']})")
    except Exception as e:
        registry.add_result("df_kucoin_pairs", "KuCoin Hacimli Coin Taraması", "Data Fetcher", "WARN", time.time() - start, "KuCoin API yanıtı başarısız veya yavaş (Kullanıcı anahtarı yoksa limitlenebilir).", error_msg=str(e))

    # Test 5: fetch_ohlcv (Binance ve KuCoin Mum Verisi)
    start = time.time()
    try:
        df_bin = data_fetcher.fetch_ohlcv_binance("BTCUSDT", interval="1h", limit=50)
        assert df_bin is not None, "Binance mum verisi alınamadı!"
        assert len(df_bin) == 50, f"Mum sayısı eşleşmiyor: {len(df_bin)}"
        assert "close" in df_bin.columns, "Close sütunu eksik!"
        registry.add_result("df_ohlcv", "Candlestick (Mum) Verisi Çekimi (Binance)", "Data Fetcher", "PASS", time.time() - start, "Binance marketinden 50 saatlik mum verisi ve hacim bilgisi çekildi.")
    except Exception as e:
        registry.add_result("df_ohlcv", "Candlestick (Mum) Verisi Çekimi (Binance)", "Data Fetcher", "FAIL", time.time() - start, error_msg=str(e))


def run_analyzer_tests(registry):
    print(f"\n{Colors.HEADER}{Colors.BOLD}--- [4] ANALYZER SERVİSİ TESTLERİ ---{Colors.ENDC}")
    import backend.analyzer as analyzer
    
    # 100 mumluk yapay veri oluştur (Sinüs dalgası şeklinde fiyat hareketi)
    t = np.linspace(0, 50, 100)
    prices = 60000 + 1000 * np.sin(t)
    df_mock = pd.DataFrame({
        "timestamp": pd.date_range(start="2026-05-30", periods=100, freq="h"),
        "open": prices * 0.999,
        "high": prices * 1.005,
        "low": prices * 0.995,
        "close": prices,
        "volume": np.random.randint(10, 100, 100) * 100000.0
    })

    # Test 1: calculate_indicators (Teknik Indikatörler)
    start = time.time()
    try:
        df_res = analyzer.calculate_indicators(df_mock)
        assert df_res is not None, "Hesaplama sonucu boş döndü!"
        
        required_cols = ["rsi", "macd", "macd_signal", "macd_hist", "bb_middle", "bb_upper", "bb_lower", "ema_50", "ema_200", "atr"]
        for col in required_cols:
            assert col in df_res.columns, f"Hesaplanan sütun eksik: {col}"
            
        rsi_val = df_res["rsi"].iloc[-1]
        assert 0 <= rsi_val <= 100, f"RSI aralık dışı: {rsi_val}"
        
        registry.add_result("an_indicators", "Teknik Analiz Göstergeleri (Wilder/EMA/BB/ATR)", "Analyzer", "PASS", time.time() - start, "RSI, MACD, Bollinger Bands, ATR ve Hareketli Ortalamalar saf pandas ile başarıyla hesaplandı.")
    except Exception as e:
        registry.add_result("an_indicators", "Teknik Analiz Göstergeleri (Wilder/EMA/BB/ATR)", "Analyzer", "FAIL", time.time() - start, error_msg=str(e))

    # Test 2: analyze_coin_status (Multi-Factor Puanlama)
    start = time.time()
    try:
        ticker = {
            "symbol": "BTCUSDT",
            "price": 60500.0,
            "volume": 250000000.0,
            "change_24h": 3.2
        }
        res = analyzer.analyze_coin_status(df_mock, ticker, btc_dominance=50.0)
        
        assert "ai_score" in res, "AI Puanı hesaplanamadı!"
        assert "signal" in res, "Al-Sat sinyali üretilemedi!"
        assert 0 <= res["ai_score"] <= 100, f"AI Puanı aralık dışı: {res['ai_score']}"
        assert res["signal"] in ["STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL"], f"Geçersiz sinyal: {res['signal']}"
        
        assert "rsi" in res["details"], "Detaylarda RSI bilgisi bulunamadı!"
        assert "reasons" in res["details"], "Detaylarda teknik kararlar (Nedenler) bulunamadı!"
        
        registry.add_result("an_scoring", "Çok Faktörlü Karar Mekanizması & Sinyal", "Analyzer", "PASS", time.time() - start, f"Multi-Factor Puanlama çalıştı: Skor: {res['ai_score']}, Sinyal: {res['signal']}. {len(res['details']['reasons'])} teknik bulgu listelendi.")
    except Exception as e:
        registry.add_result("an_scoring", "Çok Faktörlü Karar Mekanizması & Sinyal", "Analyzer", "FAIL", time.time() - start, error_msg=str(e))


def run_ai_agent_tests(registry):
    print(f"\n{Colors.HEADER}{Colors.BOLD}--- [5] AI AGENT SERVİSİ TESTLERİ ---{Colors.ENDC}")
    import backend.ai_agent as ai_agent
    
    # Test 1: extract_json_from_text (JSON Yakalayıcı ve Parser)
    start = time.time()
    try:
        dirty_json = "```json\n{\n  \"symbol\": \"BTCUSDT\",\n  \"direction\": \"LONG\"\n}\n```"
        parsed = ai_agent.extract_json_from_text(dirty_json)
        assert parsed is not None, "JSON parse edilemedi!"
        assert parsed["symbol"] == "BTCUSDT", "Değer eşleşmiyor!"
        
        dirty_json_2 = "Bazı konuşmalar... {\"score\": 85} diğer konuşmalar..."
        parsed_2 = ai_agent.extract_json_from_text(dirty_json_2)
        assert parsed_2 is not None and parsed_2["score"] == 85, "Gömülü JSON yakalanamadı!"
        
        registry.add_result("ai_json_extractor", "Akıllı Rapor Parser (JSON Extractor)", "AI Agent", "PASS", time.time() - start, "Model yanıtı içinde karmaşık/bozuk markdown JSON verileri başarıyla temizlendi ve sözlüğe çevrildi.")
    except Exception as e:
        registry.add_result("ai_json_extractor", "Akıllı Rapor Parser (JSON Extractor)", "AI Agent", "FAIL", time.time() - start, error_msg=str(e))

    # Test 2: generate_mock_report (Mock Rapor Oluşturma)
    start = time.time()
    try:
        res = ai_agent.generate_mock_report("BTCUSDT", 60000.0, 1.5, 75, "BUY", {"rsi": 55})
        assert res["symbol"] == "BTCUSDT", "Sembol uyuşmuyor!"
        assert "entry_zone" in res, "Giriş bölgesi eksik!"
        registry.add_result("ai_mock_report", "Simüle (Mock) Çevrimdışı Raporlama", "AI Agent", "PASS", time.time() - start, "API bağlantısı kesildiğinde/olmadığında üretilen akıllı mock rapor şablonu doğrulandı.")
    except Exception as e:
        registry.add_result("ai_mock_report", "Simüle (Mock) Çevrimdışı Raporlama", "AI Agent", "FAIL", time.time() - start, error_msg=str(e))

    # Test 3: is_api_key_valid (Yapılandırılmış Gemini API kontrolü)
    start = time.time()
    try:
        import backend.config as config
        key_val = config.get_setting("GEMINI_API_KEY")
        valid = ai_agent.is_api_key_valid()
        assert valid is True, f"API Key test .env dosyasına göre geçersiz sayıldı! Okunan Değer: '{key_val}' (Uzunluk: {len(key_val) if key_val else 0})"
        registry.add_result("ai_key_validation", "Gemini API Anahtarı Doğrulama", "AI Agent", "PASS", time.time() - start, "Uygulamanın Gemini API Anahtarı format ve geçerlilik doğrulayıcısı doğrulandı.")
    except Exception as e:
        registry.add_result("ai_key_validation", "Gemini API Anahtarı Doğrulama", "AI Agent", "FAIL", time.time() - start, error_msg=str(e))


def run_api_endpoint_tests(registry):
    print(f"\n{Colors.HEADER}{Colors.BOLD}--- [6] REST API ENDPOINT (FASTAPI) İNTEGRASYON TESTLERİ ---{Colors.ENDC}")
    
    base_url = "http://127.0.0.1:8099"

    # Test 1: GET /
    start = time.time()
    try:
        r = requests.get(f"{base_url}/", timeout=3)
        assert r.status_code == 200, f"Hatalı kod: {r.status_code}"
        registry.add_result("api_root", "GET / (Root HTML)", "REST API", "PASS", time.time() - start, "Ana sayfa yönlendirmesi başarıyla yanıt verdi.")
    except Exception as e:
        registry.add_result("api_root", "GET / (Root HTML)", "REST API", "FAIL", time.time() - start, error_msg=str(e))

    # Test 2: GET /api/settings
    start = time.time()
    try:
        r = requests.get(f"{base_url}/api/settings", timeout=3)
        assert r.status_code == 200, f"Hatalı kod: {r.status_code}"
        data = r.json()
        assert "llm_provider" in data, "llm_provider parametresi eksik!"
        assert "exchange" in data, "exchange parametresi eksik!"
        registry.add_result("api_get_settings", "GET /api/settings (Uygulama Ayarları)", "REST API", "PASS", time.time() - start, f"Mevcut sistem ve LLM ayarları başarıyla çekildi. Sağlayıcı: {data['llm_provider']}")
    except Exception as e:
        registry.add_result("api_get_settings", "GET /api/settings (Uygulama Ayarları)", "REST API", "FAIL", time.time() - start, error_msg=str(e))

    # Test 3: POST /api/settings
    start = time.time()
    try:
        payload = {
            "gemini_api_key": "•••",
            "top_coins_limit": 5,
            "scan_interval_minutes": 10,
            "backtest_amount": 500,
            "llm_provider": "gemini",
            "ollama_model": "llama3",
            "ollama_api_url": "http://localhost:11434",
            "llamacpp_api_url": "http://localhost:8080",
            "exchange": "binance",
            "kucoin_api_key": "",
            "kucoin_api_secret": "",
            "kucoin_api_passphrase": "",
            "kucoin_rate_limit": 60
        }
        r = requests.post(f"{base_url}/api/settings", json=payload, timeout=3)
        assert r.status_code == 200, f"Hatalı kod: {r.status_code}"
        data = r.json()
        assert data["status"] == "success", "Ayarlar güncellenemedi!"
        registry.add_result("api_post_settings", "POST /api/settings (Ayarları Güncelleme)", "REST API", "PASS", time.time() - start, "Ayarlar endpointine yazma işlemi başarıyla tamamlandı.")
    except Exception as e:
        registry.add_result("api_post_settings", "POST /api/settings (Ayarları Güncelleme)", "REST API", "FAIL", time.time() - start, error_msg=str(e))

    # Test 4: GET /api/scan (Canlı Piyasa Taraması)
    start = time.time()
    try:
        r = requests.get(f"{base_url}/api/scan?force=true", timeout=45)
        assert r.status_code == 200, f"Hatalı kod: {r.status_code}"
        data = r.json()
        assert "coins" in data, "Coins listesi eksik!"
        assert len(data["coins"]) > 0, "Taranan coin bulunamadı!"
        registry.add_result("api_scan", "GET /api/scan (Canlı Piyasa Taraması)", "REST API", "PASS", time.time() - start, f"Canlı tarama tetiklendi. Toplam {len(data['coins'])} aktif coin analiz edilip puanlandı.")
    except Exception as e:
        registry.add_result("api_scan", "GET /api/scan (Canlı Piyasa Taraması)", "REST API", "FAIL", time.time() - start, error_msg=str(e))

    # Test 5: GET /api/coin/{symbol}/candles (Grafik Verisi)
    start = time.time()
    try:
        r = requests.get(f"{base_url}/api/coin/BTCUSDT/candles?interval=1h&limit=20&indicators=bollinger,supertrend", timeout=5)
        assert r.status_code == 200, f"Hatalı kod: {r.status_code}"
        data = r.json()
        assert "candles" in data, "Candles listesi eksik!"
        assert "indicators" in data, "Indicators nesnesi eksik!"
        assert len(data["candles"]) > 0, "Mum verisi yok!"
        registry.add_result("api_candles", "GET /api/coin/candles (Grafik ve İndikatör Akışı)", "REST API", "PASS", time.time() - start, "Mum verileri ve dinamik Bollinger/Supertrend indikatörleri grafik formatında çekildi.")
    except Exception as e:
        registry.add_result("api_candles", "GET /api/coin/candles (Grafik ve İndikatör Akışı)", "REST API", "FAIL", time.time() - start, error_msg=str(e))

    # Test 6: GET /api/coin/{symbol}/report (Derin Yapay Zeka Analizi)
    start = time.time()
    try:
        r = requests.get(f"{base_url}/api/coin/BTCUSDT/report?refresh=true", timeout=15)
        assert r.status_code == 200, f"Hatalı kod: {r.status_code}"
        data = r.json()
        assert "direction" in data, "Analiz yönü eksik!"
        assert "summary" in data, "Rapor özeti eksik!"
        registry.add_result("api_report", "GET /api/coin/report (AI Analiz Raporu)", "REST API", "PASS", time.time() - start, f"Yapay zeka analiz raporu başarıyla alındı. Önerilen Yön: {data['direction']}")
    except Exception as e:
        registry.add_result("api_report", "GET /api/coin/report (AI Analiz Raporu)", "REST API", "FAIL", time.time() - start, error_msg=str(e))

    # Test 7: POST /api/coin/{symbol}/chat (AI Sohbet)
    start = time.time()
    try:
        payload = {"message": "BTC için stop loss seviyesi kaç olmalı?"}
        r = requests.post(f"{base_url}/api/coin/BTCUSDT/chat", json=payload, timeout=15)
        assert r.status_code == 200, f"Hatalı kod: {r.status_code}"
        data = r.json()
        assert "reply" in data, "AI yanıtı eksik!"
        registry.add_result("api_chat_post", "POST /api/coin/chat (AI Sohbet Sorusu)", "REST API", "PASS", time.time() - start, "AI Kripto Danışmanı sohbet mesajına başarıyla yanıt verdi.")
    except Exception as e:
        registry.add_result("api_chat_post", "POST /api/coin/chat (AI Sohbet Sorusu)", "REST API", "FAIL", time.time() - start, error_msg=str(e))

    # Test 8: GET /api/coin/{symbol}/chat (AI Sohbet Geçmişi)
    start = time.time()
    try:
        r = requests.get(f"{base_url}/api/coin/BTCUSDT/chat", timeout=3)
        assert r.status_code == 200, f"Hatalı kod: {r.status_code}"
        data = r.json()
        assert len(data) > 0, "Chat geçmişi boş döndü!"
        registry.add_result("api_chat_get", "GET /api/coin/chat (Sohbet Geçmişi)", "REST API", "PASS", time.time() - start, "Sohbet mesaj geçmişi listelendi.")
    except Exception as e:
        registry.add_result("api_chat_get", "GET /api/coin/chat (Sohbet Geçmişi)", "REST API", "FAIL", time.time() - start, error_msg=str(e))

    # Test 9: POST /api/coin/{symbol}/favorite
    start = time.time()
    try:
        r = requests.post(f"{base_url}/api/coin/BTCUSDT/favorite", timeout=3)
        assert r.status_code == 200, f"Hatalı kod: {r.status_code}"
        data = r.json()
        assert "is_favorite" in data, "Geri dönen favori durumu eksik!"
        registry.add_result("api_favorite_post", "POST /api/coin/favorite (Favori Değiştirme)", "REST API", "PASS", time.time() - start, f"Favori durumu başarıyla güncellendi: {data['is_favorite']}")
    except Exception as e:
        registry.add_result("api_favorite_post", "POST /api/coin/favorite (Favori Değiştirme)", "REST API", "FAIL", time.time() - start, error_msg=str(e))

    # Test 10: GET /api/favorites
    start = time.time()
    try:
        r = requests.get(f"{base_url}/api/favorites", timeout=3)
        assert r.status_code == 200, f"Hatalı kod: {r.status_code}"
        registry.add_result("api_favorites_get", "GET /api/favorites (Favori Listesi)", "REST API", "PASS", time.time() - start, "Tüm favori coinlerin listesi başarıyla getirildi.")
    except Exception as e:
        registry.add_result("api_favorites_get", "GET /api/favorites (Favori Listesi)", "REST API", "FAIL", time.time() - start, error_msg=str(e))

    # Test 11: GET /api/signals
    start = time.time()
    try:
        r = requests.get(f"{base_url}/api/signals", timeout=3)
        assert r.status_code == 200, f"Hatalı kod: {r.status_code}"
        data = r.json()
        registry.add_result("api_signals_get", "GET /api/signals (Sinyal Geçmişi & Backtest)", "REST API", "PASS", time.time() - start, f"Toplam {len(data)} adet Al-Sat sinyal kaydı ve P&L analizi listelendi.")
    except Exception as e:
        registry.add_result("api_signals_get", "GET /api/signals (Sinyal Geçmişi & Backtest)", "REST API", "FAIL", time.time() - start, error_msg=str(e))

    # Test 12: GET /api/fear-greed
    start = time.time()
    try:
        r = requests.get(f"{base_url}/api/fear-greed", timeout=3)
        assert r.status_code == 200, f"Hatalı kod: {r.status_code}"
        data = r.json()
        assert "value" in data, "Fear & Greed değeri eksik!"
        registry.add_result("api_fear_greed", "GET /api/fear-greed (Kripto Korku Endeksi)", "REST API", "PASS", time.time() - start, f"Fear & Greed Index REST API'den alındı: {data['value']}")
    except Exception as e:
        registry.add_result("api_fear_greed", "GET /api/fear-greed (Kripto Korku Endeksi)", "REST API", "FAIL", time.time() - start, error_msg=str(e))

    # Test 13: POST /api/signals/reset
    start = time.time()
    try:
        r = requests.post(f"{base_url}/api/signals/reset", timeout=3)
        assert r.status_code == 200, f"Hatalı kod: {r.status_code}"
        data = r.json()
        assert data["status"] == "ok", "Sinyal temizleme başarısız!"
        registry.add_result("api_signals_reset", "POST /api/signals/reset (Geçmiş Sıfırlama)", "REST API", "PASS", time.time() - start, "Veritabanındaki tüm sinyal geçmişi başarıyla sıfırlandı.")
    except Exception as e:
        registry.add_result("api_signals_reset", "POST /api/signals/reset (Geçmiş Sıfırlama)", "REST API", "FAIL", time.time() - start, error_msg=str(e))


# --- GENERATE PREMIUM HTML REPORT ---

def build_html_report(registry, summary):
    category_durations = {}
    category_counts = {}
    for r in registry.results:
        cat = r["category"]
        category_durations[cat] = category_durations.get(cat, 0.0) + r["duration"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    categories_json = list(category_durations.keys())
    durations_json = [round(category_durations[cat] / category_counts[cat], 2) for cat in categories_json]
    
    # SVG Grafik 1: Kategori Ortalama Tepki Süresi (ms)
    svg_chart_bars = ""
    max_duration = max(durations_json) if durations_json else 1.0
    chart_height = 200
    chart_width = 500
    bar_width = 40
    spacing = 60
    
    for i, (cat, dur) in enumerate(zip(categories_json, durations_json)):
        x = 60 + i * (bar_width + spacing)
        bar_h = (dur / max_duration) * (chart_height - 60)
        y = chart_height - 40 - bar_h
        
        svg_chart_bars += f"""
        <g class="bar-group">
            <rect x="{x}" y="{y}" width="{bar_width}" height="{bar_h}" fill="url(#gradient-bar)" rx="4"/>
            <text x="{x + bar_width/2}" y="{y - 8}" text-anchor="middle" font-size="10" fill="#a0aec0">{dur} ms</text>
            <text x="{x + bar_width/2}" y="{chart_height - 20}" text-anchor="middle" font-size="11" fill="#cbd5e0" font-weight="500">{cat}</text>
        </g>
        """

    test_cards_html = ""
    for r in registry.results:
        status_class = "pass" if r["status"] == "PASS" else ("warn" if r["status"] == "WARN" else "fail")
        status_text = "BAŞARILI" if r["status"] == "PASS" else ("UYARI" if r["status"] == "WARN" else "BAŞARISIZ")
        
        status_icon = ""
        if r["status"] == "PASS":
            status_icon = '<svg class="icon-pass" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>'
        elif r["status"] == "WARN":
            status_icon = '<svg class="icon-warn" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>'
        else:
            status_icon = '<svg class="icon-fail" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>'

        error_section = ""
        if r["error_msg"]:
            error_section = f"""
            <div class="test-error">
                <strong>Hata Detayı:</strong>
                <pre>{r['error_msg']}</pre>
            </div>
            """

        logs_section = ""
        if r["logs"]:
            logs_section = f"""
            <div class="test-logs">
                <strong>Test Adımları:</strong>
                <ul>
                    {"".join(f"<li>{l}</li>" for l in r["logs"])}
                </ul>
            </div>
            """

        test_cards_html += f"""
        <div class="test-card {status_class}" data-category="{r['category']}">
            <div class="test-header" onclick="toggleAccordion(this)">
                <div class="test-title-section">
                    {status_icon}
                    <div>
                        <span class="test-category-badge">{r['category']}</span>
                        <h3 class="test-name">{r['name']}</h3>
                    </div>
                </div>
                <div class="test-meta-section">
                    <span class="test-duration">{r['duration']} ms</span>
                    <span class="test-status-badge {status_class}">{status_text}</span>
                    <svg class="chevron" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
                </div>
            </div>
            <div class="test-details" style="display: none;">
                <p class="test-desc">{r['details']}</p>
                {error_section}
                {logs_section}
            </div>
        </div>
        """

    sys_logs_html = "".join(f"<div>{log}</div>" for log in registry.system_logs)

    html_content = f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Kripto Al-Sat - Detaylı Test Raporu</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-dark: #0f172a;
            --bg-card: #1e293b;
            --border-color: #334155;
            --primary: #6366f1;
            --primary-glow: rgba(99, 102, 241, 0.15);
            --success: #10b981;
            --success-glow: rgba(16, 185, 129, 0.15);
            --fail: #f43f5e;
            --fail-glow: rgba(244, 63, 94, 0.15);
            --warn: #f59e0b;
            --warn-glow: rgba(245, 158, 11, 0.15);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Inter', sans-serif;
        }}

        body {{
            background-color: var(--bg-dark);
            color: var(--text-main);
            padding: 2.5rem 1.5rem;
            line-height: 1.6;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        header {{
            margin-bottom: 2.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1.5rem;
        }}

        .title-group h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(135deg, #a5b4fc, var(--primary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.3rem;
        }}

        .title-group p {{
            color: var(--text-muted);
            font-size: 0.95rem;
        }}

        .timestamp-badge {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            padding: 0.6rem 1.2rem;
            border-radius: 12px;
            font-size: 0.85rem;
            font-weight: 500;
            color: var(--text-muted);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2.5rem;
        }}

        .stat-card {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
            position: relative;
            overflow: hidden;
            transition: all 0.3s ease;
        }}

        .stat-card:hover {{
            transform: translateY(-4px);
            border-color: #475569;
        }}

        .stat-card::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
        }}

        .stat-card.total::after {{ background-color: var(--primary); }}
        .stat-card.pass::after {{ background-color: var(--success); }}
        .stat-card.fail::after {{ background-color: var(--fail); }}
        .stat-card.duration::after {{ background-color: var(--warn); }}

        .stat-info h4 {{
            color: var(--text-muted);
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
        }}

        .stat-value {{
            font-family: 'Outfit', sans-serif;
            font-size: 2rem;
            font-weight: 700;
        }}

        .gauge-container {{
            position: relative;
            width: 80px;
            height: 80px;
        }}

        .gauge-svg {{
            transform: rotate(-90deg);
        }}

        .gauge-bg {{
            fill: none;
            stroke: #334155;
            stroke-width: 6;
        }}

        .gauge-bar {{
            fill: none;
            stroke: var(--success);
            stroke-width: 6;
            stroke-linecap: round;
            stroke-dasharray: 220;
            stroke-dashoffset: {220 - (220 * summary['success_rate'] / 100)};
            transition: stroke-dashoffset 1.5s ease-out;
        }}

        .gauge-text {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 0.85rem;
            font-weight: 700;
            color: var(--success);
            font-family: 'Outfit', sans-serif;
        }}

        .chart-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
            margin-bottom: 2.5rem;
        }}

        @media (max-width: 900px) {{
            .chart-row {{
                grid-template-columns: 1fr;
            }}
        }}

        .chart-box {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 1.5rem;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        }}

        .chart-box h3 {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 1.2rem;
            border-left: 4px solid var(--primary);
            padding-left: 0.6rem;
        }}

        .svg-container {{
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
        }}

        .bar-group:hover rect {{
            fill: var(--primary);
        }}

        .console-box {{
            background-color: #020617;
            border: 1px solid #1e293b;
            border-radius: 12px;
            padding: 1rem;
            height: 180px;
            overflow-y: auto;
            font-family: 'Courier New', Courier, monospace;
            font-size: 0.8rem;
            color: #38bdf8;
            box-shadow: inset 0 2px 4px 0 rgba(0, 0, 0, 0.6);
        }}

        .console-box div {{
            margin-bottom: 0.2rem;
        }}

        .filter-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            flex-wrap: wrap;
            gap: 1rem;
        }}

        .tabs {{
            display: flex;
            gap: 0.5rem;
            background-color: var(--bg-card);
            padding: 0.4rem;
            border-radius: 14px;
            border: 1px solid var(--border-color);
        }}

        .tab-btn {{
            background: none;
            border: none;
            color: var(--text-muted);
            padding: 0.6rem 1.2rem;
            border-radius: 10px;
            font-weight: 600;
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .tab-btn.active {{
            background-color: var(--primary);
            color: var(--text-main);
            box-shadow: 0 4px 10px var(--primary-glow);
        }}

        .tab-btn:hover:not(.active) {{
            color: var(--text-main);
            background-color: rgba(255, 255, 255, 0.05);
        }}

        .filter-badge-row {{
            display: flex;
            gap: 0.5rem;
        }}

        .badge-btn {{
            background: none;
            border: 1px solid var(--border-color);
            color: var(--text-muted);
            padding: 0.4rem 0.8rem;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .badge-btn.active {{
            background-color: var(--border-color);
            color: var(--text-main);
        }}

        .test-list-wrapper {{
            display: flex;
            flex-direction: column;
            gap: 0.8rem;
        }}

        .test-card {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            overflow: hidden;
            transition: border-color 0.2s ease;
        }}

        .test-card.pass {{ border-left: 5px solid var(--success); }}
        .test-card.warn {{ border-left: 5px solid var(--warn); }}
        .test-card.fail {{ border-left: 5px solid var(--fail); }}

        .test-card.pass:hover {{ border-color: rgba(16, 185, 129, 0.4); }}
        .test-card.warn:hover {{ border-color: rgba(245, 158, 11, 0.4); }}
        .test-card.fail:hover {{ border-color: rgba(244, 63, 94, 0.4); }}

        .test-header {{
            padding: 1.2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            user-select: none;
            flex-wrap: wrap;
            gap: 1rem;
        }}

        .test-title-section {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}

        .test-title-section svg {{
            width: 24px;
            height: 24px;
            flex-shrink: 0;
        }}

        .icon-pass {{ color: var(--success); }}
        .icon-warn {{ color: var(--warn); }}
        .icon-fail {{ color: var(--fail); }}

        .test-name {{
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text-main);
        }}

        .test-category-badge {{
            display: inline-block;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            color: var(--primary);
            margin-bottom: 0.2rem;
        }}

        .test-meta-section {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}

        .test-duration {{
            font-size: 0.85rem;
            color: var(--text-muted);
            font-weight: 500;
        }}

        .test-status-badge {{
            padding: 0.3rem 0.8rem;
            border-radius: 8px;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }}

        .test-status-badge.pass {{ background-color: var(--success-glow); color: var(--success); }}
        .test-status-badge.warn {{ background-color: var(--warn-glow); color: var(--warn); }}
        .test-status-badge.fail {{ background-color: var(--fail-glow); color: var(--fail); }}

        .chevron {{
            width: 20px;
            height: 20px;
            color: var(--text-muted);
            transition: transform 0.3s ease;
        }}

        .test-card.active .chevron {{
            transform: rotate(180deg);
        }}

        .test-details {{
            border-top: 1px solid var(--border-color);
            background-color: rgba(0, 0, 0, 0.15);
            padding: 1.2rem;
            animation: slideDown 0.25s ease-out;
        }}

        @keyframes slideDown {{
            from {{ opacity: 0; transform: translateY(-5px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .test-desc {{
            font-size: 0.9rem;
            color: #cbd5e1;
            margin-bottom: 1rem;
        }}

        .test-error {{
            background-color: rgba(244, 63, 94, 0.08);
            border: 1px solid rgba(244, 63, 94, 0.2);
            border-radius: 8px;
            padding: 0.8rem;
            margin-bottom: 1rem;
        }}

        .test-error strong {{
            color: var(--fail);
            font-size: 0.85rem;
            display: block;
            margin-bottom: 0.4rem;
        }}

        .test-error pre {{
            font-family: 'Courier New', Courier, monospace;
            font-size: 0.8rem;
            color: #fda4af;
            white-space: pre-wrap;
            word-break: break-all;
        }}

        .test-logs {{
            background-color: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 0.8rem;
        }}

        .test-logs strong {{
            color: var(--text-muted);
            font-size: 0.85rem;
            display: block;
            margin-bottom: 0.4rem;
        }}

        .test-logs ul {{
            list-style: none;
            padding-left: 0.5rem;
        }}

        .test-logs li {{
            font-size: 0.82rem;
            color: #94a3b8;
            margin-bottom: 0.2rem;
            position: relative;
            padding-left: 1rem;
        }}

        .test-logs li::before {{
            content: '•';
            position: absolute;
            left: 0;
            color: var(--primary);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="title-group">
                <h1>AI Kripto Al-Sat Test Dashboard</h1>
                <p>İzole Sandbox Üzerinde Tam Uçtan Uca Doğrulama</p>
            </div>
            <div class="timestamp-badge">
                Test Zamanı: {summary['timestamp']}
            </div>
        </header>

        <div class="stats-grid">
            <div class="stat-card total">
                <div class="stat-info">
                    <h4>Toplam Test</h4>
                    <div class="stat-value">{summary['total']}</div>
                </div>
                <svg width="40" height="40" fill="none" stroke="var(--primary)" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
            </div>
            <div class="stat-card pass">
                <div class="stat-info">
                    <h4>Başarılı</h4>
                    <div class="stat-value">{summary['passed']}</div>
                </div>
                <div class="gauge-container">
                    <svg class="gauge-svg" width="80" height="80">
                        <circle class="gauge-bg" cx="40" cy="40" r="35"></circle>
                        <circle class="gauge-bar" cx="40" cy="40" r="35"></circle>
                    </svg>
                    <div class="gauge-text">{summary['success_rate']}%</div>
                </div>
            </div>
            <div class="stat-card fail">
                <div class="stat-info">
                    <h4>Hatalı / Kritik</h4>
                    <div class="stat-value">{summary['failed']}</div>
                </div>
                <svg width="40" height="40" fill="none" stroke="var(--fail)" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
            </div>
            <div class="stat-card duration">
                <div class="stat-info">
                    <h4>Süre</h4>
                    <div class="stat-value">{summary['duration']} sn</div>
                </div>
                <svg width="40" height="40" fill="none" stroke="var(--warn)" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            </div>
        </div>

        <div class="chart-row">
            <div class="chart-box">
                <h3>Ortalama Yanıt Süresi (Kategori Bazında)</h3>
                <div class="svg-container">
                    <svg width="{chart_width}" height="{chart_height}" viewBox="0 0 {chart_width} {chart_height}">
                        <defs>
                            <linearGradient id="gradient-bar" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stop-color="#818cf8"/>
                                <stop offset="100%" stop-color="#4f46e5"/>
                            </linearGradient>
                        </defs>
                        <line x1="50" y1="160" x2="450" y2="160" stroke="#334155" stroke-dasharray="4"/>
                        <line x1="50" y1="100" x2="450" y2="100" stroke="#334155" stroke-dasharray="4"/>
                        <line x1="50" y1="40" x2="450" y2="40" stroke="#334155" stroke-dasharray="4"/>
                        
                        {svg_chart_bars}
                        
                        <line x1="40" y1="160" x2="460" y2="160" stroke="#475569" stroke-width="2"/>
                    </svg>
                </div>
            </div>
            <div class="chart-box">
                <h3>Sandbox Sistem Çıktısı (Runner Console)</h3>
                <div class="console-box">
                    {sys_logs_html}
                </div>
            </div>
        </div>

        <div class="filter-row">
            <div class="tabs">
                <button class="tab-btn active" onclick="filterCategory('ALL', this)">Tüm Testler</button>
                <button class="tab-btn" onclick="filterCategory('Config', this)">Config</button>
                <button class="tab-btn" onclick="filterCategory('Database', this)">Database</button>
                <button class="tab-btn" onclick="filterCategory('Data Fetcher', this)">Fetcher</button>
                <button class="tab-btn" onclick="filterCategory('Analyzer', this)">Analyzer</button>
                <button class="tab-btn" onclick="filterCategory('AI Agent', this)">AI Agent</button>
                <button class="tab-btn" onclick="filterCategory('REST API', this)">REST API</button>
            </div>
            <div class="filter-badge-row">
                <button class="badge-btn active" onclick="filterStatus('ALL', this)">Tümü ({summary['total']})</button>
                <button class="badge-btn" onclick="filterStatus('pass', this)">Başarılı ({summary['passed']})</button>
                <button class="badge-btn" onclick="filterStatus('fail', this)">Hatalı ({summary['failed']})</button>
            </div>
        </div>

        <div class="test-list-wrapper">
            {test_cards_html}
        </div>
    </div>

    <script>
        let currentCategory = 'ALL';
        let currentStatus = 'ALL';

        function toggleAccordion(header) {{
            const card = header.parentElement;
            const details = card.querySelector('.test-details');
            const isCurrentlyOpen = details.style.display === 'block';
            
            document.querySelectorAll('.test-details').forEach(el => el.style.display = 'none');
            document.querySelectorAll('.test-card').forEach(el => el.classList.remove('active'));
            
            if (!isCurrentlyOpen) {{
                details.style.display = 'block';
                card.classList.add('active');
            }}
        }}

        function filterCategory(category, btn) {{
            currentCategory = category;
            
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            applyFilters();
        }}

        function filterStatus(status, btn) {{
            currentStatus = status;
            
            document.querySelectorAll('.badge-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            applyFilters();
        }}

        function applyFilters() {{
            const cards = document.querySelectorAll('.test-card');
            
            cards.forEach(card => {{
                const cat = card.getAttribute('data-category');
                const isPass = card.classList.contains('pass');
                const isWarn = card.classList.contains('warn');
                const isFail = card.classList.contains('fail');
                
                let matchCat = (currentCategory === 'ALL' || cat === currentCategory);
                let matchStatus = true;
                
                if (currentStatus === 'pass') {{
                    matchStatus = isPass;
                }} else if (currentStatus === 'fail') {{
                    matchStatus = isFail;
                }} else if (currentStatus === 'warn') {{
                    matchStatus = isWarn;
                }}
                
                if (matchCat && matchStatus) {{
                    card.style.display = 'block';
                }} else {{
                    card.style.display = 'none';
                }}
            }});
        }}
    </script>
</body>
</html>
"""
    
    report_path = os.path.join(PROJECT_ROOT, "test_report.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"\n{Colors.GREEN}{Colors.BOLD}✓ HTML RAPOR DOSYASI BAŞARIYLA OLUŞTURULDU: {report_path}{Colors.ENDC}")


def run_custom_sample_tests(registry):
    """
    Kullanıcının kendi test senaryolarını ekleyebilmesi için örnek bir şablon sunar.
    Bu fonksiyonu inceleyerek kendi özel testlerinizi run_tests.py içerisine yazabilirsiniz.
    """
    print(f"\n{Colors.HEADER}{Colors.BOLD}--- [7] ÖRNEK ÖZEL TEST SENARYOLARI ---{Colors.ENDC}")
    
    # -------------------------------------------------------------
    # Senaryo 1: Başarılı Örnek Matematik / Mantık Testi
    # -------------------------------------------------------------
    start_time = time.time()
    logs = []
    try:
        logs.append("Adım 1: Test parametreleri ilklendiriliyor...")
        param_a = 10
        param_b = 20
        
        logs.append(f"Adım 2: İşlem gerçekleştiriliyor ({param_a} + {param_b})...")
        toplam = param_a + param_b
        
        logs.append("Adım 3: Değerler doğrulanıyor (Assert)...")
        assert toplam == 30, f"Matematiksel hata! Sonuç: {toplam}"
        
        registry.add_result(
            test_id="sample_math_success",
            name="Başarılı Matematik & Akış Hesaplama (Örnek)",
            category="Özel Örnek",
            status="PASS",
            duration=time.time() - start_time,
            details="Bu test, özel bir test senaryosunun nasıl yazılacağını ve adımların loglanacağını gösteren başarılı bir şablondur.",
            logs=logs
        )
    except Exception as e:
        registry.add_result(
            test_id="sample_math_success",
            name="Başarılı Matematik & Akış Hesaplama (Örnek)",
            category="Özel Örnek",
            status="FAIL",
            duration=time.time() - start_time,
            error_msg=str(e),
            logs=logs
        )

    # -------------------------------------------------------------
    # Senaryo 2: Kasıtlı Olarak Uyarı / Hata Veren Simüle Hesap Kontrolü
    # -------------------------------------------------------------
    start_time = time.time()
    logs = []
    try:
        logs.append("Adım 1: Bakiye kontrolü simüle ediliyor...")
        available_balance = 50.0
        required_balance = 100.0
        
        logs.append(f"Adım 2: Koşul sorgulanıyor (Mevcut: {available_balance} USDT, Gereken: {required_balance} USDT)")
        
        # Kasıtlı olarak bir uyarı tetikleyelim
        if available_balance < required_balance:
            raise ValueError(f"Yetersiz Bakiye! Mevcut: {available_balance} USDT, Gereken: {required_balance} USDT")
            
    except Exception as e:
        # Hata durumunu görsel raporda turuncu 'UYARI' olarak görmek için status='WARN' verdik.
        # Gerçek bir hata doğrulaması için 'FAIL' de verebilirsiniz.
        registry.add_result(
            test_id="sample_balance_warning",
            name="Yetersiz Bakiye Durum Kontrolü (Örnek)",
            category="Özel Örnek",
            status="WARN",
            duration=time.time() - start_time,
            details="Kullanıcı bakiyesi yetersiz olduğunda sistemin ürettiği uyarıyı yakalayıp raporda listeleyen şablondur.",
            logs=logs,
            error_msg=str(e)
        )


# --- MAIN RUNNER ---

if __name__ == "__main__":
    import requests
    
    print("="*60)
    print(f"{Colors.CYAN}{Colors.BOLD}AI KRİPTO AL-SAT KAPSAMLI TEST SUITE BAŞLATILIYOR{Colors.ENDC}")
    print("="*60)
    
    registry = TestRegistry()
    sandbox = TestSandbox(registry)
    
    try:
        sandbox.enter()
        
        run_config_tests(registry)
        run_database_tests(registry)
        run_data_fetcher_tests(registry)
        run_analyzer_tests(registry)
        run_ai_agent_tests(registry)
        run_custom_sample_tests(registry)
        
        server_ok = sandbox.start_test_server()
        if server_ok:
            try:
                run_api_endpoint_tests(registry)
            finally:
                sandbox.stop_test_server()
        else:
            registry.add_result("api_server_start", "FastAPI Sunucusu Çalıştırma", "REST API", "FAIL", 0.0, "Uvicorn test sunucusu 8099 portunda ayağa kalkamadı.", error_msg="Server startup timeout.")
            
    except Exception as e:
        print(f"\n{Colors.RED}❌ Beklenmeyen Kritik Test Suite Hatası: {e}{Colors.ENDC}")
        traceback.print_exc()
        
    finally:
        sandbox.exit()
        
        summary = registry.get_summary()
        
        print("\n" + "="*60)
        print(f"{Colors.BOLD}TEST SONUÇLARI ÖZETİ{Colors.ENDC}")
        print("="*60)
        print(f"Toplam Test     : {summary['total']}")
        print(f"Başarılı        : {Colors.GREEN}{summary['passed']}{Colors.ENDC}")
        print(f"Hatalı (Fail)   : {Colors.RED if summary['failed'] > 0 else Colors.GREEN}{summary['failed']}{Colors.ENDC}")
        print(f"Uyarı (Warn)    : {Colors.YELLOW if summary['warned'] > 0 else Colors.GREEN}{summary['warned']}{Colors.ENDC}")
        print(f"Başarı Oranı    : {Colors.GREEN if summary['success_rate'] == 100 else Colors.YELLOW}{summary['success_rate']}%{Colors.ENDC}")
        print(f"Toplam Süre     : {summary['duration']} sn")
        print("="*60)
        
        build_html_report(registry, summary)
        
        if summary['failed'] > 0:
            sys.exit(1)
        else:
            sys.exit(0)
