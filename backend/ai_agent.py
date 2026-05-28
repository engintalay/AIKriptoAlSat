import os
import json
import random
import requests
from datetime import datetime
import google.generativeai as genai
from backend.config import get_setting

def is_api_key_valid():
    """Gemini API Key'in tanımlı olup olmadığını kontrol eder."""
    api_key = get_setting("GEMINI_API_KEY")
    return bool(api_key and len(api_key.strip()) > 10 and not api_key.startswith("your_"))

def init_gemini():
    """Gemini modelini initialize eder."""
    if is_api_key_valid():
        api_key = get_setting("GEMINI_API_KEY")
        genai.configure(api_key=api_key)
        return genai.GenerativeModel("gemini-1.5-flash")
    return None

def generate_mock_report(symbol, price, change_24h, score, signal, details):
    """
    API Key olmadığında çalışan, teknik göstergelerle 100% uyumlu
    akıllı bir simüle edilmiş AI rapor jeneratörü.
    """
    if not isinstance(details, dict):
        details = {}
    # Giriş, Stop Loss ve TP seviyelerini matematiksel olarak hesapla
    # BUY yönünde giriş fiyata yakın, stop %3 aşağıda, TP'ler yukarıda.
    # SELL yönünde tam tersi (Short işlem)
    is_buy = "BUY" in signal
    
    if is_buy:
        entry_min = price * 0.995
        entry_max = price * 1.002
        stop_loss = price * 0.965
        tp1 = price * 1.035
        tp2 = price * 1.07
        risk_reward = "1:2.3"
        leverage = "3x - 5x (Isolated)"
        direction = "LONG / BUY"
    else:
        entry_min = price * 0.998
        entry_max = price * 1.005
        stop_loss = price * 1.035
        tp1 = price * 0.965
        tp2 = price * 0.93
        risk_reward = "1:2.0"
        leverage = "2x - 3x (Isolated)"
        direction = "SHORT / SELL"
        
    if "HOLD" in signal:
        entry_min = price * 0.99
        entry_max = price * 1.01
        stop_loss = price * 0.95
        tp1 = price * 1.05
        tp2 = price * 1.10
        risk_reward = "1:1.8"
        leverage = "Kaldıraç Önerilmez (Spot)"
        direction = "WAIT / ACCUMULATE"

    reasons_str = " • " + "\n • ".join(details.get("reasons", ["Fiyat yatay seyrediyor."]))
    
    # Simüle edilmiş rapor metinleri
    summaries = {
        "STRONG BUY": f"{symbol} paritesinde çok güçlü bir alım ivmesi gözlemleniyor. Teknik göstergelerin tamamı boğa lehine dönmüş durumda. Yüksek hacimli kırılımla birlikte yükselişin devam etmesi bekleniyor.",
        "BUY": f"{symbol} paritesi teknik açıdan olumlu bir alım bölgesinde. İndikatörler aşırı satım sonrası toparlanmaya işaret ediyor. Destek seviyelerinden kademeli alım değerlendirilebilir.",
        "HOLD": f"{symbol} şu anda karar aşamasında. Yatay konsolidasyon veya kararsız mum yapıları mevcut. Yeni bir kırılım yönü gelene kadar pozisyon korumak en makul seçenektir.",
        "SELL": f"{symbol} paritesinde ayıların baskısı artıyor. Kısa vadeli destekler kırılmış durumda ve momentum zayıflıyor. Kâr alımı veya risk azaltımı düşünülebilir.",
        "STRONG SELL": f"{symbol} paritesinde çok ciddi bir satış baskısı mevcut. Tüm hareketli ortalamaların altına inilmiş durumda ve RSI aşırı satım bölgesine doğru dik bir düşüş gösteriyor. Risk oldukça yüksek."
    }
    
    patterns = [
        "Yükselen Üçgen (Ascending Triangle) Formasyonu belirginleşiyor.",
        "İkili Dip (Double Bottom) Formasyonu tamamlanmak üzere.",
        "Fiyat, majör direnç bölgesinden sert bir hacimle geri çekildi.",
        "Düşen Kama (Falling Wedge) yukarı yönlü kırıldı.",
        "RSI ve Fiyat arasında hafif bir pozitif uyumsuzluk (Bullish Divergence) var.",
        "Kritik EMA 50 desteği başarıyla test edildi ve alıcılar devreye girdi."
    ]
    
    chosen_pattern = random.choice(patterns) if is_buy else "Dirençten dönüş / OBO (Omuz Baş Omuz) riski mevcut."
    if "HOLD" in signal:
        chosen_pattern = "Dikdörtgen Konsolidasyon Alanı (Yatay Kanal) içinde hareket ediyor."

    report = {
        "symbol": symbol,
        "direction": direction,
        "score": score,
        "summary": summaries.get(signal, "Parite nötr durumda."),
        "entry_zone": f"{entry_min:.4f} - {entry_max:.4f}",
        "stop_loss": f"{stop_loss:.4f}",
        "take_profit_1": f"{tp1:.4f}",
        "take_profit_2": f"{tp2:.4f}",
        "risk_reward_ratio": risk_reward,
        "leverage_advice": leverage,
        "technical_analysis": f"Hesaplanan göstergeler:\n{reasons_str}\nRSI değeri {details.get('rsi', 50.0):.1f} seviyesinde ve MACD trend gücünü doğruluyor.",
        "chart_patterns": chosen_pattern,
        "risk_assessment": "Piyasanın genel yönü (Bitcoin hareketleri) yakından takip edilmelidir. Stop seviyesine sadık kalınmalıdır."
    }
    return report

