from multi_perp_dex import MultiPerpDex, MultiPerpDexMixin
import logging
import json
import asyncio
import aiohttp
import websockets
import time
import os

logger = logging.getLogger(__name__)

class LighterExchange(MultiPerpDexMixin, MultiPerpDex):
    def __init__(self, account_id, private_key, api_key_id, l1_address):
        super().__init__()
        self.account_index = int(account_id)
        self.api_key_id = int(api_key_id)
        self.private_key = private_key
        self.l1_address = l1_address
        
        self.base_url = "https://api.lighter.xyz"
        self.ws_url = "wss://api.lighter.xyz/v1/ws"
        
        self.client = None
        self.client_order_index = int(time.time() * 1000) % 2**31
        self.session = None
        
    async def init(self):
        import lighter
        from lighter import SignerClient
        
        pk = self.private_key
        if not pk.startswith("0x"): pk = "0x" + pk
        
        api_private_keys = {self.api_key_id: pk}
        
        try:
            self.client = SignerClient(
                url=self.base_url,
                account_index=self.account_index,
                api_private_keys=api_private_keys,
                nonce_management_type=lighter.NonceManagerType.OPTIMISTIC
            )
            logger.info("Lighter SDK SignerClient initialized.")
        except Exception as e:
            logger.error(f"Lighter SDK Init Failed: {e}")
            raise
            
        return self

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _run_sync(self, func, *args, **kwargs):
        return await asyncio.get_event_loop().run_in_executor(None, lambda: func(*args, **kwargs))

    async def create_order(self, symbol, side, amount, price=None, order_type='market'):
        import lighter
        is_ask = (side.lower() == 'sell')
        market_index = 1 if 'BTC' in symbol.upper() else 0 # 1 = WBTC-USDC
        self.client_order_index += 1
        
        if price is None:
            # Market Order
            exec_price = 0.1 if is_ask else 200000.0 # Slippage protection
            result = await self._run_sync(
                self.client.create_market_order,
                market_index=market_index,
                client_order_index=self.client_order_index,
                base_amount=float(amount),
                avg_execution_price=float(exec_price),
                is_ask=is_ask
            )
        else:
            # Limit Order
            tif = lighter.ORDER_TIME_IN_FORCE_GOOD_TILL_TIME
            result = await self._run_sync(
                self.client.create_order,
                market_index=market_index,
                client_order_index=self.client_order_index,
                base_amount=float(amount),
                price=float(price),
                is_ask=is_ask,
                order_type=lighter.ORDER_TYPE_LIMIT,
                time_in_force=tif
            )
            
        if isinstance(result, tuple) and len(result) >= 3 and result[2] is None:
            return {"id": str(self.client_order_index), "status": "New"}
        else:
            logger.error(f"Lighter Order Fail: {result}")
            return None

    async def get_position(self, symbol):
        # Lighter는 SDK를 통해 계정 정보를 조회해야 합니다. (app.get_account)
        # 하지만 API를 직접 호출하는 방식이 더 확실할 수 있습니다.
        session = await self._get_session()
        url = f"{self.base_url}/v1/accounts/{self.account_index}"
        
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # data['balances'] 에서 해당 마켓의 포지션 확인 (WBTC 등)
                    # Lighter는 Spot-like Orderbook이므로 balance가 곧 포지션입니다.
                    # 하지만 이 봇은 Perpetual 처럼 사용하므로, 
                    # 기준 balance 대비 변화량을 포지션으로 간주하거나, 별도의 관리가 필요할 수 있습니다.
                    # 현재는 balance 정보를 반환합니다.
                    balances = data.get('balances', [])
                    market_index = 1 if 'BTC' in symbol.upper() else 0
                    
                    for b in balances:
                        if b.get('market_index') == market_index:
                            # market_index 1 이면 WBTC-USDC 마켓.
                            # b['base_amount'] 가 코인 수량입니다.
                            # Perpetual 봇으로 활용 시, '포지션'의 개념을 balance로 대체.
                            size = float(b.get('base_amount', 0))
                            # Lighter는 현물 기반이므로 side는 항상 long으로 처리될 수 있음.
                            # (차액 거래 봇에서는 이를 상대 수량으로 계산)
                            return {"size": size, "side": "long", "entry_price": 0}
                return None
        except Exception as e:
            logger.error(f"Lighter get_position failed: {e}")
            return None

    async def get_collateral(self):
        session = await self._get_session()
        url = f"{self.base_url}/v1/accounts/{self.account_index}"
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    balances = data.get('balances', [])
                    # USDC(quote) balance를 담보로 간주
                    for b in balances:
                        if b.get('market_index') == 0: # 마켓 0의 quote 또는 마켓 1의 quote
                            pass
                    # 임시로 첫 번째 balance의 가용 수량 반환
                    total = sum(float(b.get('quote_amount', 0)) for b in balances)
                    return {"available_collateral": total, "total_collateral": total}
        except:
            pass
        return {"available_collateral": 0, "total_collateral": 0}

    async def get_open_orders(self, symbol):
        # Lighter SDK or REST API to list orders
        return []

    async def cancel_orders(self, symbol, open_orders=None):
        return True

    async def get_mark_price(self, symbol):
        return 0.0

    async def close(self):
        if self.session:
            await self.session.close()
