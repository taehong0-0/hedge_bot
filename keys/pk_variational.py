from dataclasses import dataclass

@dataclass
class VariationalKEY:
    evm_wallet_address: str
    session_cookies: dict
    evm_private_key: str
    
VARIATIONAL_KEY = VariationalKEY(
    evm_wallet_address = '', # required, your evm address
    session_cookies = {"vr_token":""},  # aplication 탭 까보면 있음.
    )