def generate_ollama_report(symbol, price, change_24h, score, signal, details):
    """
    Ollama API kullanarak yerel bir LLM üzerinden Al-Sat işlem raporu üretir.
    """
    if not isinstance(details, dict):
        details = {}
    ollama_url = get_setting("OLLAMA_API_URL", "http://localhost:11434").rstrip('/')
    model_name = get_setting("OLLAMA_MODEL", "llama3")
    
    reasons_str = "\n".join([f"- {r}" for r in details.get("reasons", [])])
    
    prompt = f"""
    Sen uzman bir kripto para ticaret analistisin. Sana vereceğim teknik verileri inceleyip bana profesyonel ve uygulamaya hazır bir Al-Sat işlem stratejisi ve teknik rapor sunacaksın.
    
    Parametreler:
    - Coin: {symbol}
    - Anlık Fiyat: {price}
    - 24 Saatlik Değişim: {change_24h}%
    - Teknik Skor (0-100): {score}
    - Sinyal Durumu: {signal}
    - İndikatör Ayrıntıları:
      * RSI: {details.get('rsi', 'Belirsiz')}
      * MACD: {details.get('macd', 'Belirsiz')} (Sinyal: {details.get('macd_signal', 'Belirsiz')})
      * Bollinger Alt Bandı: {details.get('bb_lower', 'Belirsiz')}
      * Bollinger Üst Bandı: {details.get('bb_upper', 'Belirsiz')}
      * EMA 50: {details.get('ema_50', 'Belirsiz')}
      * EMA 200: {details.get('ema_200', 'Belirsiz')}
    - Tespit Edilen Teknik Bulgular:
    {reasons_str}
    
    Lütfen yanıtını AŞAĞIDAKİ JSON formatında gönder. Sadece geçerli JSON çıktısı ver, açıklama satırı ekleme, JSON kod blokları (```json ) içine alma, doğrudan ham JSON objesi olsun:
    {{
      "symbol": "{symbol}",
      "direction": "LONG / BUY veya SHORT / SELL veya WAIT / HOLD (Net işlem yönü)",
      "score": {score},
      "summary": "Coine ait 2-3 cümlelik genel piyasa ve momentum yorumu (Türkçe)",
      "entry_zone": "Net fiyat aralığı girin (örn: 1.2400 - 1.2550)",
      "stop_loss": "Net stop seviyesi (fiyat olarak)",
      "take_profit_1": "Kâr al seviyesi 1 (fiyat olarak)",
      "take_profit_2": "Kâr al seviyesi 2 (fiyat olarak)",
      "risk_reward_ratio": "Risk ödül oranı (örn: 1:2.5)",
      "leverage_advice": "Önerilen kaldıraç seviyesi ve modu (örn: 3x Isolated veya Kaldıraçsız Spot)",
      "technical_analysis": "RSI, MACD ve hareketli ortalamalara dayalı 2 cümlelik derin teknik analiz (Türkçe)",
      "chart_patterns": "Bu fiyat hareketlerinde oluşması muhtemel formasyon analizi (örn: İkili dip, bayrak formasyonu, direnç kırılımı vb. Türkçe)",
      "risk_assessment": "İşleme girerken dikkat edilmesi gereken risk unsurları (örn: BTC volatilitesi, veri açıklamaları vb. Türkçe)"
    }}
    """
    
    try:
        url = f"{ollama_url}/api/generate"
        payload = {
            "model": model_name,
            "prompt": prompt,
            "format": "json",
            "stream": False
        }
        response = requests.post(url, json=payload, timeout=25)
        if response.status_code == 200:
            result = response.json()
            report_text = result.get("response", "")
            return json.loads(report_text)
        else:
            print(f"Ollama hata kodu döndü: {response.status_code}. Mock moda geçiliyor...")
            return generate_mock_report(symbol, price, change_24h, score, signal, details)
    except Exception as e:
        print(f"Ollama API bağlantı hatası: {e}. Mock moda geçiliyor...")
        return generate_mock_report(symbol, price, change_24h, score, signal, details)

