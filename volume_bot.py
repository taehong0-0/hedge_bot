import asyncio
import logging
import os
import json
import certifi
from datetime import datetime
from decimal import Decimal

# macOS SSL Certificate Fix
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

from exchange_factory import create_exchange, symbol_create
from keys.pk_backpack import BACKPACK_KEY
from keys.pk_pacifica import PACIFICA_KEY
from keys.pk_extended import EDGEX_KEY as EXTENDED_KEY
from keys.pk_variational import VARIATIONAL_KEY

# Logging setup for console
logger = logging.getLogger("volume_bot")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

# ==========================================
# 사용자 설정 변수 (User Configuration)
# ==========================================
TARGET_EXCHANGE = "backpack"  # 대상 거래소: backpack, pacifica, extended
COIN = "BTC"                  # 거래 대상 코인
AMOUNT = 0.002                # 거래 수량 (BTC 단위)
BUY_OFFSET = -0.5             # 매수 시 마크 프라이스 대비 가격
SELL_OFFSET = 0.5             # 매도 시 마크 프라이스 대비 가격

HEDGE_WAIT_TIME = 5         # 사이클 중간 대기 시간 (초)
COOLDOWN_TIME = 5           # 사이클 종료 후 대기 시간 (초)

# 헤징 설정
ENABLE_INTERNAL_HEDGE = True
POST_ONLY = True             # 지정가 주문 시 Post-Only 강제 선택

# 상세 설정
CHECK_INTERVAL = 1.0           # 체결 상태 확인 및 재주문 간격 (초)
# ==========================================

EXCHANGES_CONFIG = {
    "backpack": BACKPACK_KEY,
    "pacifica": PACIFICA_KEY,
    "extended": EXTENDED_KEY,
}

HEDGE_EXCHANGE_NAME = "variational"
HEDGE_CONFIG = VARIATIONAL_KEY

