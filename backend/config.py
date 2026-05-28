import os
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

def load_all_env():
    """Environment değişkenlerini tekrar yükler."""
    if os.path.exists(ENV_PATH):
        load_dotenv(ENV_PATH, override=True)
    else:
        # Örnek dosyadan kopyala veya oluştur
        example_path = ENV_PATH + ".example"
        if os.path.exists(example_path):
            import shutil
            shutil.copy(example_path, ENV_PATH)
        load_dotenv(ENV_PATH)

# İlk yükleme
load_all_env()

def get_setting(key, default=None):
    """Belirtilen ayar değerini döner."""
    load_all_env() # Her okumada taze veriyi yükle
    return os.getenv(key, default)

def update_setting(key, value):
    """
    Belirli bir ayarı dinamik olarak .env dosyasına yazar.
    Bu sayede kullanıcı arayüzden Gemini API Key girdiğinde kalıcı olur.
    """
    lines = []
    found = False
    
    # Mevcut dosyayı oku
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
    # Güncelle veya Ekle
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
            
    if not found:
        # Eğer yoksa dosyanın sonuna ekle
        new_lines.append(f"{key}={value}\n")
        
    # Geri yaz
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
        
    # Çevre değişkenini bu oturum için de güncelle
    os.environ[key] = str(value)
    load_all_env()
    return True

# Exchange ayarları için helper fonksiyonlar
def get_exchange_settings():
    """Tüm exchange ayarlarını döner."""
    return {
        "exchange": get_setting("EXCHANGE", "binance"),
        "kucoin_api_key": get_setting("KUCOIN_API_KEY", ""),
        "kucoin_api_secret": get_setting("KUCOIN_API_SECRET", ""),
        "kucoin_api_passphrase": get_setting("KUCOIN_API_PASSPHRASE", ""),
        "kucoin_rate_limit": int(get_setting("KUCOIN_RATE_LIMIT", "60"))
    }