def generate_llamacpp_report(symbol, price, change_24h, score, signal, details):
    """
    llama.cpp API kullanarak yerel bir model üzerinden Al-Sat işlem raporu üretir.
    Hem OpenAI uyumlu /v1/chat/completions hem de sade /completion uç noktalarını destekler.
    """
    if not isinstance(details, dict):
        details = {}
    llamacpp_url = get_setting("LLAMACPP_API_URL", "http://localhost:8080").rstrip('/')
    
    reasons_str = "\n".join([f"- {r}" for r in details.get("reasons", [])])
    
    prompt = f"""
    Sen uzman bir kripto para ticaret analistisin. Sana vereceğim teknik verileri inceleyip bana profesyonel ve uygulamaya hazır bir Al-Sat işlem stratejisi ve teknik rapor sunacaksın.
    
    Parametreler:
    - Coin: {symbol}
    - Anlık Fiyat: {price}
    - 24 Saatlik Değişim: {change_24h}%
    - Teknik Skor (0-100): {score}
    - Sinyal Durumu: {signal}
    - İndikatör Ayrıntıları:
      * RSI: {details.get('rsi', 'Belirsiz')}
      * MACD: {details.get('macd', 'Belirsiz')} (Sinyal: {details.get('macd_signal', 'Belirsiz')})
      * Bollinger Alt Bandı: {details.get('bb_lower', 'Belirsiz')}
      * Bollinger Üst Bandı: {details.get('bb_upper', 'Belirsiz')}
      * EMA 50: {details.get('ema_50', 'Belirsiz')}
      * EMA 200: {details.get('ema_200', 'Belirsiz')}
    - Tespit Edilen Teknik Bulgular:
    {reasons_str}
    
    Lütfen yanıtını AŞAĞIDAKİ JSON formatında gönder. Sadece geçerli JSON çıktısı ver, açıklama satırı ekleme, JSON kod blokları (```json ) içine alma, doğrudan ham JSON objesi olsun:
    {{
      "symbol": "{symbol}",
      "direction": "LONG / BUY veya SHORT / SELL veya WAIT / HOLD (Net işlem yönü)",
      "score": {score},
      "summary": "Coine ait 2-3 cümlelik genel piyasa ve momentum yorumu (Türkçe)",
      "entry_zone": "Net fiyat aralığı girin (örn: 1.2400 - 1.2550)",
      "stop_loss": "Net stop seviyesi (fiyat olarak)",
      "take_profit_1": "Kâr al seviyesi 1 (fiyat olarak)",
      "take_profit_2": "Kâr al seviyesi 2 (fiyat olarak)",
      "risk_reward_ratio": "Risk ödül oranı (örn: 1:2.5)",
      "leverage_advice": "Önerilen kaldıraç seviyesi ve modu (örn: 3x Isolated veya Kaldıraçsız Spot)",
      "technical_analysis": "RSI, MACD ve hareketli ortalamalara dayalı 2 cümlelik derin teknik analiz (Türkçe)",
      "chart_patterns": "Bu fiyat hareketlerinde oluşması muhtemel formasyon analizi (örn: İkili dip, bayrak formasyonu, direnç kırılımı vb. Türkçe)",
      "risk_assessment": "İşleme girerken dikkat edilmesi gereken risk unsurları (örn: BTC volatilitesi, veri açıklamaları vb. Türkçe)"
    }}
    """
    
    # 1. Deneme: OpenAI Uyumlu Chat API
    try:
        url = f"{llamacpp_url}/v1/chat/completions"
        payload = {
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }
        response = requests.post(url, json=payload, timeout=25)
        if response.status_code == 200:
            result = response.json()
            report_text = result["choices"][0]["message"]["content"]
            # Markdown formatındaki JSON'u temizle
            report_text = report_text.replace("```json", "").replace("```", "").strip()
            return json.loads(report_text)
    except Exception:
        pass
        
    # 2. Deneme: Native /completion API fallback
    try:
        url = f"{llamacpp_url}/completion"
        payload = {
            "prompt": prompt,
            "temperature": 0.2,
            "stream": False
        }
        response = requests.post(url, json=payload, timeout=25)
        if response.status_code == 200:
            result = response.json()
            report_text = result.get("content", "")
            report_text = report_text.replace("```json", "").replace("```", "").strip()
            return json.loads(report_text)
    except Exception as e:
        print(f"llama.cpp bağlantı hatası: {e}. Mock moda geçiliyor...")
        
    return generate_mock_report(symbol, price, change_24h, score, signal, details)

