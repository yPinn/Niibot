"""Bounded, fair in-process admission for shared provider quotas."""

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final, Literal

from shared.assistant.contracts import ProviderRequest
from shared.assistant.providers.registry import ProviderKind

_PROTOCOL_TOKENS_PER_MESSAGE: Final = 4
_PROTOCOL_TOKENS_PER_REQUEST: Final = 2
CAPACITY_DEPLOYMENT_MODE: Final = "partitioned-local"


@dataclass(frozen=True, slots=True)
class ProviderAccountCeiling:
    """Externally enforced provider/model account ceiling used by contracts."""

    requests_per_minute: int | None = None
    tokens_per_minute: int | None = None
    requests_per_day: int | None = None


@dataclass(frozen=True, slots=True)
class CapacityDeploymentGuard:
    """Declare the topology under which local quota partitions are safe."""

    runtime: Literal["twitch", "discord"]
    mode: str = CAPACITY_DEPLOYMENT_MODE
    max_replicas: int = 1
    distributed: bool = False
    shared_provider_accounts: bool = True

    def health_payload(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "runtime": self.runtime,
            "max_replicas": self.max_replicas,
            "distributed": self.distributed,
            "shared_provider_accounts": self.shared_provider_accounts,
        }


def capacity_deployment_guard(
    runtime: Literal["twitch", "discord"],
) -> CapacityDeploymentGuard:
    return CapacityDeploymentGuard(runtime=runtime)


def provider_account_ceilings() -> dict[ProviderKind, ProviderAccountCeiling]:
    """Return the ceilings that the static Twitch/Discord split must fit."""
    return {
        ProviderKind.GROQ: ProviderAccountCeiling(30, 8_000, 1_000),
        ProviderKind.GROQ_SECONDARY: ProviderAccountCeiling(30, 8_000, 1_000),
        ProviderKind.OPENROUTER: ProviderAccountCeiling(20, None, 1_000),
    }


@dataclass(frozen=True, slots=True)
class ProviderBudgetPolicy:
    """Local safety envelope kept below an external provider's account quota."""

    requests_per_minute: int | None = None
    tokens_per_minute: int | None = None
    requests_per_day: int | None = None
    max_queue_depth: int = 16
    max_wait_seconds: float = 0.25
    minute_window_seconds: float = 60.0
    day_window_seconds: float = 86_400.0

    def __post_init__(self) -> None:
        limits = (
            self.requests_per_minute,
            self.tokens_per_minute,
            self.requests_per_day,
        )
        if all(limit is None for limit in limits):
            raise ValueError("provider budget requires at least one limit")
        if any(limit is not None and limit <= 0 for limit in limits):
            raise ValueError("provider budget limits must be positive")
        if self.max_queue_depth < 0:
            raise ValueError("max_queue_depth must not be negative")
        if self.max_wait_seconds < 0:
            raise ValueError("max_wait_seconds must not be negative")
        if self.minute_window_seconds <= 0 or self.day_window_seconds <= 0:
            raise ValueError("provider budget windows must be positive")
        if self.day_window_seconds < self.minute_window_seconds:
            raise ValueError("daily budget window cannot be shorter than minute window")


def twitch_free_tier_budgets() -> dict[ProviderKind, ProviderBudgetPolicy]:
    """Reserve most direct-provider capacity for latency-sensitive Twitch chat.

    Confirmed September 2026 account-wide free-tier ceilings (per-key, shared
    across every process on the account) this split stays under:
      - Groq openai/gpt-oss-120b, no billing on file: 30 RPM / 8,000 TPM /
        1,000 RPD (https://console.groq.com/docs/rate-limits).
      - OpenRouter ":free" models with $10+ lifetime credit purchased:
        20 RPM (hard account cap, does not scale with API key count) /
        1,000 RPD (https://openrouter.ai/docs/guides/best-practices... and
        https://openrouter.zendesk.com/hc/en-us/articles/39501163636379).
    The paired Discord allocation below takes the smaller remaining share so
    the two single-process runtimes combined stay within ~85-95% of the above
    with headroom for estimation slack and Groq prompt-cache misses (a cold
    cache bills/limits the static prefix at full weight — see
    https://console.groq.com/docs/prompt-caching). Horizontal replicas need a
    distributed limiter before they can safely reuse these allocations. If
    OpenRouter credit ever drops back under $10, its real cap falls to 50
    RPD/20 RPM account-wide and this split must shrink accordingly.

    GROQ_SECONDARY (openai/gpt-oss-20b on the same Groq account) is a second,
    fully independent 30 RPM / 8,000 TPM / 1,000 RPD bucket — Groq tracks
    limits per (account, model), not per account
    (https://console.groq.com/docs/rate-limits). Discord does not use this
    model, so Twitch can claim nearly the whole bucket.
    """

    return {
        ProviderKind.GROQ: ProviderBudgetPolicy(
            requests_per_minute=22,
            tokens_per_minute=6_000,
            requests_per_day=780,
            max_queue_depth=32,
            max_wait_seconds=0.15,
        ),
        ProviderKind.GROQ_SECONDARY: ProviderBudgetPolicy(
            requests_per_minute=26,
            tokens_per_minute=7_200,
            requests_per_day=900,
            max_queue_depth=32,
            max_wait_seconds=0.15,
        ),
        ProviderKind.OPENROUTER: ProviderBudgetPolicy(
            requests_per_minute=13,
            requests_per_day=750,
            max_queue_depth=32,
            max_wait_seconds=0.15,
        ),
    }


