#!/bin/bash

# AI Kripto Al-Sat - Stop Script
# Çalışan backend sunucusunu durdurur

pgrep -f "uvicorn main:app" | xargs -r kill
