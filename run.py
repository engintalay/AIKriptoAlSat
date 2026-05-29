#!/usr/bin/env python3
"""AI Kripto Al-Sat - Backend Sunucu Başlatıcı"""

import os
import subprocess
import sys
import signal
import time

# Sanal ortam yolu
VENV_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "bin", "python")

def start_server():
    """Backend sunucusunu başlatır"""
    print("AI Kripto Al-Sat sunucusu başlatılıyor...")
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    process = subprocess.Popen(
        [VENV_PYTHON, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        preexec_fn=os.setsid
    )
    print(f"Sunucu başlatıldı (PID: {process.pid})")
    return process

def stop_server(force=False):
    """Çalışan sunucuyu durdurur"""
    sig = signal.SIGKILL if force else signal.SIGTERM
    try:
        result = subprocess.run(
            ["pgrep", "-f", "uvicorn backend.main:app"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split("\n")
            for pid in pids:
                if pid:
                    try:
                        os.killpg(os.getpgid(int(pid)), sig)
                    except ProcessLookupError:
                        os.kill(int(pid), sig)
                    print(f"Sunucu durduruldu (PID: {pid}){' [FORCE]' if force else ''}")
        else:
            print("Çalışan sunucu bulunamadı.")
    except Exception as e:
        print(f"Hata: {e}")

def main():
    if len(sys.argv) < 2:
        print("Kullanım: python run.py [start|stop|restart]")
        return
    
    command = sys.argv[1].lower()
    
    if command == "start":
        start_server()
    elif command == "stop":
        stop_server()
    elif command == "forcestop":
        stop_server(force=True)
    elif command == "restart":
        stop_server()
        time.sleep(1)
        start_server()
    else:
        print("Geçersiz komut. Kullanım: python run.py [start|stop|forcestop|restart]")

if __name__ == "__main__":
    main()