def discord_free_tier_budgets() -> dict[ProviderKind, ProviderBudgetPolicy]:
    """Return the smaller quota share for the less latency-sensitive runtime.

    See twitch_free_tier_budgets() for the confirmed account-wide ceilings
    this is split from.
    """

    return {
        ProviderKind.GROQ: ProviderBudgetPolicy(
            requests_per_minute=5,
            tokens_per_minute=1_700,
            requests_per_day=120,
            max_queue_depth=16,
            max_wait_seconds=0.5,
        ),
        ProviderKind.GEMINI: ProviderBudgetPolicy(
            requests_per_minute=4,
            max_queue_depth=16,
            max_wait_seconds=0.5,
        ),
        ProviderKind.OPENROUTER: ProviderBudgetPolicy(
            requests_per_minute=4,
            requests_per_day=150,
            max_queue_depth=16,
            max_wait_seconds=0.5,
        ),
    }


@dataclass(frozen=True, slots=True)
class CapacityLease:
    """Opaque reservation handle without tenant or prompt content."""

    provider: str
    model: str
    reservation_id: int


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    admitted: bool
    lease: CapacityLease | None = None
    retry_after_seconds: float | None = None

    def __post_init__(self) -> None:
        if not self.admitted and self.lease is not None:
            raise ValueError("rejected admission cannot contain a lease")
        if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must not be negative")


@dataclass(frozen=True, slots=True)
class ProviderCapacitySnapshot:
    provider: str
    model: str
    minute_requests: int
    minute_tokens: int
    daily_requests: int | None
    queued_requests: int
    requests_per_minute: int | None
    tokens_per_minute: int | None
    requests_per_day: int | None


@dataclass(slots=True)
class _Reservation:
    id: int
    created_at: float
    tokens: int


@dataclass(frozen=True, slots=True)
class _Waiter:
    id: int
    scope: str
    tokens: int


def estimate_request_tokens(request: ProviderRequest) -> int:
    """Conservatively estimate mixed CJK/ASCII input plus maximum output."""

    ascii_chars = 0
    non_ascii_chars = 0
    for message in request.messages:
        for character in message.content:
            if ord(character) < 128:
                ascii_chars += 1
            else:
                non_ascii_chars += 1
    input_tokens = (
        math.ceil(ascii_chars / 4)
        + non_ascii_chars
        + len(request.messages) * _PROTOCOL_TOKENS_PER_MESSAGE
        + _PROTOCOL_TOKENS_PER_REQUEST
    )
    return max(1, input_tokens + request.max_output_tokens)


