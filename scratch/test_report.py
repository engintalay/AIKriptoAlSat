import traceback
from backend.ai_agent import generate_ai_report

try:
    print("Testing generate_ai_report with llamacpp...")
    report = generate_ai_report(
        symbol="BTCUSDT",
        price=73000.0,
        change_24h=1.5,
        score=85,
        signal="STRONG BUY",
        details={"reasons": ["RSI cross", "EMA cross"], "rsi": 65.0}
    )
    print("Report generated successfully:")
    print(report)
except Exception as e:
    print("ERROR:")
    traceback.print_exc()