def generate_ai_report(symbol, price, change_24h, score, signal, details):
    """
    Seçilen sağlayıcıya (Gemini, Ollama veya llama.cpp) göre kripto analiz raporu hazırlar.
    Hata durumunda akıllı mock raporuna fallback yapar.
    """
    if not isinstance(details, dict):
        details = {}
    provider = get_setting("LLM_PROVIDER", "gemini").lower()
    if provider == "ollama":
        return generate_ollama_report(symbol, price, change_24h, score, signal, details)
    elif provider == "llamacpp":
        return generate_llamacpp_report(symbol, price, change_24h, score, signal, details)
        
    model = init_gemini()
    if not model:
        # Mock modu aktifleştir
        return generate_mock_report(symbol, price, change_24h, score, signal, details)
        
    # Gemini prompt hazırlama
    reasons_str = "\n".join([f"- {r}" for r in details.get("reasons", [])])
    
    prompt = f"""
    Sen uzman bir kripto para ticaret analistisin. Sana vereceğim teknik verileri inceleyip bana profesyonel ve uygulamaya hazır bir Al-Sat işlem stratejisi ve teknik rapor sunacaksın.
    
    Parametreler:
    - Coin: {symbol}
    - Anlık Fiyat: {price}
    - 24 Saatlik Değişim: {change_24h}%
    - Teknik Skor (0-100): {score}
    - Sinyal Durumu: {signal}
    - İndikatör Ayrıntıları:
      * RSI: {details.get('rsi', 'Belirsiz')}
      * MACD: {details.get('macd', 'Belirsiz')} (Sinyal: {details.get('macd_signal', 'Belirsiz')})
      * Bollinger Alt Bandı: {details.get('bb_lower', 'Belirsiz')}
      * Bollinger Üst Bandı: {details.get('bb_upper', 'Belirsiz')}
      * EMA 50: {details.get('ema_50', 'Belirsiz')}
      * EMA 200: {details.get('ema_200', 'Belirsiz')}
    - Tespit Edilen Teknik Bulgular:
    {reasons_str}
    
    Lütfen yanıtını AŞAĞIDAKİ JSON formatında gönder. Sadece geçerli JSON çıktısı ver, açıklama satırı ekleme, JSON kod blokları (```json ) içine alma, doğrudan ham JSON objesi olsun:
    {{
      "symbol": "{symbol}",
      "direction": "LONG / BUY veya SHORT / SELL veya WAIT / HOLD (Net işlem yönü)",
      "score": {score},
      "summary": "Coine ait 2-3 cümlelik genel piyasa ve momentum yorumu (Türkçe)",
      "entry_zone": "Net fiyat aralığı girin (örn: 1.2400 - 1.2550)",
      "stop_loss": "Net stop seviyesi (fiyat olarak)",
      "take_profit_1": "Kâr al seviyesi 1 (fiyat olarak)",
      "take_profit_2": "Kâr al seviyesi 2 (fiyat olarak)",
      "risk_reward_ratio": "Risk ödül oranı (örn: 1:2.5)",
      "leverage_advice": "Önerilen kaldıraç seviyesi ve modu (örn: 3x Isolated veya Kaldıraçsız Spot)",
      "technical_analysis": "RSI, MACD ve hareketli ortalamalara dayalı 2 cümlelik derin teknik analiz (Türkçe)",
      "chart_patterns": "Bu fiyat hareketlerinde oluşması muhtemel formasyon analizi (örn: İkili dip, bayrak formasyonu, direnç kırılımı vb. Türkçe)",
      "risk_assessment": "İşleme girerken dikkat edilmesi gereken risk unsurları (örn: BTC volatilitesi, veri açıklamaları vb. Türkçe)"
    }}
    """
    
    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        report_dict = json.loads(response.text)
        return report_dict
    except Exception as e:
        print(f"Gemini API rapor üretirken hata verdi: {e}. Mock moda geçiliyor...")
        return generate_mock_report(symbol, price, change_24h, score, signal, details)

