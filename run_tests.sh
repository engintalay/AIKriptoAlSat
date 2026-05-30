#!/bin/bash
# AI Kripto Al-Sat - Kapsamlı Test Çalıştırıcı
# -------------------------------------------
# Bu script, testleri sanal ortam (venv) altında güvenli bir şekilde tetikler.

# Dosyanın bulunduğu klasöre geç
cd "$(dirname "$0")"

# Sanal ortam python'ı ile test suite'i çalıştır
./venv/bin/python run_tests.py
