import os

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

def _read_env():
    """Doğrudan .env dosyasını okuyup dict olarak döner."""
    settings = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                settings[key.strip()] = value.strip()
    return settings

def get_setting(key, default=None):
    """Belirtilen ayar değerini .env dosyasından okur."""
    settings = _read_env()
    return settings.get(key, default)

def update_setting(key, value):
    """Belirli bir ayarı .env dosyasına yazar."""
    lines = []
    found = False
    
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
    
    if not found:
        new_lines.append(f"{key}={value}\n")
    
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    return True

def get_exchange_settings():
    """Tüm exchange ayarlarını döner."""
    return {
        "exchange": get_setting("EXCHANGE", "binance"),
        "kucoin_api_key": get_setting("KUCOIN_API_KEY", ""),
        "kucoin_api_secret": get_setting("KUCOIN_API_SECRET", ""),
        "kucoin_api_passphrase": get_setting("KUCOIN_API_PASSPHRASE", ""),
        "kucoin_rate_limit": int(get_setting("KUCOIN_RATE_LIMIT", "60"))
    }
