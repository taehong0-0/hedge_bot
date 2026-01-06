import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from exchange_factory import create_exchange, symbol_create
import asyncio
from keys.pk_extended import EDGEX_KEY as EXTENDED_KEY

# testing Extended exchange connectivity and orders

coin = 'BTC' # Target BTC for volume bot
symbol = symbol_create('extended', coin) # BTCUSDT

async def main():
    print(f"Testing Extended with symbol: {symbol}")
    extended = await create_exchange('extended', EXTENDED_KEY)

    try:
        # 1. Get Mark Price
        price = await extended.get_mark_price(symbol)
        print(f"Mark Price: {price}")

        # 2. Get Collateral
        coll = await extended.get_collateral()
        print(f"Collateral: {coll}")

        # 3. Create Limit Buy (far away to avoid fill)
        buy_price = price * 0.5
        print(f"Placing Limit Buy at: {buy_price}")
        order = await extended.create_order(symbol, 'buy', 0.001, price=buy_price, order_type='limit')
        print(f"Order Result: {order}")

        # 4. Get Open Orders
        open_orders = await extended.get_open_orders(symbol)
        print(f"Open Orders: {open_orders}")

        # 5. Cancel Orders
        if open_orders:
            print(f"Cancelling orders...")
            res = await extended.cancel_orders(symbol, open_orders)
            print(f"Cancel Result: {res}")

        # 6. Get Position
        pos = await extended.get_position(symbol)
        print(f"Position: {pos}")

    except Exception as e:
        print(f"Test failed with error: {e}")
    finally:
        await extended.close()

if __name__ == "__main__":
    asyncio.run(main())
