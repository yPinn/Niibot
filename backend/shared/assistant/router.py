"""Bounded provider routing with deadlines and in-memory circuit state."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from shared.assistant.contracts import (
    AssistantProvider,
    AssistantResult,
    AttemptRecord,
    FailureKind,
    ProviderCompletion,
    ProviderFailure,
    ProviderRequest,
)


@dataclass(frozen=True, slots=True)
class RouterPolicy:
    """Hard limits for one assistant request and provider health tracking."""

    total_timeout_seconds: float
    per_attempt_timeout_seconds: float
    max_attempts: int = 3
    failure_threshold: int = 2
    cooldown_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.total_timeout_seconds <= 0:
            raise ValueError("total_timeout_seconds must be positive")
        if self.per_attempt_timeout_seconds <= 0:
            raise ValueError("per_attempt_timeout_seconds must be positive")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if self.cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds must be positive")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class ProviderCircuitSnapshot:
    provider: str
    model: str
    state: CircuitState
    consecutive_failures: int
    retry_at: float | None


@dataclass(slots=True)
class _Circuit:
    consecutive_failures: int = 0
    retry_at: float | None = None
    unhealthy: bool = False
    probe_in_flight: bool = False

    def state(self, now: float) -> CircuitState:
        if self.unhealthy:
            return CircuitState.UNHEALTHY
        if self.retry_at is None:
            return CircuitState.CLOSED
        if now < self.retry_at:
            return CircuitState.OPEN
        return CircuitState.HALF_OPEN

    def allow(self, now: float) -> bool:
        state = self.state(now)
        if state in {CircuitState.UNHEALTHY, CircuitState.OPEN}:
            return False
        if state is CircuitState.HALF_OPEN:
            if self.probe_in_flight:
                return False
            self.probe_in_flight = True
        return True

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.retry_at = None
        self.unhealthy = False
        self.probe_in_flight = False

    def record_failure(
        self,
        failure: ProviderFailure,
        *,
        now: float,
        policy: RouterPolicy,
    ) -> None:
        was_half_open = self.retry_at is not None and now >= self.retry_at
        self.probe_in_flight = False

        if failure.kind in {FailureKind.AUTHENTICATION, FailureKind.PERMISSION}:
            self.unhealthy = True
            self.retry_at = None
            return

        if not failure.retryable:
            self.record_success()
            return

        self.consecutive_failures += 1
        if was_half_open or self.consecutive_failures >= policy.failure_threshold:
            self.retry_at = now + policy.cooldown_seconds


class BoundedAssistantRouter:
    """Try a short fixed chain without retrying permanent failures."""

    def __init__(
        self,
        providers: Sequence[AssistantProvider],
        *,
        policy: RouterPolicy,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._providers = tuple(providers)
        self._policy = policy
        self._clock = clock
        self._circuits = {
            (provider.name, provider.model): _Circuit() for provider in self._providers
        }

    async def route(self, request: ProviderRequest) -> AssistantResult:
        if not self._providers:
            failure = ProviderFailure(
                provider="router",
                model="unconfigured",
                kind=FailureKind.VALIDATION,
            )
            return AssistantResult.from_failure(failure, attempts=())

        started_at = self._clock()
        attempts: list[AttemptRecord] = []
        last_failure: ProviderFailure | None = None
        attempted_count = 0

        for provider in self._providers:
            if attempted_count >= self._policy.max_attempts:
                break

            circuit = self._circuits[(provider.name, provider.model)]
            now = self._clock()
            if not circuit.allow(now):
                continue

            remaining = self._policy.total_timeout_seconds - (now - started_at)
            if remaining <= 0:
                circuit.probe_in_flight = False
                break

            attempted_count += 1
            attempt_started_at = self._clock()
            timeout = min(self._policy.per_attempt_timeout_seconds, remaining)
            response: ProviderCompletion | ProviderFailure
            try:
                response = await asyncio.wait_for(provider.complete(request), timeout=timeout)
            except TimeoutError:
                response = ProviderFailure(
                    provider=provider.name,
                    model=provider.model,
                    kind=FailureKind.TIMEOUT,
                )
            except Exception:
                response = ProviderFailure(
                    provider=provider.name,
                    model=provider.model,
                    kind=FailureKind.UNKNOWN,
                )

            latency_ms = max(0, int((self._clock() - attempt_started_at) * 1000))

            if isinstance(response, ProviderCompletion):
                circuit.record_success()
                attempts.append(
                    AttemptRecord(
                        provider=response.provider,
                        model=response.model,
                        latency_ms=latency_ms,
                    )
                )
                return AssistantResult.from_completion(
                    response,
                    attempts=tuple(attempts),
                )

            circuit.record_failure(response, now=self._clock(), policy=self._policy)
            attempts.append(
                AttemptRecord(
                    provider=response.provider,
                    model=response.model,
                    latency_ms=latency_ms,
                    failure=response,
                )
            )
            last_failure = response
            if not response.retryable:
                return AssistantResult.from_failure(
                    response,
                    attempts=tuple(attempts),
                )

        if last_failure is None:
            last_failure = ProviderFailure(
                provider="router",
                model="unavailable",
                kind=FailureKind.MODEL_UNAVAILABLE,
            )
        return AssistantResult.from_failure(last_failure, attempts=tuple(attempts))

    def provider_health(self) -> tuple[ProviderCircuitSnapshot, ...]:
        now = self._clock()
        return tuple(
            ProviderCircuitSnapshot(
                provider=provider.name,
                model=provider.model,
                state=self._circuits[(provider.name, provider.model)].state(now),
                consecutive_failures=self._circuits[
                    (provider.name, provider.model)
                ].consecutive_failures,
                retry_at=self._circuits[(provider.name, provider.model)].retry_at,
            )
            for provider in self._providers
        )
