import traceback
import asyncio
from backend.main import ask_coin_ai, ChatMessageRequest

async def test():
    try:
        print("Testing ask_coin_ai endpoint directly...")
        req = ChatMessageRequest(message="BTC trendi nedir?")
        res = await ask_coin_ai("BTCUSDT", req)
        print("Result:")
        print(res)
    except Exception as e:
        print("ERROR:")
        traceback.print_exc()

asyncio.run(test())
