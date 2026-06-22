import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
POSITIONS_PATH = BASE_DIR / "positions.json"
SNAPSHOTS_DIR = BASE_DIR / "snapshots"
DB_PATH = BASE_DIR / "bloom_terminal.db"

RISK_FREE_RATE = 0.045
MAX_CONTEXT_HISTORY = 512
IV_LOOKBACK_DAYS = 252
IV_MIN_HISTORY = 20
CONCENTRATION_TICKER_CAP = 0.40
CONCENTRATION_SECTOR_CAP = 0.60
DTE_WARN_THRESHOLD = 45
IV_RICH_THRESHOLD = 70
IV_CHEAP_THRESHOLD = 30
NEW_STRIKE_BAND = 0.30
TARGET_NEAR_PCT = 0.80
IV_CHANGE_PCT = 0.20

NEWS_LOOKBACK_DAYS = 3
OPENCODE_NEWS_MODEL = "opencode/north-mini-code-free"

MACRO_WEIGHTS = {
    "vix_level": 0.25,
    "vix_percentile": 0.20,
    "vix_term": 0.20,
    "breadth": 0.20,
    "credit": 0.15,
}

TELEGRAM_ENABLED = False
TELEGRAM_BOT_TOKEN = os.environ.get("BLOOM_TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("BLOOM_TELEGRAM_CHAT_ID", "")
IMESSAGE_ENABLED = False
IMESSAGE_RECIPIENT = os.environ.get("BLOOM_IMESSAGE_TO", "")

SECTOR_MAP = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "NVDA": "Technology",
    "AMD": "Technology",
    "TSLA": "Consumer Cyclical",
    "AMZN": "Consumer Cyclical",
    "GOOGL": "Communication",
    "META": "Communication",
    "JPM": "Financial",
    "GS": "Financial",
    "XOM": "Energy",
    "CVX": "Energy",
    "JNJ": "Healthcare",
    "PFE": "Healthcare",
    "SPY": "ETF",
    "QQQ": "ETF",
    "IWM": "ETF",
    "TLT": "Fixed Income",
    "HYG": "Fixed Income",
}


def load_positions():
    with open(POSITIONS_PATH) as f:
        return json.load(f)


def get_sector(ticker):
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        return info.get("sector", "Unknown")
    except Exception:
        return SECTOR_MAP.get(ticker.upper(), "Unknown")


def load_config():
    return {
        "risk_free_rate": RISK_FREE_RATE,
        "iv_lookback_days": IV_LOOKBACK_DAYS,
        "iv_min_history": IV_MIN_HISTORY,
        "concentration_ticker_cap": CONCENTRATION_TICKER_CAP,
        "concentration_sector_cap": CONCENTRATION_SECTOR_CAP,
        "dte_warn_threshold": DTE_WARN_THRESHOLD,
        "iv_rich_threshold": IV_RICH_THRESHOLD,
        "iv_cheap_threshold": IV_CHEAP_THRESHOLD,
        "new_strike_band": NEW_STRIKE_BAND,
        "target_near_pct": TARGET_NEAR_PCT,
        "iv_change_pct": IV_CHANGE_PCT,
        "news_lookback_days": NEWS_LOOKBACK_DAYS,
    }
