"""Twitch public stream-schedule operations."""

from __future__ import annotations

import logging
from typing import Any

from services._twitch_api._base import HELIX_BASE, _TwitchAPIBase
from shared.twitch_egress import EgressPriority, credential_bucket_key

LOGGER: logging.Logger = logging.getLogger(__name__)


class TwitchScheduleAPIError(RuntimeError):
    """Sanitized provider failure suitable for publisher policy decisions."""

    def __init__(self, code: str, *, status_code: int | None, retryable: bool) -> None:
        super().__init__(f"Twitch schedule request failed ({code})")
        self.code = code
        self.status_code = status_code
        self.retryable = retryable


class _ScheduleMixin(_TwitchAPIBase):
    @staticmethod
    def _segment_from_response(body: dict[str, Any]) -> dict[str, Any]:
        data = body.get("data") or {}
        segments = data.get("segments") or []
        if not segments:
            raise TwitchScheduleAPIError("invalid_response", status_code=200, retryable=True)
        return dict(segments[0])

    @staticmethod
    def _error_for_status(
        status_code: int,
        *,
        missing_scope: bool = False,
        non_recurring: bool = False,
        segment_not_found: bool = False,
    ) -> TwitchScheduleAPIError:
        if status_code == 401 and missing_scope:
            return TwitchScheduleAPIError("missing_scope", status_code=401, retryable=False)
        if status_code == 401:
            return TwitchScheduleAPIError("unauthorized", status_code=401, retryable=False)
        if status_code == 403 and non_recurring:
            return TwitchScheduleAPIError(
                "non_recurring_unsupported", status_code=403, retryable=False
            )
        if status_code == 429:
            return TwitchScheduleAPIError("rate_limited", status_code=429, retryable=True)
        if status_code >= 500:
            return TwitchScheduleAPIError(
                "provider_unavailable", status_code=status_code, retryable=True
            )
        if status_code in (400, 404):
            return TwitchScheduleAPIError(
                "segment_not_found"
                if status_code == 404 or segment_not_found
                else "invalid_request",
                status_code=status_code,
                retryable=False,
            )
        return TwitchScheduleAPIError("provider_rejected", status_code=status_code, retryable=False)

    async def _schedule_mutation(
        self,
        method: str,
        *,
        broadcaster_id: str,
        access_token: str,
        segment_id: str | None = None,
        body: dict[str, Any] | None = None,
        expected_status: int = 200,
        non_recurring: bool = False,
    ):
        bucket_key = credential_bucket_key(access_token)
        await self._egress.acquire_helix(bucket_key, priority=EgressPriority.BACKGROUND)
        params = {"broadcaster_id": broadcaster_id}
        if segment_id is not None:
            params["id"] = segment_id
        try:
            response = await self._http.request(
                method,
                f"{HELIX_BASE}/schedule/segment",
                params=params,
                json=body,
                headers=self._app_headers(access_token),
            )
        except Exception:
            LOGGER.warning(
                "Twitch schedule request transport failure for broadcaster %s",
                broadcaster_id,
            )
            raise TwitchScheduleAPIError(
                "provider_unavailable", status_code=None, retryable=True
            ) from None
        self._egress.observe_helix(
            bucket_key,
            status_code=response.status_code,
            headers=response.headers,
        )
        if response.status_code != expected_status:
            message = ""
            try:
                message = str(response.json().get("message", "")).lower()
            except Exception:
                pass
            LOGGER.warning(
                "Twitch schedule request rejected for broadcaster %s with status %s",
                broadcaster_id,
                response.status_code,
            )
            raise self._error_for_status(
                response.status_code,
                missing_scope="scope" in message,
                non_recurring=non_recurring,
                segment_not_found=method == "DELETE" and segment_id is not None,
            )
        return response

    async def get_channel_stream_schedule(
        self,
        broadcaster_id: str,
        access_token: str,
        *,
        start_time: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"broadcaster_id": broadcaster_id, "first": 25}
        if start_time is not None:
            params["start_time"] = start_time
        response = await self._helix_get("schedule", params, token=access_token)
        if response is None:
            raise TwitchScheduleAPIError("provider_unavailable", status_code=None, retryable=True)
        # Twitch uses 404 to represent an otherwise valid broadcaster with no schedule.
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            message = ""
            try:
                message = str(response.json().get("message", "")).lower()
            except Exception:
                pass
            raise self._error_for_status(
                response.status_code,
                missing_scope="scope" in message,
            )
        data = response.json().get("data") or {}
        return [dict(segment) for segment in data.get("segments") or []]

    async def create_channel_stream_schedule_segment(
        self,
        broadcaster_id: str,
        access_token: str,
        *,
        start_time: str,
        timezone: str,
        duration_minutes: int,
        is_recurring: bool,
        title: str | None = None,
        category_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "start_time": start_time,
            "timezone": timezone,
            "duration": str(duration_minutes),
            "is_recurring": is_recurring,
        }
        if title is not None:
            body["title"] = title
        if category_id is not None:
            body["category_id"] = category_id
        response = await self._schedule_mutation(
            "POST",
            broadcaster_id=broadcaster_id,
            access_token=access_token,
            body=body,
            non_recurring=not is_recurring,
        )
        return self._segment_from_response(response.json())

    async def update_channel_stream_schedule_segment(
        self,
        broadcaster_id: str,
        segment_id: str,
        access_token: str,
        *,
        start_time: str | None = None,
        timezone: str | None = None,
        duration_minutes: int | None = None,
        title: str | None = None,
        category_id: str | None = None,
        is_canceled: bool | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if start_time is not None:
            body["start_time"] = start_time
        if timezone is not None:
            body["timezone"] = timezone
        if duration_minutes is not None:
            body["duration"] = str(duration_minutes)
        if title is not None:
            body["title"] = title
        if category_id is not None:
            body["category_id"] = category_id
        if is_canceled is not None:
            body["is_canceled"] = is_canceled
        response = await self._schedule_mutation(
            "PATCH",
            broadcaster_id=broadcaster_id,
            segment_id=segment_id,
            access_token=access_token,
            body=body,
        )
        return self._segment_from_response(response.json())

    async def delete_channel_stream_schedule_segment(
        self,
        broadcaster_id: str,
        segment_id: str,
        access_token: str,
    ) -> None:
        await self._schedule_mutation(
            "DELETE",
            broadcaster_id=broadcaster_id,
            segment_id=segment_id,
            access_token=access_token,
            expected_status=204,
        )
