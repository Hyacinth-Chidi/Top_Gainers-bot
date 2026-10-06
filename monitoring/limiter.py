from collections import deque
from datetime import datetime, timedelta
from typing import Deque, Dict, List, Optional, Tuple

# Time-critical alerts and slower, informational ones have separate
# allowances, so a burst of daily-gainer alerts can't crowd out a pump.
FAST = "fast"   # pumps, dumps, early signals, DEX
SLOW = "slow"   # daily gainers / losers
DEFAULT_CAPS = {FAST: 10, SLOW: 3}


class AlertLimiter:
    """
    Caps how many alerts each user gets per hour, per kind (FAST / SLOW).

    Alerts over the cap aren't lost: their headlines are collected and sent
    as a single summary message (a "digest") a little later.
    """

    def __init__(self, caps: Optional[Dict[str, int]] = None,
                 digest_delay: timedelta = timedelta(minutes=15), digest_max_lines: int = 15):
        self.caps = dict(caps or DEFAULT_CAPS)
        self.digest_delay = digest_delay
        self.digest_max_lines = digest_max_lines
        self._sent: Dict[Tuple[int, str], Deque[datetime]] = {}
        self._pending: Dict[int, List[str]] = {}
        self._pending_since: Dict[int, datetime] = {}

    def _recent(self, user_id: int, kind: str, now: datetime) -> Deque[datetime]:
        """Send times in the last hour (older ones are dropped)"""
        log = self._sent.setdefault((user_id, kind), deque())
        cutoff = now - timedelta(hours=1)
        while log and log[0] <= cutoff:
            log.popleft()
        return log

    def allow(self, user_id: int, now: datetime, kind: str = FAST) -> bool:
        """Is this user still under their hourly cap for this kind of alert?"""
        return len(self._recent(user_id, kind, now)) < self.caps.get(kind, self.caps[FAST])

    def record(self, user_id: int, now: datetime, kind: str = FAST):
        self._recent(user_id, kind, now).append(now)

    def defer(self, user_id: int, headline: str, now: datetime):
        """Keep an alert's headline for the user's next digest"""
        self._pending.setdefault(user_id, []).append(headline)
        self._pending_since.setdefault(user_id, now)

    def due_digests(self, now: datetime) -> List[Tuple[int, List[str]]]:
        """Digests that have waited long enough; removes them from the queue"""
        due = []
        for user_id, since in list(self._pending_since.items()):
            if now - since >= self.digest_delay:
                due.append((user_id, self._pending.pop(user_id, [])))
                del self._pending_since[user_id]
        return due

    def forget(self, user_id: int):
        """Drop all state for a user (e.g. they blocked the bot)"""
        for key in [k for k in self._sent if k[0] == user_id]:
            del self._sent[key]
        self._pending.pop(user_id, None)
        self._pending_since.pop(user_id, None)

    def reset(self):
        self._sent.clear()
        self._pending.clear()
        self._pending_since.clear()


# Shared by the CEX and DEX trackers so the cap covers all alerts a user gets
DEFAULT_LIMITER = AlertLimiter()
