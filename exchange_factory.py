import importlib  # [ADDED]

def _load(exchange_platform: str):  # [ADDED] 필요한 경우에만 모듈 로드
    mapping = {
        "grvt": ("wrappers.grvt", "GrvtExchange"),
        "backpack": ("wrappers.backpack", "BackpackExchange"),
        "variational": ("wrappers.variational", "VariationalExchange"),
        "pacifica": ("wrappers.pacifica", "PacificaExchange"),
        "extended": ("wrappers.extended", "ExtendedExchange"),
        "lighter": ("wrappers.lighter", "LighterExchange"),
    }
    try:
        mod, cls = mapping[exchange_platform]
    except KeyError:
        raise ValueError(f"Unsupported exchange: {exchange_platform}")
    module = importlib.import_module(mod)
    return getattr(module, cls)

async def create_exchange(exchange_platform: str, key_params=None):  # [MODIFIED] 지연 로드 사용
    if key_params is None:
        raise ValueError(f"[ERROR] key_params is required for exchange: {exchange_platform}")
    Ex = _load(exchange_platform)  # [ADDED]
    
    if exchange_platform == "grvt":
        return await Ex(
            key_params.api_key, 
            key_params.account_id, 
            key_params.secret_key
            ).init()
    
    elif exchange_platform == "backpack":
        return await Ex(
            key_params.api_key, 
            key_params.secret_key
            ).init()
    
    elif exchange_platform == "variational":
        return await Ex(
            key_params.evm_wallet_address, 
            key_params.session_cookies, 
            key_params.evm_private_key
            ).init()
    
    elif exchange_platform == "pacifica":
        return await Ex(
            key_params.public_key, 
            key_params.agent_public_key, 
            key_params.agent_private_key
            ).init()
    
    elif exchange_platform == "extended":
        return await Ex(
            key_params.account_id, 
            key_params.private_key
            ).init()
    
    elif exchange_platform == "lighter":
        return await Ex(
            key_params.account_id, 
            key_params.private_key,
            key_params.api_key_id,
            key_params.l1_address
            ).init()

    else:
        raise ValueError(f"Unsupported exchange: {exchange_platform}")

SYMBOL_FORMATS = {
    "grvt":     lambda c, q=None: f"{c}_USDT_Perp",
    "backpack": lambda c, q=None: f"{c}_USDC_PERP",
    "variational": lambda coin, q=None: coin.upper(),
    "pacifica": lambda coin, q=None: coin.upper(),
    "extended": lambda c, q=None: f"{c}USDT",
    "lighter": lambda coin, q=None: coin.upper(),
}

SPOT_SYMBOL_FORMATS = {
    "backpack": lambda c: f"{c[0]}_{c[1]}", # BTC_USDC 형태
}

def symbol_create(exchange_platform: str, coin: str, *, is_spot=False, quote=None):
    """spot의 경우 BTC/USDC와 같은 형태, quote가 있음"""
    """perp의 경우 BTC의 형태, dex가 붙으면 xyz:XYZ100 형태, quote가 없음"""
    
    if is_spot:
        # 총 3케이스를 다룸 "/", "_", "-"
        splitters = ['/','_','-']
        for spliter in splitters:
            if spliter in coin:
                base_symbol = coin.split(spliter)[0].upper()
                quote = coin.split(spliter)[1].upper()
                #print(base_symbol,quote)
                break
        try:
            return SPOT_SYMBOL_FORMATS[exchange_platform]([base_symbol,quote])
        except KeyError:
            raise ValueError(f"Unsupported exchange: {exchange_platform}, coin: {coin}")
    else:
        # perp가 default
        coin = coin.upper()
        try:
            return SYMBOL_FORMATS[exchange_platform](coin, quote)
        except KeyError:
            raise ValueError(f"Unsupported exchange: {exchange_platform}, coin: {coin}")