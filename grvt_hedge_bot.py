import asyncio
import logging
import time
import os
import json
import ssl
import certifi
from datetime import datetime
from decimal import Decimal

# macOS SSL Certificate Fix
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

from exchange_factory import create_exchange, symbol_create
from keys.pk_grvt import GRVT_KEY
from keys.pk_variational import VARIATIONAL_KEY

# Logging setup
logger = logging.getLogger("grvt_hedge_bot")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

# ==========================================
# 설정 변수 (Configuration)
# ==========================================
COIN = "BTC"                  # 감시할 코인
SYNC_INTERVAL = 1             # 동기화 간격 (초)
HEDGE_RATIO = 1.0             # 헤징 비율 (GRVT : Variational)
# ==========================================

class GrvtHedgeBot:
    def __init__(self, coin=COIN):
        self.coin = coin
        self.grvt_ex = None
        self.variational_ex = None
        self.grvt_symbol = None
        self.variational_symbol = None
        
        self.initial_grvt_signed_size = None  # 시작 시점의 포지션 기준점
        self.last_sync_time = 0

    async def init_exchanges(self):
        logger.info("거래소(GRVT, Variational) 초기화 중...")
        self.grvt_ex = await create_exchange("grvt", GRVT_KEY)
        self.variational_ex = await create_exchange("variational", VARIATIONAL_KEY)
        
        self.grvt_symbol = symbol_create("grvt", self.coin)
        self.variational_symbol = symbol_create("variational", self.coin)
        
        logger.info(f"GRVT 심볼: {self.grvt_symbol}")
        logger.info(f"Variational 심볼: {self.variational_symbol}")
        
        # 시작 시점의 기준 포지션 획득
        init_pos = await self.grvt_ex.get_position(self.grvt_symbol)
        init_size = self._to_decimal(init_pos['size']) if init_pos else Decimal(0)
        init_side = init_pos['side'].lower() if init_pos else "없음"
        self.last_grvt_signed_size = init_size if init_side == "long" else (-init_size if init_side == "short" else Decimal(0))
        
        logger.info(f"[기준 설정] 감시 시작 GRVT 포지션: {self.last_grvt_signed_size} ({init_side})")
        logger.info("거래소 초기화 완료.")

    def _to_decimal(self, n):
        if n is None: return Decimal(0)
        return Decimal(str(n))

    async def sync_positions(self):
        try:
            # 1. GRVT 현재 포지션 확인
            grvt_pos = await self.grvt_ex.get_position(self.grvt_symbol)
            if grvt_pos is None and self.last_grvt_signed_size == Decimal(0):
                return

            current_grvt_size = self._to_decimal(grvt_pos['size']) if grvt_pos else Decimal(0)
            current_grvt_side = grvt_pos['side'].lower() if grvt_pos else "없음"
            current_grvt_signed_size = current_grvt_size if current_grvt_side == "long" else (-current_grvt_size if current_grvt_side == "short" else Decimal(0))
            
            # 2. 변화량(Delta) 계산
            delta = current_grvt_signed_size - self.last_grvt_signed_size
            
            if abs(delta) < Decimal("0.00001"):
                return

            logger.info(f"[감시] GRVT 변화 감지: {self.last_grvt_signed_size} -> {current_grvt_signed_size} (차이: {delta})")
            
            # 3. 변화량만큼만 Variational에 주문 실행 (동기화가 아닌 '대응 주문')
            # GRVT가 +0.002(매수) 되면 Variational은 -0.002(매도) 주문
            side = "sell" if delta > 0 else "buy"
            amount = abs(delta) * Decimal(str(HEDGE_RATIO))
            
            logger.info(f"[Variational] 대응 주문 실행: {side} {amount}")
            await self.variational_ex.create_order(self.variational_symbol, side, float(amount), order_type="market")
            logger.info("[Variational] 대응 주문 체결 완료.")
            
            # 기준점 업데이트
            self.last_grvt_signed_size = current_grvt_signed_size
            
        except Exception as e:
            logger.error(f"[에러] 변화량 처리 중 오류 발생: {e}")

    async def start(self):
        await self.init_exchanges()
        logger.info(f"봇 가동 시작 (감시 주기: {SYNC_INTERVAL}초)")
        while True:
            await self.sync_positions()
            await asyncio.sleep(SYNC_INTERVAL)

if __name__ == "__main__":
    bot = GrvtHedgeBot(COIN)
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
