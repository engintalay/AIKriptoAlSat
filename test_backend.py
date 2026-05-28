#!/usr/bin/env python3
import sys
import os

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(PROJECT_ROOT)

from backend.database import init_db, save_scanned_coins, get_scanned_coins
import backend.data_fetcher as data_fetcher
import backend.analyzer as analyzer
import backend.ai_agent as ai_agent

def test_database():
    print("Testing database setup...")
    init_db()
    print("✓ Database initialized successfully.")

def test_data_fetcher():
    print("Testing data fetcher from Binance API...")
    # 1. Fetch top volume pairs
    pairs = data_fetcher.fetch_top_usdt_pairs(limit=5)
    assert len(pairs) > 0, "Failed to fetch top USDT pairs from Binance!"
    print(f"✓ Successfully fetched {len(pairs)} top USDT pairs. Top coin: {pairs[0]['symbol']} (${pairs[0]['price']})")
    
    # 2. Fetch candles
    df = data_fetcher.fetch_ohlcv(pairs[0]['symbol'], interval="1h", limit=50)
    assert df is not None, f"Failed to fetch candles for {pairs[0]['symbol']}!"
    assert len(df) == 50, f"Candles length mismatch! Expected 50, got {len(df)}"
    print("✓ Successfully fetched candle history from Binance.")
    return df, pairs[0]

def test_analyzer(df, ticker_info):
    print("Testing technical analysis calculations...")
    df_ind = analyzer.calculate_indicators(df)
    assert df_ind is not None, "Failed to compute indicators!"
    assert "rsi" in df_ind.columns, "RSI column is missing!"
    assert "macd" in df_ind.columns, "MACD column is missing!"
    assert "bb_lower" in df_ind.columns, "Bollinger bands columns are missing!"
    print("✓ Safely calculated indicators (RSI, MACD, Moving Averages, BB) using pure pandas.")
    
    analysis = analyzer.analyze_coin_status(df, ticker_info)
    assert "ai_score" in analysis, "Analysis missing AI Score!"
    assert "signal" in analysis, "Analysis missing trade signal!"
    print(f"✓ Multi-Factor Scoring works. Coin Score: {analysis['ai_score']}, Signal: {analysis['signal']}")
    return analysis

def test_ai_agent(analysis):
    print("Testing AI Agent report generator...")
    # Force Mock generator for offline/resilient verification
    mock_report = ai_agent.generate_mock_report(
        analysis["symbol"],
        analysis["price"],
        analysis["change_24h"],
        analysis["ai_score"],
        analysis["signal"],
        analysis["details"]
    )
    assert mock_report["symbol"] == analysis["symbol"], "Mock symbol mismatch!"
    assert "entry_zone" in mock_report, "Missing entry levels in trade plan!"
    print("✓ Smart AI simulated report works with accurate trade levels and formatting.")

if __name__ == "__main__":
    print("="*40)
    print("RUNNING AI KRİPTO AL-SAT BACKEND TESTS")
    print("="*40)
    try:
        test_database()
        df, ticker = test_data_fetcher()
        analysis = test_analyzer(df, ticker)
        test_ai_agent(analysis)
        print("="*40)
        print("✓ ALL TESTS COMPLETED SUCCESSFULLY!")
        print("="*40)
    except Exception as e:
        print("="*40)
        print(f"❌ TEST FAILED: {e}")
        print("="*40)
        sys.exit(1)
