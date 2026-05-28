import traceback
import asyncio
from backend.main import get_coin_report

async def test():
    try:
        print("Testing get_coin_report endpoint directly...")
        res = await get_coin_report("BTCUSDT")
        print("Result:")
        print(res)
    except Exception as e:
        print("ERROR:")
        traceback.print_exc()

asyncio.run(test())
