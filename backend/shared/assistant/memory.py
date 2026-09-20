"""Small, bounded, process-local conversation memory for chat assistants.

The store deliberately owns no timers and performs no persistence. Expiry and
eviction happen synchronously on access, so adding channels does not add
background tasks. Keys and content never appear in aggregate statistics.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ConversationKey:
    platform: str
    channel_id: str
    participant_id: str
    assistant_scope: str = "persona"

    def __post_init__(self) -> None:
        if not self.platform.strip():
            raise ValueError("platform must not be blank")
        if not self.channel_id.strip():
            raise ValueError("channel_id must not be blank")
        if not self.participant_id.strip():
            raise ValueError("participant_id must not be blank")
        if not self.assistant_scope.strip():
            raise ValueError("assistant_scope must not be blank")


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    user_content: str
    assistant_content: str

    def __post_init__(self) -> None:
        if not self.user_content.strip():
            raise ValueError("user content must not be blank")
        if not self.assistant_content.strip():
            raise ValueError("assistant content must not be blank")

    @property
    def char_count(self) -> int:
        return len(self.user_content) + len(self.assistant_content)


@dataclass(frozen=True, slots=True)
class ConversationMemoryStats:
    active_sessions: int
    total_chars: int
    ttl_evictions: int
    lru_evictions: int
    budget_evictions: int
    oversized_turn_rejections: int


class ConversationMemoryStore(Protocol):
    def get(self, key: ConversationKey) -> tuple[ConversationTurn, ...]: ...

    def append(self, key: ConversationKey, turn: ConversationTurn) -> bool: ...

    def clear(self, key: ConversationKey) -> None: ...

    def clear_channel(self, platform: str, channel_id: str) -> int: ...

    def clear_channel_except_scope(
        self,
        platform: str,
        channel_id: str,
        assistant_scope: str,
    ) -> int: ...

    def stats(self) -> ConversationMemoryStats: ...


class NullConversationMemoryStore:
    """Drop-in store for deployments where conversation memory is disabled."""

    def get(self, key: ConversationKey) -> tuple[ConversationTurn, ...]:
        return ()

    def append(self, key: ConversationKey, turn: ConversationTurn) -> bool:
        return False

    def clear(self, key: ConversationKey) -> None:
        return None

    def clear_channel(self, platform: str, channel_id: str) -> int:
        return 0

    def clear_channel_except_scope(
        self,
        platform: str,
        channel_id: str,
        assistant_scope: str,
    ) -> int:
        return 0

    def stats(self) -> ConversationMemoryStats:
        return ConversationMemoryStats(0, 0, 0, 0, 0, 0)


@dataclass(slots=True)
class _Session:
    turns: list[ConversationTurn]
    char_count: int
    expires_at: float


class BoundedConversationMemoryStore:
    """TTL + LRU bounded short-term memory with aggregate-only telemetry."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_sessions: int,
        max_turns_per_session: int,
        max_chars_per_session: int,
        max_total_chars: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        limits = (
            ttl_seconds,
            max_sessions,
            max_turns_per_session,
            max_chars_per_session,
            max_total_chars,
        )
        if any(limit <= 0 for limit in limits):
            raise ValueError("conversation memory limits must be positive")

        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions
        self._max_turns_per_session = max_turns_per_session
        self._max_chars_per_session = max_chars_per_session
        self._max_total_chars = max_total_chars
        self._clock = clock
        self._sessions: OrderedDict[ConversationKey, _Session] = OrderedDict()
        self._total_chars = 0
        self._ttl_evictions = 0
        self._lru_evictions = 0
        self._budget_evictions = 0
        self._oversized_turn_rejections = 0

    def get(self, key: ConversationKey) -> tuple[ConversationTurn, ...]:
        session = self._sessions.get(key)
        if session is None:
            return ()
        if session.expires_at <= self._clock():
            self._remove(key)
            self._ttl_evictions += 1
            return ()
        self._sessions.move_to_end(key)
        return tuple(session.turns)

    def append(self, key: ConversationKey, turn: ConversationTurn) -> bool:
        self._purge_expired()
        if turn.char_count > self._max_chars_per_session:
            self._oversized_turn_rejections += 1
            return False

        previous = self._sessions.get(key)
        turns = list(previous.turns) if previous is not None else []
        turns.append(turn)
        while len(turns) > self._max_turns_per_session:
            turns.pop(0)
        char_count = sum(item.char_count for item in turns)
        while len(turns) > 1 and char_count > self._max_chars_per_session:
            char_count -= turns.pop(0).char_count

        if previous is not None:
            self._total_chars -= previous.char_count
        self._sessions[key] = _Session(
            turns=turns,
            char_count=char_count,
            expires_at=self._clock() + self._ttl_seconds,
        )
        self._sessions.move_to_end(key)
        self._total_chars += char_count

        while len(self._sessions) > self._max_sessions:
            self._pop_oldest()
            self._lru_evictions += 1
        while self._total_chars > self._max_total_chars:
            self._pop_oldest()
            self._budget_evictions += 1
        return key in self._sessions

    def clear(self, key: ConversationKey) -> None:
        self._remove(key)

    def clear_channel(self, platform: str, channel_id: str) -> int:
        matching = [
            key
            for key in self._sessions
            if key.platform == platform and key.channel_id == channel_id
        ]
        for key in matching:
            self._remove(key)
        return len(matching)

    def clear_channel_except_scope(
        self,
        platform: str,
        channel_id: str,
        assistant_scope: str,
    ) -> int:
        """Retire old identities while preserving an idempotent current scope."""
        matching = [
            key
            for key in self._sessions
            if key.platform == platform
            and key.channel_id == channel_id
            and key.assistant_scope != assistant_scope
        ]
        for key in matching:
            self._remove(key)
        return len(matching)

    def stats(self) -> ConversationMemoryStats:
        self._purge_expired()
        return ConversationMemoryStats(
            active_sessions=len(self._sessions),
            total_chars=self._total_chars,
            ttl_evictions=self._ttl_evictions,
            lru_evictions=self._lru_evictions,
            budget_evictions=self._budget_evictions,
            oversized_turn_rejections=self._oversized_turn_rejections,
        )

    def _purge_expired(self) -> None:
        now = self._clock()
        expired = [key for key, session in self._sessions.items() if session.expires_at <= now]
        for key in expired:
            self._remove(key)
        self._ttl_evictions += len(expired)

    def _remove(self, key: ConversationKey) -> None:
        session = self._sessions.pop(key, None)
        if session is not None:
            self._total_chars -= session.char_count

    def _pop_oldest(self) -> None:
        _, session = self._sessions.popitem(last=False)
        self._total_chars -= session.char_count