def get_simulated_chat_reply(symbol, user_message, price, signal, score):
    """Chat için akıllı ve dinamik simüle edilmiş AI cevapları."""
    msg = user_message.lower()
    
    # Kelime yakalayarak özel cevaplar üretelim
    if "giriş" in msg or "nereden al" in msg or "gireyim" in msg:
        if "BUY" in signal:
            return f"**{symbol}** şu an güçlü bir alım bölgesinde ({price} USDT). Önerilen giriş aralığımız fiyata oldukça yakın. Kademeli alım stratejisi ile bu bölgeden girmek, olası ufak geri çekilmelerde ortalamanızı iyileştirmenizi sağlar."
        else:
            return f"**{symbol}** için şu an doğrudan alım önermiyorum. Fiyat düşüş trendinde veya kararsız bir bölgede. Destek seviyelerine doğru bir çekilme beklenmeli veya teknik kırılımın gerçekleşmesi beklenmelidir."
            
    elif "stop" in msg or "zarar kes" in msg or "patlar" in msg:
        stop_val = price * 0.965 if "BUY" in signal else price * 1.035
        return f"**{symbol}** işlem planında stop seviyesi son derece kritiktir. Şu anki analize göre stop seviyemiz **{stop_val:.4f} USDT** olarak hesaplanmıştır. Bu seviyenin altında 4 saatlik mum kapanışı gelmesi durumunda pozisyondan çıkmak sermayenizi koruyacaktır."
        
    elif "hedef" in msg or "tp" in msg or "kar al" in msg or "nereye" in msg:
        tp1 = price * 1.035 if "BUY" in signal else price * 0.965
        tp2 = price * 1.07 if "BUY" in signal else price * 0.93
        return f"**{symbol}** için hedeflerimiz sırasıyla:\n🎯 **TP 1:** {tp1:.4f} USDT (%3.5 potansiyel)\n🎯 **TP 2:** {tp2:.4f} USDT (%7 potansiyel)\nYükseliş trendlerinde TP1 seviyesinde pozisyonun yarısını kapatıp stop noktasını giriş seviyesine çekmek harika bir risk yönetimidir."
        
    elif "indikatör" in msg or "rsi" in msg or "macd" in msg:
        return f"**{symbol}** teknik göstergelerine baktığımızda, AI Skorunun **{score}/100** olduğunu görüyoruz. Bu skor, indikatörlerin ağırlıklı ortalamasıyla hesaplanır. Detay panelinde görebileceğiniz üzere, RSI gücünü koruyor ve MACD momentumu destekliyor."
        
    elif "destek" in msg or "direnç" in msg or "seviye" in msg:
        destek = price * 0.97
        direnc = price * 1.04
        return f"**{symbol}** paritesinde takip ettiğimiz güncel teknik seviyeler:\n🛡️ **Majör Destek:** {destek:.4f} USDT\n⚡ **Majör Direnç:** {direnc:.4f} USDT\nFiyat bu direnci hacimli kırarsa yükseliş ivme kazanacaktır."

    elif "kaldıraç" in msg or "risk" in msg:
        return f"**{symbol}** volatilitesi yüksek bir paritedir. Bu nedenle **maksimum 3x-5x kaldıraç (Isolated)** kullanmanızı veya doğrudan **Spot** piyasada işlem yapmanızı öneririm. Kaldıraçlı işlemlerde likidasyon seviyenizi stop seviyenizin altında tutmaya dikkat edin."

    # Genel / Selamlaşma cevapları
    welcome_keywords = ["merhaba", "selam", "hey", "nasılsın", "yardım"]
    if any(k in msg for k in welcome_keywords):
        return f"Merhaba! Ben **{symbol}** Analiz Asistanıyım. Bu coine dair indikatör durumlarını, formasyonları, giriş/çıkış stratejilerini sorabilirsin. Sana nasıl yardımcı olabilirim?"

    return f"**{symbol}** için sorduğunuz soruyu anladım. Güncel AI Analiz Skoruna ({score}/100) göre parite **{signal}** sinyalinde. İşlem stratejimiz dahilinde Giriş Bölgesi ({price:.4f} civarı) ve Stop seviyelerine sadık kalarak işlem yönetmenizi tavsiye ederim. Başka bir teknik seviyeyi veya indikatör yorumunu merak ediyorsanız sorabilirsiniz!"

