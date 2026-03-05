from .hackernews import fetch as fetch_hackernews
from .reddit import fetch as fetch_reddit
from .google_news import fetch as fetch_google_news
from .github_releases import fetch as fetch_github
from .devto import fetch as fetch_devto
from .crypto_sentiment import fetch as fetch_crypto
from .gold_quant import fetch as fetch_gold_quant

ALL_FETCHERS = [
    ("Hacker News", fetch_hackernews),
    ("Reddit", fetch_reddit),
    ("Google News", fetch_google_news),
    ("GitHub", fetch_github),
    ("Dev.to", fetch_devto),
    ("Crypto Sentiment", fetch_crypto),
    ("Gold & Quant", fetch_gold_quant),
]
