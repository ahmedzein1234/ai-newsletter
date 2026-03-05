"""Send newsletter email via Resend API."""
from __future__ import annotations

import logging

import httpx

from .config import settings

log = logging.getLogger(__name__)


async def send_email(subject: str, html_body: str) -> bool:
    if not settings.resend_api_key:
        log.warning("RESEND_API_KEY not set, skipping email")
        return False

    recipients = [r.strip() for r in settings.newsletter_to.split(",") if r.strip()]
    if not recipients:
        log.warning("NEWSLETTER_TO not set, skipping email")
        return False

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.newsletter_from,
                "to": recipients,
                "subject": subject,
                "html": html_body,
            },
            timeout=15,
        )

    if resp.status_code in (200, 201):
        log.info("Email sent to %s", recipients)
        return True

    log.error("Resend API %d: %s", resp.status_code, resp.text[:300])
    return False
