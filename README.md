# Multi-Exchange Volume & Hedge Bot

이 저장소는 여러 Perp DEX(Backpack, GRVT, Pacifica, Extended 등)간의 거래량 작업(Volume Generating) 및 포지션 헤징(Hedging)을 자동화하기 위한 봇 시스템입니다.

---

## 주요 기능

1. **볼륨 봇 (`volume_bot.py`)**  
   - 지정된 거래소(Backpack, Pacifica, Extended 등)에서 주기적으로 지정가 주문(Post-Only)을 생성하여 거래량을 발생시킵니다.
   - **순수 델타 헤징**: 타겟 거래소에서 포지션이 체결되는 즉시 Variational DEX에 동일 수량의 반대 포지션을 잡아 리스크를 헤지합니다.
   - **실시간 감시 및 청산 대응**: 사이클 유지 시간(기본 2분) 동안 1초마다 포지션을 감시하여, 청산이나 수동 종료 시 헤징 포지션을 즉시 정리합니다.

2. **멀티 헤지 봇 (`multi_hedge_bot.py`)**  
   - 여러 거래소(GRVT, Backpack, Extended, Pacifica 등)를 동시에 감시합니다.
   - 어떤 거래소에서든 포지션 변화(Delta)가 감지되면 Variational DEX에 즉시 대응 주문을 넣어 전체 포트폴리오의 델타를 중립으로 유지합니다.
   - 복잡한 잔고 동기화 없이 오직 '실시간 변화량'에만 기계적으로 반응하여 충돌을 방지합니다.

---

## 지원 거래소 및 래퍼 (`wrappers/`)

- **Backpack**: 공식 API 지원 및 실시간 포지션 추적 지연 보정 로직 포함.
- **GRVT**: `grvt-pysdk` 기반 통합.
- **Extended**: Edgex 기반의 새로운 인터페이스.
- **Pacifica**: 신규 DEX 지원.
- **Variational**: 헤징 전용 래퍼.
- **Lighter**: `lighter-sdk` 통합.

---

## 요구 사항

- Python 3.10 이상 권장
- macOS / Linux (Windows는 fastecdsa 등의 라이브러리 설치가 까다로울 수 있음)
- `requirements.txt`에 명시된 의존성 패키지들

---

## 설치 및 시작

### 1. 가상환경 및 의존성 설치
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 키 설정 (`keys/`)
`keys/pk_*.py` 파일들을 작성하여 API 키와 개인키를 설정합니다. 아래 파일들이 필수적입니다:
- `pk_backpack.py`
- `pk_grvt.py`
- `pk_extended.py`
- `pk_pacifica.py`
- `pk_variational.py`

### 3. 봇 실행

**볼륨 봇 실행:**
```bash
python volume_bot.py
```
*(파일 상단의 `TARGET_EXCHANGE`, `AMOUNT` 등을 수정하여 설정 변경 가능)*

**멀티 헤지 봇 실행:**
```bash
python multi_hedge_bot.py
```

---

## 보안 주의

- `keys/` 폴더 내의 파일들은 암호화되지 않은 개인키를 포함하므로 절대 외부에 노출되거나 Git에 커밋되지 않도록 주의하십시오.
- `.gitignore`에 `keys/*.py` (템플릿 제외)가 포함되어 있는지 확인하십시오.

---

## 라이선스

MIT