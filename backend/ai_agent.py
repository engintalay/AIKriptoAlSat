import os
import json
import requests
from datetime import datetime
import google.generativeai as genai
from backend.config import get_setting
from backend.ai_logger import ai_log

# Global abort flag - rapor/chat iptal mekanizması
_abort_flag = False

def abort_ai():
    """AI işlemini iptal et."""
    global _abort_flag
    _abort_flag = True

def reset_abort():
    """Abort flag'i sıfırla."""
    global _abort_flag
    _abort_flag = False

def is_aborted():
    return _abort_flag

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
    LLM bağlantısı olmadığında kullanıcıya bilgi veren hata raporu.
    """
    return {
        "symbol": symbol,
        "direction": "⚠️ AI BAĞLANTISI YOK",
        "score": score,
        "summary": "AI modeline bağlanılamadı. Lütfen Ayarlar'dan LLM sağlayıcınızı kontrol edin (Gemini API Key, Ollama veya llama.cpp sunucusu).",
        "entry_zone": "-",
        "stop_loss": "-",
        "take_profit_1": "-",
        "take_profit_2": "-",
        "risk_reward_ratio": "-",
        "leverage_advice": "-",
        "technical_analysis": f"Teknik veriler mevcut: RSI, MACD, Bollinger hesaplanmış. Ancak AI yorumu için LLM bağlantısı gerekli.",
        "chart_patterns": "AI bağlantısı olmadan formasyonlar analiz edilemiyor.",
        "risk_assessment": "Ayarlar > LLM Sağlayıcı bölümünden bağlantınızı kontrol edin."
    }

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
        response = requests.post(url, json=payload, timeout=300)
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
        if is_aborted(): return generate_mock_report(symbol, price, change_24h, score, signal, details)
        url = f"{llamacpp_url}/v1/chat/completions"
        payload = {
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "stream": True
        }
        ai_log("SEND", f"[{symbol}] Rapor isteği → {url}")
        ai_log("PROMPT", f"[{symbol}] {prompt}")
        collected = ""
        with requests.post(url, json=payload, timeout=300, stream=True) as response:
            if response.status_code == 200:
                for chunk in response.iter_lines():
                    if is_aborted():
                        ai_log("ABORT", f"[{symbol}] Rapor üretimi iptal edildi.")
                        response.close()
                        return generate_mock_report(symbol, price, change_24h, score, signal, details)
                    if chunk:
                        line = chunk.decode("utf-8").removeprefix("data: ").strip()
                        if line == "[DONE]": break
                        try:
                            data = json.loads(line)
                            delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            collected += delta
                            if delta:
                                ai_log("STREAM", delta)
                        except json.JSONDecodeError:
                            collected += line
                if collected:
                    ai_log("RECV", f"[{symbol}] Rapor alındı ({len(collected)} karakter)")
                    collected = collected.replace("```json", "").replace("```", "").strip()
                    return json.loads(collected)
    except Exception:
        pass
        
    # 2. Deneme: Native /completion API fallback (streaming)
    try:
        if is_aborted(): return generate_mock_report(symbol, price, change_24h, score, signal, details)
        url = f"{llamacpp_url}/completion"
        payload = {
            "prompt": prompt,
            "temperature": 0.2,
            "stream": True
        }
        collected = ""
        with requests.post(url, json=payload, timeout=300, stream=True) as response:
            if response.status_code == 200:
                for chunk in response.iter_lines():
                    if is_aborted():
                        print(f"{symbol} AI rapor üretimi iptal edildi (completion).")
                        response.close()
                        return generate_mock_report(symbol, price, change_24h, score, signal, details)
                    if chunk:
                        line = chunk.decode("utf-8").removeprefix("data: ").strip()
                        if line == "[DONE]": break
                        try:
                            data = json.loads(line)
                            collected += data.get("content", "")
                        except json.JSONDecodeError:
                            collected += line
                if collected:
                    collected = collected.replace("```json", "").replace("```", "").strip()
                    return json.loads(collected)
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
    """LLM bağlantısı olmadığında kullanıcıya bilgi veren hata mesajı."""
    return f"⚠️ AI modeline bağlanılamadı. Chat özelliği için Ayarlar'dan LLM sağlayıcınızı (Gemini/Ollama/llama.cpp) kontrol edin."

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
        response = requests.post(url, json=payload, timeout=300)
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
    
    # 1. Deneme: OpenAI Uyumlu Chat API (streaming)
    try:
        if is_aborted(): return get_simulated_chat_reply(symbol, user_message, price, signal, score)
        url = f"{llamacpp_url}/v1/chat/completions"
        payload = {
            "messages": messages,
            "temperature": 0.7,
            "stream": True
        }
        ai_log("SEND", f"[{symbol}] Chat isteği → {url}")
        ai_log("PROMPT", f"[{symbol}] Kullanıcı: {user_message}")
        collected = ""
        with requests.post(url, json=payload, timeout=300, stream=True) as response:
            if response.status_code == 200:
                for chunk in response.iter_lines():
                    if is_aborted():
                        response.close()
                        ai_log("ABORT", f"[{symbol}] Chat iptal edildi.")
                        return "⚠️ İstek iptal edildi."
                    if chunk:
                        line = chunk.decode("utf-8").removeprefix("data: ").strip()
                        if line == "[DONE]": break
                        try:
                            data = json.loads(line)
                            delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            collected += delta
                            if delta:
                                ai_log("STREAM", delta)
                        except json.JSONDecodeError:
                            pass
                if collected:
                    ai_log("RECV", f"[{symbol}] Chat yanıtı alındı ({len(collected)} karakter)")
                    return collected
    except Exception:
        pass
        
    # 2. Deneme: Native /completion fallback (streaming)
    try:
        if is_aborted(): return get_simulated_chat_reply(symbol, user_message, price, signal, score)
        full_prompt = f"{system_prompt}\n\n"
        for msg in messages[1:]:
            role_label = "Kullanıcı" if msg["role"] == "user" else "Analist"
            full_prompt += f"{role_label}: {msg['content']}\n"
        full_prompt += "Analist: "
        
        url = f"{llamacpp_url}/completion"
        payload = {
            "prompt": full_prompt,
            "temperature": 0.7,
            "stream": True,
            "stop": ["Kullanıcı:", "Analist:"]
        }
        collected = ""
        with requests.post(url, json=payload, timeout=300, stream=True) as response:
            if response.status_code == 200:
                for chunk in response.iter_lines():
                    if is_aborted():
                        response.close()
                        return "⚠️ İstek iptal edildi."
                    if chunk:
                        line = chunk.decode("utf-8").removeprefix("data: ").strip()
                        if line == "[DONE]": break
                        try:
                            data = json.loads(line)
                            collected += data.get("content", "")
                        except json.JSONDecodeError:
                            pass
                if collected:
                    return collected.strip()
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