def chat_with_ollama(symbol, price, signal, score, chat_history, user_message):
    """
    Ollama API kullanarak yerel bir LLM üzerinden coine özel chat yanıtı üretir.
    """
    ollama_url = get_setting("OLLAMA_API_URL", "http://localhost:11434").rstrip('/')
    model_name = get_setting("OLLAMA_MODEL", "llama3")
    
    system_prompt = f"""
    Sen uzman bir kripto para ticaret analistisin. Kullanıcının sorduğu soruya aşağıdaki coin verilerine ve indikatörlerine dayanarak Türkçe, samimi ama profesyonel, net ve kısa yanıtlar vereceksin. 
    Gereksiz laf kalabalığı yapma. Finansal tavsiye vermediğini yasal olarak hatırlatmak yerine profesyonel bir işlemci gibi net stratejiler sun.
    
    Coin Verileri:
    - Coin: {symbol}
    - Anlık Fiyat: {price} USDT
    - Sinyal: {signal}
    - AI Güç Skoru: {score}/100
    """
    
    messages = [
        {"role": "system", "content": system_prompt}
    ]
    
    # Son 10 sohbet mesajını bağlam olarak ekle
    for chat in chat_history[-10:]:
        role = "user" if chat["sender"] == "USER" else "assistant"
        messages.append({"role": role, "content": chat["message"]})
        
    messages.append({"role": "user", "content": user_message})
    
    try:
        url = f"{ollama_url}/api/chat"
        payload = {
            "model": model_name,
            "messages": messages,
            "stream": False
        }
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 200:
            result = response.json()
            return result.get("message", {}).get("content", "Yanıt alınamadı.")
        else:
            return get_simulated_chat_reply(symbol, user_message, price, signal, score)
    except Exception as e:
        print(f"Ollama Chat bağlantı hatası: {e}. Simülatöre geçiliyor...")
        return get_simulated_chat_reply(symbol, user_message, price, signal, score)

