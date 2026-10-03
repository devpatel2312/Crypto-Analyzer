"""Central configuration for the BTC/ETH crypto derivatives analyzer."""
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

IST = ZoneInfo("Asia/Kolkata")
DERIBIT_URL = os.getenv("DERIBIT_URL", "https://www.deribit.com/api/v2")
QUICKNODE_BTC_URL = os.getenv("QUICKNODE_BTC_URL", "")
QUICKNODE_ETH_URL = os.getenv("QUICKNODE_ETH_URL", "")
CRYPTO_RISK_FREE = float(os.getenv("CRYPTO_RISK_FREE", "0.0"))
DB_PATH = os.getenv("DB_PATH", "data/cache.db")

ASSETS = {
    "BTC": dict(label="Bitcoin", exchange="CRYPTO", kind="crypto", underlying="BTC", step=1000),
    "ETH": dict(label="Ethereum", exchange="CRYPTO", kind="crypto", underlying="ETH", step=50),
}

SESSIONS = {"CRYPTO": (None, None)}
MAX_DEPTH = 20
LIVE_TTL = 3
