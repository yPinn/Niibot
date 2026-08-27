"""Aggregation read queries for AnalyticsRepository.

Composed from focused sub-mixins so each query concern stays small and
testable in isolation:

    _query_session  — per-session command/event detail
    _query_summary  — channel-level summary + top commands/chatters
    _query_insights — the Insights-page parallel aggregation
    _query_viewers  — viewer list, profile, rank, and channel status

Shared module-level constants and the bot-list helper live in _query_common.

Depends on attributes defined in AnalyticsRepository.__init__:
    self.pool
"""

from __future__ import annotations

from shared.repositories.analytics._query_common import (  # noqa: F401  (re-exported for tests)
    _SCORE_SQL,
    _get_bot_list,
)
from shared.repositories.analytics._query_insights import _InsightsQueryMixin
from shared.repositories.analytics._query_session import _SessionQueryMixin
from shared.repositories.analytics._query_summary import _SummaryQueryMixin
from shared.repositories.analytics._query_viewers import _ViewerQueryMixin


class _AnalyticsQueryMixin(
    _SessionQueryMixin,
    _SummaryQueryMixin,
    _InsightsQueryMixin,
    _ViewerQueryMixin,
):
    """Aggregation reads: session detail, channel summaries, insights, viewers."""