class _ProviderLimiter:
    def __init__(
        self,
        policy: ProviderBudgetPolicy,
        *,
        clock: Callable[[], float],
    ) -> None:
        self.policy = policy
        self.clock = clock
        self.condition = asyncio.Condition()
        self.reservations: deque[_Reservation] = deque()
        self.waiters: dict[str, deque[_Waiter]] = {}
        self.scope_order: deque[str] = deque()
        self.waiter_count = 0
        self.last_granted_scope: str | None = None
        self.next_reservation_id = 1
        self.next_waiter_id = 1

    async def admit(
        self,
        *,
        scope: str,
        estimated_tokens: int,
        max_wait_seconds: float | None,
    ) -> tuple[bool, int | None, float | None]:
        if estimated_tokens <= 0:
            raise ValueError("estimated_tokens must be positive")
        if self.policy.tokens_per_minute is not None:
            if estimated_tokens > self.policy.tokens_per_minute:
                return False, None, self.policy.minute_window_seconds

        wait_limit = self.policy.max_wait_seconds
        if max_wait_seconds is not None:
            if max_wait_seconds < 0:
                raise ValueError("max_wait_seconds must not be negative")
            wait_limit = min(wait_limit, max_wait_seconds)

        async with self.condition:
            now = self.clock()
            self._prune(now)
            if not self.waiter_count and self._has_capacity(now, estimated_tokens):
                reservation_id = self._reserve(now, estimated_tokens, scope)
                return True, reservation_id, None

            retry_after = self._retry_after(now, estimated_tokens)
            if wait_limit <= 0 or self.waiter_count >= self.policy.max_queue_depth:
                return False, None, retry_after

            waiter = self._enqueue(scope, estimated_tokens)
            deadline = now + wait_limit
            try:
                while True:
                    now = self.clock()
                    self._prune(now)
                    if self._is_turn(waiter) and self._has_capacity(now, estimated_tokens):
                        self._remove_waiter(waiter)
                        reservation_id = self._reserve(now, estimated_tokens, scope)
                        self.condition.notify_all()
                        return True, reservation_id, None

                    remaining = deadline - now
                    if remaining <= 0:
                        self._remove_waiter(waiter)
                        self.condition.notify_all()
                        return False, None, self._retry_after(now, estimated_tokens)
                    retry_after = self._retry_after(now, estimated_tokens)
                    wake_after = min(remaining, max(0.001, retry_after or remaining))
                    try:
                        await asyncio.wait_for(self.condition.wait(), timeout=wake_after)
                    except TimeoutError:
                        pass
            except BaseException:
                self._remove_waiter(waiter)
                self.condition.notify_all()
                raise

    async def reconcile(self, reservation_id: int, *, actual_tokens: int) -> None:
        if actual_tokens < 0:
            raise ValueError("actual_tokens must not be negative")
        async with self.condition:
            for reservation in self.reservations:
                if reservation.id == reservation_id:
                    reservation.tokens = actual_tokens
                    self.condition.notify_all()
                    return

    async def cancel(self, reservation_id: int) -> None:
        """Remove a reservation when no provider request was started."""

        async with self.condition:
            for index, reservation in enumerate(self.reservations):
                if reservation.id == reservation_id:
                    del self.reservations[index]
                    self.condition.notify_all()
                    return

    def _prune(self, now: float) -> None:
        oldest_window = (
            self.policy.day_window_seconds
            if self.policy.requests_per_day is not None
            else self.policy.minute_window_seconds
        )
        cutoff = now - oldest_window
        while self.reservations and self.reservations[0].created_at <= cutoff:
            self.reservations.popleft()

    def _minute_reservations(self, now: float) -> tuple[_Reservation, ...]:
        cutoff = now - self.policy.minute_window_seconds
        return tuple(item for item in self.reservations if item.created_at > cutoff)

    def _has_capacity(self, now: float, estimated_tokens: int) -> bool:
        minute_items = self._minute_reservations(now)
        if (
            self.policy.requests_per_minute is not None
            and len(minute_items) >= self.policy.requests_per_minute
        ):
            return False
        if self.policy.tokens_per_minute is not None and (
            sum(item.tokens for item in minute_items) + estimated_tokens
            > self.policy.tokens_per_minute
        ):
            return False
        return not (
            self.policy.requests_per_day is not None
            and len(self.reservations) >= self.policy.requests_per_day
        )

    def _retry_after(self, now: float, estimated_tokens: int) -> float | None:
        delays: list[float] = []
        minute_items = self._minute_reservations(now)
        if (
            self.policy.requests_per_minute is not None
            and len(minute_items) >= self.policy.requests_per_minute
        ):
            index = len(minute_items) - self.policy.requests_per_minute
            delays.append(minute_items[index].created_at + self.policy.minute_window_seconds - now)
        if self.policy.tokens_per_minute is not None:
            token_total = sum(item.tokens for item in minute_items)
            if token_total + estimated_tokens > self.policy.tokens_per_minute:
                for item in minute_items:
                    token_total -= item.tokens
                    if token_total + estimated_tokens <= self.policy.tokens_per_minute:
                        delays.append(item.created_at + self.policy.minute_window_seconds - now)
                        break
        if (
            self.policy.requests_per_day is not None
            and len(self.reservations) >= self.policy.requests_per_day
        ):
            index = len(self.reservations) - self.policy.requests_per_day
            delays.append(
                self.reservations[index].created_at + self.policy.day_window_seconds - now
            )
        return max(0.0, max(delays)) if delays else None

    def _reserve(self, now: float, tokens: int, scope: str) -> int:
        reservation_id = self.next_reservation_id
        self.next_reservation_id += 1
        self.reservations.append(_Reservation(reservation_id, now, tokens))
        self.last_granted_scope = scope
        return reservation_id

    def _enqueue(self, scope: str, tokens: int) -> _Waiter:
        waiter = _Waiter(self.next_waiter_id, scope, tokens)
        self.next_waiter_id += 1
        queue = self.waiters.get(scope)
        if queue is None:
            queue = deque()
            self.waiters[scope] = queue
            self.scope_order.append(scope)
        queue.append(waiter)
        self.waiter_count += 1
        self.condition.notify_all()
        return waiter

    def _is_turn(self, waiter: _Waiter) -> bool:
        self._drop_empty_scopes()
        if len(self.scope_order) > 1 and self.scope_order[0] == self.last_granted_scope:
            self.scope_order.rotate(-1)
        if not self.scope_order or self.scope_order[0] != waiter.scope:
            return False
        queue = self.waiters.get(waiter.scope)
        return bool(queue and queue[0].id == waiter.id)

    def _remove_waiter(self, waiter: _Waiter) -> None:
        queue = self.waiters.get(waiter.scope)
        if queue is None:
            return
        for index, queued in enumerate(queue):
            if queued.id == waiter.id:
                del queue[index]
                self.waiter_count -= 1
                break
        if not queue:
            self.waiters.pop(waiter.scope, None)
            try:
                self.scope_order.remove(waiter.scope)
            except ValueError:
                pass
        elif self.scope_order and self.scope_order[0] == waiter.scope:
            self.scope_order.rotate(-1)

    def _drop_empty_scopes(self) -> None:
        for scope in tuple(self.scope_order):
            if not self.waiters.get(scope):
                self.scope_order.remove(scope)

    def snapshot(self, provider: str, model: str) -> ProviderCapacitySnapshot:
        now = self.clock()
        self._prune(now)
        minute_items = self._minute_reservations(now)
        return ProviderCapacitySnapshot(
            provider=provider,
            model=model,
            minute_requests=len(minute_items),
            minute_tokens=sum(item.tokens for item in minute_items),
            daily_requests=(
                len(self.reservations) if self.policy.requests_per_day is not None else None
            ),
            queued_requests=self.waiter_count,
            requests_per_minute=self.policy.requests_per_minute,
            tokens_per_minute=self.policy.tokens_per_minute,
            requests_per_day=self.policy.requests_per_day,
        )


