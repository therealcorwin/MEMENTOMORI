"""
Service de notifications proactives Telegram pour l'administrateur (§16.12, Task 6.7).
Envoie des alertes critiques et alertes de maintenance (ingestion, backups, dépassement de coût).
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Optional
import httpx

from knowledge.logging import get_logger

logger = get_logger(__name__)


class AlertLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


LEVEL_ICONS = {
    AlertLevel.INFO: "[INFO]",
    AlertLevel.WARNING: "[ATTENTION]",
    AlertLevel.CRITICAL: "[CRITIQUE]",
}


async def send_admin_alert(
    level: AlertLevel | str,
    title: str,
    message: str,
    context: Optional[dict[str, Any]] = None,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> bool:
    """Envoie une notification d'alerte Telegram formatée à l'administrateur."""
    if isinstance(level, str):
        try:
            level = AlertLevel(level.upper())
        except ValueError:
            level = AlertLevel.INFO

    icon = LEVEL_ICONS.get(level, "ℹ️")
    token = bot_token or os.getenv("BOT_TOKEN")
    target_chat = chat_id or os.getenv("ADMIN_CHAT_ID") or os.getenv("COPRO_CHAT_ID")

    context_str = ""
    if context:
        lines = [f"• <b>{k}</b>: <code>{v}</code>" for k, v in context.items()]
        context_str = "\n\n<b>Détails techniques :</b>\n" + "\n".join(lines)

    formatted_text = (
        f"{icon} <b>[ALERTE MEMENTOMORI — {level.value}]</b>\n\n"
        f"<b>{title}</b>\n"
        f"{message}"
        f"{context_str}"
    )

    logger.info("admin_alert_prepared", level=level.value, title=title)

    if not token or not target_chat:
        logger.warning(
            "telegram_token_or_chat_id_missing_simulated_alert",
            level=level.value,
            title=title,
            preview=formatted_text[:120]
        )
        return True  # Mode simulation réussi en dev sans token

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": formatted_text,
        "parse_mode": "HTML"
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                logger.info("telegram_admin_alert_sent_successfully", title=title)
                return True
            else:
                logger.error("telegram_api_error", status=resp.status_code, body=resp.text)
                return False
    except Exception as e:
        logger.error("telegram_alert_network_failed", error=str(e))
        return False
