from .hackernews import fetch as fetch_hackernews
from .reddit import fetch as fetch_reddit
from .google_news import fetch as fetch_google_news
from .github_releases import fetch as fetch_github
from .devto import fetch as fetch_devto
from .crypto_sentiment import fetch as fetch_crypto_news
from .gold_quant import fetch as fetch_gold_quant
from .ai_startups import fetch as fetch_ai_startups
from .ai_realestate import fetch as fetch_ai_realestate
from .binance_direct import fetch as fetch_binance
from .btc_guru import fetch as fetch_btc_guru
from .pulse_trader_db import fetch as fetch_pulse_trader
from .world_news import fetch as fetch_world_news

ALL_FETCHERS = [
    ("Hacker News", fetch_hackernews),
    ("Reddit", fetch_reddit),
    ("Google News", fetch_google_news),
    ("GitHub", fetch_github),
    ("Dev.to", fetch_devto),
    ("Binance Direct", fetch_binance),
    ("BTC Guru", fetch_btc_guru),
    ("Pulse Trader", fetch_pulse_trader),
    ("Crypto News", fetch_crypto_news),
    ("Gold & Quant", fetch_gold_quant),
    ("AI Startups", fetch_ai_startups),
    ("AI Real Estate", fetch_ai_realestate),
    ("World News", fetch_world_news),
]
