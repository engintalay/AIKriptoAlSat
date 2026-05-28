#!/bin/bash

# AI Kripto Al-Sat - Run Script
# Backend sunucusını başlatır

cd "$(dirname "$0")"

# Sanal ortamı etkinleştir
source venv/bin/activate

# Backend sunucusunu başlat
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
