from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openrouter_api_key: str = ""
    resend_api_key: str = ""
    newsletter_to: str = ""
    newsletter_from: str = "newsletter@pulsetrade.io"
    site_url: str = "https://ai-newsletter.pages.dev"
    github_token: str = ""
    data_dir: str = "data"
    site_dir: str = "site"
    dry_run: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