def chat_with_llamacpp(symbol, price, signal, score, chat_history, user_message):
    """
    llama.cpp API kullanarak yerel bir LLM üzerinden coine özel chat yanıtı üretir.
    """
    llamacpp_url = get_setting("LLAMACPP_API_URL", "http://localhost:8080").rstrip('/')
    
    system_prompt = f"""
    Sen uzman bir kripto para ticaret analistisin. Kullanıcının sorduğu soruya aşağıdaki coin verilerine ve indikatörlerine dayanarak Türkçe, samimi ama profesyonel, net ve kısa yanıtlar vereceksin. 
    Gereksiz laf kalabalığı yapma. Finansal tavsiye vermediğini yasal olarak hatırlatmak yerine profesyonel bir işlemci gibi net stratejiler sun.
    
    Coin Verileri:
    - Coin: {symbol}
    - Anlık Fiyat: {price} USDT
    - Sinyal: {signal}
    - AI Güç Skoru: {score}/100
    """
    
    messages = [
        {"role": "system", "content": system_prompt}
    ]
    
    # Son 10 sohbet mesajını bağlam olarak ekle
    for chat in chat_history[-10:]:
        role = "user" if chat["sender"] == "USER" else "assistant"
        messages.append({"role": role, "content": chat["message"]})
        
    messages.append({"role": "user", "content": user_message})
    
    # 1. Deneme: OpenAI Uyumlu Chat API
    try:
        url = f"{llamacpp_url}/v1/chat/completions"
        payload = {
            "messages": messages,
            "temperature": 0.7
        }
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]
    except Exception:
        pass
        
    # 2. Deneme: Native /completion fallback
    try:
        full_prompt = f"{system_prompt}\n\n"
        for msg in messages[1:]:
            role_label = "Kullanıcı" if msg["role"] == "user" else "Analist"
            full_prompt += f"{role_label}: {msg['content']}\n"
        full_prompt += "Analist: "
        
        url = f"{llamacpp_url}/completion"
        payload = {
            "prompt": full_prompt,
            "temperature": 0.7,
            "stream": False,
            "stop": ["Kullanıcı:", "Analist:"]
        }
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 200:
            result = response.json()
            return result.get("content", "").strip()
    except Exception as e:
        print(f"llama.cpp Chat bağlantı hatası: {e}. Simülatöre geçiliyor...")
        
    return get_simulated_chat_reply(symbol, user_message, price, signal, score)

def chat_with_coin_ai(symbol, price, signal, score, chat_history, user_message):
    """
    Seçilen sağlayıcıya (Gemini, Ollama veya llama.cpp) göre coine özel chat yanıtı üretir.
    Hata durumunda akıllı mock yanıtına fallback yapar.
    """
    provider = get_setting("LLM_PROVIDER", "gemini").lower()
    if provider == "ollama":
        return chat_with_ollama(symbol, price, signal, score, chat_history, user_message)
    elif provider == "llamacpp":
        return chat_with_llamacpp(symbol, price, signal, score, chat_history, user_message)
        
    model = init_gemini()
    if not model:
        # Mock modu aktifleştir
        return get_simulated_chat_reply(symbol, user_message, price, signal, score)
        
    # Sohbet geçmişini Gemini formatına çevir
    formatted_history = []
    for chat in chat_history[-10:]: # Son 10 mesajı bağlam olarak gönder
        role = "user" if chat["sender"] == "USER" else "model"
        formatted_history.append({"role": role, "parts": [chat["message"]]})
        
    prompt = f"""
    Sen uzman bir kripto para ticaret analistisin. Kullanıcının sorduğu soruya aşağıdaki coin verilerine ve indikatörlerine dayanarak Türkçe, samimi ama profesyonel, net ve kısa yanıtlar vereceksin. 
    Gereksiz laf kalabalığı yapma. Finansal tavsiye vermediğini yasal olarak hatırlatmak yerine profesyonel bir işlemci gibi net stratejiler sun.
    
    Coin Verileri:
    - Coin: {symbol}
    - Anlık Fiyat: {price} USDT
    - Sinyal: {signal}
    - AI Güç Skoru: {score}/100
    
    Kullanıcının Sorusu: {user_message}
    """
    
    try:
        # Chat oturumu başlatarak geçmişle birlikte gönder
        chat_session = model.start_chat(history=formatted_history)
        response = chat_session.send_message(prompt)
        return response.text
    except Exception as e:
        print(f"Gemini Chat hatası: {e}. Mock yanıta geçiliyor...")
        return get_simulated_chat_reply(symbol, user_message, price, signal, score)
