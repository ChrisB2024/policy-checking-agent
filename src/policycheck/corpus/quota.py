"""Persistent request budget for the CourtListener API.

CourtListener allows authenticated users 5 requests/minute, 50/hour, and **125/day**
(https://wiki.free.law/c/courtlistener/help/api/rest/v4/overview). The daily cap is the one
that binds: it means roughly one search plus a hundred downloads per day, total, for the
whole project.

An in-process rate limiter is not enough — a script that forgets its usage between runs will
blow the daily budget in three invocations and then sit blocked for 24 hours. So the ledger
is on disk, and every request is recorded before it is made.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path

# (window in seconds, max requests in that window)
LIMITS: tuple[tuple[int, int], ...] = (
    (60, 5),
    (3_600, 50),
    (86_400, 125),
)

DEFAULT_LEDGER = Path("corpus/.quota.json")


@dataclass(frozen=True)
class QuotaState:
    """Remaining budget in each window, plus how long until the tightest one frees up."""

    remaining: dict[int, int]
    wait_seconds: float

    @property
    def daily_remaining(self) -> int:
        return self.remaining[86_400]

    @property
    def exhausted(self) -> bool:
        """True when the daily cap is spent. Waiting will not help today."""
        return self.daily_remaining <= 0


class QuotaLedger:
    """Append-only log of request timestamps, pruned to the widest window.

    Not concurrency-safe. Run one sourcing process at a time — with a 125/day budget there
    is no reason to run two.
    """

    def __init__(self, path: Path = DEFAULT_LEDGER) -> None:
        self.path = path
        self._stamps: list[float] = self._load()

    def _load(self) -> list[float]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            # A corrupt ledger must fail closed: assume the budget is spent rather than
            # silently resetting it and hammering the API.
            raise RuntimeError(
                f"Quota ledger at {self.path} is unreadable. Delete it only if you are "
                f"certain today's requests have not been made."
            ) from None
        widest = max(window for window, _ in LIMITS)
        cutoff = time.time() - widest
        return [float(t) for t in raw.get("requests", []) if float(t) > cutoff]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"requests": self._stamps}, indent=2))

    def state(self, now: float | None = None) -> QuotaState:
        """Remaining budget per window and the wait needed before the next request."""
        now = now or time.time()
        remaining: dict[int, int] = {}
        wait = 0.0
        for window, cap in LIMITS:
            used = [t for t in self._stamps if t > now - window]
            remaining[window] = cap - len(used)
            if len(used) >= cap and used:
                # The oldest request in this window has to age out before we may proceed.
                wait = max(wait, (min(used) + window) - now)
        return QuotaState(remaining=remaining, wait_seconds=max(wait, 0.0))

    def spend(self, n: int = 1, now: float | None = None) -> None:
        """Record `n` requests as made. Call this BEFORE the request, not after.

        Recording first means a request that errors still counts — which is correct, since
        CourtListener counts it too.
        """
        now = now or time.time()
        self._stamps.extend([now] * n)
        self._save()

    def wait_for_slot(self, sleep=time.sleep) -> None:
        """Block until a request may be made. Raises when the daily cap is spent."""
        state = self.state()
        if state.exhausted:
            raise QuotaExhaustedError(
                "Daily CourtListener quota (125 requests) is spent. "
                "Resume tomorrow, or raise the limit via a membership tier."
            )
        if state.wait_seconds > 0:
            sleep(state.wait_seconds + 0.5)


class QuotaExhaustedError(RuntimeError):
    """Raised when the daily cap is spent. Waiting will not help until tomorrow."""