class ProviderCapacityController:
    """Coordinate independent provider/model budgets across channel scopes."""

    def __init__(
        self,
        policies: Mapping[tuple[str, str], ProviderBudgetPolicy],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limiters = {
            key: _ProviderLimiter(policy, clock=clock) for key, policy in policies.items()
        }

    async def admit(
        self,
        provider: str,
        model: str,
        *,
        scope: str,
        estimated_tokens: int,
        max_wait_seconds: float | None = None,
    ) -> AdmissionDecision:
        if not provider.strip() or not model.strip():
            raise ValueError("provider and model must not be blank")
        if not scope.strip():
            raise ValueError("scope must not be blank")
        limiter = self._limiters.get((provider, model))
        if limiter is None:
            return AdmissionDecision(admitted=True)
        admitted, reservation_id, retry_after = await limiter.admit(
            scope=scope,
            estimated_tokens=estimated_tokens,
            max_wait_seconds=max_wait_seconds,
        )
        lease = (
            CapacityLease(provider, model, reservation_id) if reservation_id is not None else None
        )
        return AdmissionDecision(
            admitted=admitted,
            lease=lease,
            retry_after_seconds=retry_after,
        )

    async def reconcile(self, lease: CapacityLease, *, actual_tokens: int) -> None:
        limiter = self._limiters.get((lease.provider, lease.model))
        if limiter is not None:
            await limiter.reconcile(lease.reservation_id, actual_tokens=actual_tokens)

    async def cancel(self, lease: CapacityLease) -> None:
        limiter = self._limiters.get((lease.provider, lease.model))
        if limiter is not None:
            await limiter.cancel(lease.reservation_id)

    def snapshots(self) -> tuple[ProviderCapacitySnapshot, ...]:
        return tuple(
            limiter.snapshot(provider, model)
            for (provider, model), limiter in self._limiters.items()
        )
