import asyncio
import logging
import os
import certifi
from decimal import Decimal

# macOS SSL Certificate Fix
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

from exchange_factory import create_exchange, symbol_create

# ==========================================
# 설정 변수 (Configuration)
# ==========================================
MONITOR_EXCHANGES = ["grvt", "backpack", "extended", "pacifica"] # 감시할 모든 거래소
HEDGE_EXCHANGE = "variational"            # 헤징을 수행할 단일 거래소
COIN = "BTC"                              # 매매 코인
SYNC_INTERVAL = 1                         # 감시 주기 (초)
HEDGE_RATIO = 1.0                         # 헤징 비율 (1.0 = 100% 헤징)
# ==========================================

# 키 로드
KEYS = {}
try: from keys.pk_grvt import GRVT_KEY; KEYS["grvt"] = GRVT_KEY
except ImportError: pass
try: from keys.pk_backpack import BACKPACK_KEY; KEYS["backpack"] = BACKPACK_KEY
except ImportError: pass
try: from keys.pk_extended import EXTENDED_KEY; KEYS["extended"] = EXTENDED_KEY
except ImportError: pass
try: from keys.pk_pacifica import PACIFICA_KEY; KEYS["pacifica"] = PACIFICA_KEY
except ImportError: pass
try: from keys.pk_variational import VARIATIONAL_KEY; KEYS["variational"] = VARIATIONAL_KEY
except ImportError: pass
try: from keys.pk_lighter import LIGHTER_KEY; KEYS["lighter"] = LIGHTER_KEY
except ImportError: pass

# Logging setup
logger = logging.getLogger("multi_hedge_bot")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

class MultiHedgeBot:
    def __init__(self, monitor_names=MONITOR_EXCHANGES, hedge_name=HEDGE_EXCHANGE, coin=COIN):
        self.monitor_names = monitor_names
        self.hedge_name = hedge_name
        self.coin = coin
        
        self.monitor_exs = {} # name -> exchange_instance
        self.hedge_ex = None
        self.monitor_symbols = {} # name -> symbol
        self.hedge_symbol = None
        
        self.last_positions = {} # name -> last_known_signed_size
        self.running = True

    async def init_exchanges(self):
        logger.info(f"거래소 초기화 중... [감시: {self.monitor_names}] -> [헤징: {self.hedge_name}]")
        
        for name in self.monitor_names:
            if name not in KEYS:
                raise ValueError(f"감시 거래소 '{name}'의 키 파일이 keys/ 폴더에 없습니다.")
            ex = await create_exchange(name, KEYS[name])
            self.monitor_exs[name] = ex
            self.monitor_symbols[name] = symbol_create(name, self.coin)
            
            # 현재 포지션 기록 (이 시점부터의 변화만 쫓음)
            pos = await ex.get_position(self.monitor_symbols[name])
            self.last_positions[name] = self._get_signed_size(pos)
            logger.info(f"[{name}] 기준 포지션 기록: {self.last_positions[name]}")

        if self.hedge_name not in KEYS:
            raise ValueError(f"헤징 거래소 '{self.hedge_name}'의 키 파일이 keys/ 폴더에 없습니다.")
        self.hedge_ex = await create_exchange(self.hedge_name, KEYS[self.hedge_name])
        self.hedge_symbol = symbol_create(self.hedge_name, self.coin)

        logger.info("모든 거래소 초기화 완료.")

    def _get_signed_size(self, pos):
        if not pos: return Decimal(0)
        size = Decimal(str(pos['size']))
        side = pos['side'].lower()
        return size if side in ['long', 'buy'] else -size

    async def sync_positions(self):
        try:
            for name, ex in self.monitor_exs.items():
                curr_pos = await ex.get_position(self.monitor_symbols[name])
                curr_signed = self._get_signed_size(curr_pos)
                
                delta = curr_signed - self.last_positions.get(name, Decimal(0))
                
                if abs(delta) < Decimal("0.0000001"):
                    continue

                logger.info(f"[{name}] 변화 감지: {delta} (현재: {curr_signed})")
                
                # 즉시 헤징 주문 (Variational 잔고 상관없이 변화량만큼만 주문)
                side = "sell" if delta > 0 else "buy"
                amount = float(abs(delta) * Decimal(str(HEDGE_RATIO)))
                
                logger.info(f"[{self.hedge_name}] 대응 주문 실행: {side} {amount}")
                try:
                    await self.hedge_ex.create_order(self.hedge_symbol, side, amount, order_type="market")
                    logger.info(f"[{self.hedge_name}] 대응 주문 완료.")
                    # 기준점 업데이트
                    self.last_positions[name] = curr_signed
                except Exception as e:
                    logger.error(f"[{self.hedge_name}] 대응 주문 실패: {e}")
            
        except Exception as e:
            logger.error(f"[에러] 포지션 추적 중 오류: {e}")

    async def start(self):
        try:
            await self.init_exchanges()
            logger.info(f"범용 헤징 봇 가동 시작 (주기: {SYNC_INTERVAL}초)")
            while self.running:
                await self.sync_positions()
                await asyncio.sleep(SYNC_INTERVAL)
        except Exception as e:
            logger.error(f"[치명적 에러] {e}")
        finally:
            for ex in self.monitor_exs.values(): await ex.close()
            if self.hedge_ex: await self.hedge_ex.close()

if __name__ == "__main__":
    bot = MultiHedgeBot()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("사용자에 의해 중단됨.")
