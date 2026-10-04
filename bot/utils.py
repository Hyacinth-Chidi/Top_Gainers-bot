"""
Shared helpers for formatting and safely sending Telegram messages
"""

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter
import asyncio

# Characters with special meaning in Telegram's legacy Markdown
_MD_SPECIAL = ('_', '*', '`', '[')


def escape_md(text) -> str:
    """Escape user/exchange-provided text for legacy Markdown (outside entities only)"""
    text = str(text)
    for ch in _MD_SPECIAL:
        text = text.replace(ch, f"\\{ch}")
    return text


def md_bold(text) -> str:
    """
    Bold text safely. Legacy Markdown can't escape inside an entity,
    so text containing special characters is escaped and left unbolded.
    """
    text = str(text)
    if any(ch in text for ch in _MD_SPECIAL):
        return escape_md(text)
    return f"*{text}*"


def format_price(price: float) -> str:
    """Format a price with precision that suits its magnitude"""
    price = price or 0
    if price >= 1000:
        return f"${price:,.2f}"
    if price >= 1:
        return f"${price:.4f}"
    if price >= 0.01:
        return f"${price:.5f}"
    if price > 0:
        return f"${price:.8f}"
    return "$0"


def format_volume(volume: float) -> str:
    """Format a USD volume as K/M/B"""
    volume = volume or 0
    if volume >= 1_000_000_000:
        return f"${volume/1_000_000_000:.2f}B"
    if volume >= 1_000_000:
        return f"${volume/1_000_000:.2f}M"
    return f"${volume/1_000:.2f}K"


class SendResult:
    OK = "ok"
    BLOCKED = "blocked"   # User blocked the bot / chat no longer exists
    FAILED = "failed"


async def safe_send(bot: Bot, chat_id: int, text: str, **kwargs) -> str:
    """
    Send a Markdown message, handling the common failure modes:
    - Markdown parse errors -> resend as plain text
    - Flood control -> wait and retry once
    - Blocked bot / deleted chat -> report BLOCKED so callers can stop sending
    """
    kwargs.setdefault('parse_mode', ParseMode.MARKDOWN)
    kwargs.setdefault('disable_web_page_preview', True)

    for attempt in range(2):
        try:
            await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            return SendResult.OK
        except RetryAfter as e:
            if attempt == 0:
                await asyncio.sleep(float(e.retry_after) + 1)
                continue
            return SendResult.FAILED
        except Forbidden:
            return SendResult.BLOCKED
        except BadRequest as e:
            msg = str(e).lower()
            if "chat not found" in msg:
                return SendResult.BLOCKED
            if "parse entities" in msg and kwargs.get('parse_mode'):
                # Formatting broke - fall back to plain text
                kwargs['parse_mode'] = None
                continue
            print(f"Failed to send to {chat_id}: {e}")
            return SendResult.FAILED
        except Exception as e:
            print(f"Failed to send to {chat_id}: {e}")
            return SendResult.FAILED
    return SendResult.FAILED