class VolumeBot:
    def __init__(self, target_exchange_name, amount=AMOUNT):
        self.target_name = target_exchange_name
        self.amount = amount
        self.target_ex = None
        self.hedge_ex = None
        self.symbol = None
        self.hedge_symbol = None
        
        self.total_volume = Decimal(0)
        self.trades_count = 0
        self.amount_dec = Decimal(str(amount))
        self.current_day = datetime.now().strftime("%Y-%m-%d")

        # 실시간 변화 추적용
        self.last_pos_for_hedge = Decimal(0)

    async def init_exchanges(self):
        logger.info(f"Initializing exchanges: {self.target_name} and {HEDGE_EXCHANGE_NAME}")
        self.target_ex = await create_exchange(self.target_name, EXCHANGES_CONFIG[self.target_name])
        self.hedge_ex = await create_exchange(HEDGE_EXCHANGE_NAME, HEDGE_CONFIG)
        self.symbol = symbol_create(self.target_name, COIN)
        self.hedge_symbol = symbol_create(HEDGE_EXCHANGE_NAME, COIN)
        
        coll = await self.target_ex.get_collateral()
        self.daily_start_seed = float(coll.get('total_collateral', 0))
        
        # 시작 시점 포지션 기록
        pos = await self.target_ex.get_position(self.symbol)
        self.last_pos_for_hedge = self._get_signed_size(pos)
        
        logger.info(f"Initial Seed: {self.daily_start_seed}")
        logger.info(f"Initial Position: {self.last_pos_for_hedge}")

    async def log_trade(self, last_price, trade_amount):
        if not last_price: return
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        
        if date_str != self.current_day:
            coll = await self.target_ex.get_collateral()
            self.daily_start_seed = float(coll.get('total_collateral', 0))
            self.total_volume = Decimal(0)
            self.trades_count = 0
            self.current_day = date_str

        filename = f"{date_str}.log"
        time_str = now.strftime("%H:%M:%S")
        
        coll = await self.target_ex.get_collateral()
        current_seed = float(coll.get('total_collateral', 0))
        
        volume_delta = Decimal(str(trade_amount)) * Decimal(str(last_price))
        self.total_volume += volume_delta
        
        log_data = {
            "timestamp": time_str,
            "trade_index": self.trades_count,
            "daily_start_seed": self.daily_start_seed,
            "current_seed": current_seed,
            "session_trade_count": self.trades_count,
            "session_total_volume": float(round(self.total_volume, 2)),
            "last_trade_amount": float(trade_amount),
            "last_trade_price": float(last_price)
        }
        
        with open(filename, "a") as f:
            f.write(json.dumps(log_data) + "\n")
        
        logger.info(f"Logged trade: Vol={self.total_volume:.2f}, Seed={current_seed:.2f}")

    async def get_target_price(self):
        try:
            return float(await self.target_ex.get_mark_price(self.symbol))
        except Exception as e:
            logger.error(f"Error getting mark price: {e}")
            return None

    def _get_signed_size(self, pos):
        if not pos: return Decimal(0)
        size = Decimal(str(pos['size']))
        side = pos['side'].lower()
        return size if side in ['long', 'buy'] else -size

    async def sync_hedge(self):
        """
        오직 포지션의 실제 '변화량'만 체크하여 즉시 Variational에 주문을 던집니다.
        """
        curr_pos = await self.target_ex.get_position(self.symbol)
        curr_signed = self._get_signed_size(curr_pos)
        
        delta = curr_signed - self.last_pos_for_hedge
        
        if abs(delta) > Decimal("0.0000001"):
            logger.info(f"[체결감지] {self.target_name} 포지션 변화: {delta} (현재: {curr_signed})")
            if ENABLE_INTERNAL_HEDGE:
                side = "sell" if delta > 0 else "buy"
                amount = abs(delta)
                logger.info(f"[Variational] 델타 헷징 주문: {side} {amount}")
                try:
                    await self.hedge_ex.create_order(self.hedge_symbol, side, float(amount), None, "market")
                    self.trades_count += 1
                    price = await self.get_target_price()
                    await self.log_trade(price, amount)
                except Exception as e:
                    logger.error(f"[에러] Variational 헷징 주문 실패: {e}")
            
            # 주문 성공 여부에 상관없이 현재 포지션을 기준으로 잡아 다음 변화를 쫓음
            self.last_pos_for_hedge = curr_signed
        
        return curr_signed

    async def run_cycle(self):
        logger.info("--- 사이클 가동 ---")
        
        # 현재 포지션을 기준으로 목표 설정
        curr_signed = await self.sync_hedge()
        base_pos = curr_signed
        target_buy = base_pos + self.amount_dec
        
        # 1. 매수 단계 (Phase 1)
        logger.info(f"[매수] 시작 -> 목표: {target_buy}")
        while True:
            curr_signed = await self.sync_hedge()
            
            if curr_signed >= target_buy - Decimal("0.0000001"):
                logger.info("[매수] 목표 달성 완료")
                break
                
            # 기존 주문 취소 후 새로 주문
            await self.target_ex.cancel_orders(self.symbol)
            price = await self.get_target_price()
            if not price:
                await asyncio.sleep(2)
                continue
                
            buy_price = price + BUY_OFFSET
            remaining = float(target_buy - curr_signed)
            
            logger.info(f"[{self.target_name}] 매수 주문 (Post-Only): {buy_price}, 남은수량: {remaining}")
            try:
                await self.target_ex.create_order(
                    self.symbol, "buy", remaining, buy_price, "limit", post_only=POST_ONLY
                )
                await asyncio.sleep(CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"주문 에러: {e}")
                await asyncio.sleep(1)

        # 2. 유지 단계 (Phase 2)
        logger.info(f"[유지] {HEDGE_WAIT_TIME}초 대기...")
        await asyncio.sleep(HEDGE_WAIT_TIME)
        await self.sync_hedge()

        # 3. 매도 단계 (Phase 3)
        logger.info(f"[매도] 시작 -> 목표: {base_pos}")
        while True:
            curr_signed = await self.sync_hedge()
            
            if curr_signed <= base_pos + Decimal("0.0000001"):
                logger.info("[매도] 기준점 복귀 완료")
                break
                
            await self.target_ex.cancel_orders(self.symbol)
            price = await self.get_target_price()
            if not price:
                await asyncio.sleep(2)
                continue
                
            sell_price = price + SELL_OFFSET
            excess = float(curr_signed - base_pos)
            
            logger.info(f"[{self.target_name}] 매도 주문 (Post-Only): {sell_price}, 남은수량: {excess}")
            try:
                await self.target_ex.create_order(
                    self.symbol, "sell", excess, sell_price, "limit", post_only=POST_ONLY
                )
                await asyncio.sleep(CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"주문 에러: {e}")
                await asyncio.sleep(1)

        await self.sync_hedge()
        logger.info(f"사이클 종료. {COOLDOWN_TIME}초 대기...")
        await asyncio.sleep(COOLDOWN_TIME)

    async def start(self):
        await self.init_exchanges()
        while True:
            try:
                await self.run_cycle()
            except Exception as e:
                logger.error(f"Main Loop Error: {e}", exc_info=True)
                await asyncio.sleep(10)

if __name__ == "__main__":
    bot = VolumeBot(TARGET_EXCHANGE, AMOUNT)
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
