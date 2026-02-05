"""
Discord API 速率限制監控和預防模組
防止 bot 因過多請求而被 Discord 封禁
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

import discord

from .config import BotConfig

logger = logging.getLogger("discord_bot.rate_limiter")


@dataclass
class RateLimitStats:
    """速率限制統計數據"""

    total_requests: int = 0
    rate_limited_count: int = 0

    # 時間窗口內的請求記錄 (儲存時間戳)
    recent_requests: deque[float] = field(default_factory=lambda: deque(maxlen=1000))

    # 429 錯誤記錄
    rate_limit_errors: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=50))

    # 最後一次重置時間
    last_reset: float = field(default_factory=time.time)


class RateLimitMonitor:
    """Discord API 速率限制監控器"""

    # Discord API 限制參考值
    GLOBAL_RATE_LIMIT = 50
    MESSAGE_RATE_LIMIT = 5
    REACTION_RATE_LIMIT = 1

    def __init__(self, client: discord.Client):
        self.client = client
        self.stats = RateLimitStats()
        self._monitoring = False

        # 修正 Mypy 報錯：明確標註字典型別
        self._warning_cooldown: dict[str, float] = {}

        self.WARNING_THRESHOLD: float = getattr(BotConfig, "RATE_LIMIT_WARNING_THRESHOLD", 0.7)
        self.CRITICAL_THRESHOLD: float = getattr(BotConfig, "RATE_LIMIT_CRITICAL_THRESHOLD", 0.9)
        self.enabled: bool = getattr(BotConfig, "RATE_LIMIT_ENABLED", True)

    async def start_monitoring(self) -> None:
        """啟動監控"""
        if self._monitoring or not self.enabled:
            return

        self._monitoring = True

        # 使用 cast 轉型為 Any 解決 "Client has no attribute add_listener"
        client_any = cast(Any, self.client)
        client_any.add_listener(self._on_request, "on_socket_raw_send")
        client_any.add_listener(self._on_rate_limit, "on_rate_limit")

        asyncio.create_task(self._periodic_reset())
        logger.info("Rate Limit Monitor started")

    async def stop_monitoring(self) -> None:
        """停止監控"""
        if not self._monitoring:
            return

        self._monitoring = False

        # 使用 cast 轉型為 Any 解決屬性不存在的報錯
        client_any = cast(Any, self.client)
        client_any.remove_listener(self._on_request, "on_socket_raw_send")
        client_any.remove_listener(self._on_rate_limit, "on_rate_limit")
        logger.info("Rate Limit Monitor stopped")

    async def _on_request(self, payload: Any) -> None:
        """記錄每個發送的請求"""
        self.stats.total_requests += 1
        self.stats.recent_requests.append(time.time())

    async def _on_rate_limit(self, payload: Any) -> None:
        """處理速率限制事件"""
        self.stats.rate_limited_count += 1

        error_info = {
            "timestamp": datetime.now().isoformat(),
            "bucket": getattr(payload, "bucket", "global"),
            "retry_after": getattr(payload, "retry_after", 0.0),
            "scope": getattr(payload, "scope", "unknown"),
        }
        self.stats.rate_limit_errors.append(error_info)

        logger.warning(
            f"Rate limit triggered - "
            f"Bucket: {error_info['bucket']}, "
            f"Retry: {error_info['retry_after']:.2f}s, "
            f"Scope: {error_info['scope']}"
        )

    def _get_recent_count(self, seconds: float) -> int:
        """計算給定秒數內的請求數量 (優化效能)"""
        now = time.time()
        threshold = now - seconds
        count = 0
        # 從最近的紀錄開始往前找，直到超過時間閾值就停止
        for t in reversed(self.stats.recent_requests):
            if t > threshold:
                count += 1
            else:
                break
        return count

    def check_rate_limit_risk(self, action_type: str = "general") -> tuple[bool, str]:
        """檢查當前速率風險"""
        recent_1s = self._get_recent_count(1.0)
        global_usage = recent_1s / self.GLOBAL_RATE_LIMIT

        if global_usage >= self.CRITICAL_THRESHOLD:
            return False, f"Critical: Global rate high ({recent_1s}/{self.GLOBAL_RATE_LIMIT} req/s)"

        if global_usage >= self.WARNING_THRESHOLD:
            msg = f"Warning: Global rate threshold reached ({recent_1s}/{self.GLOBAL_RATE_LIMIT} req/s)"
            self._log_warning_once("global", msg)
            return True, msg

        if action_type == "message":
            recent_5s = self._get_recent_count(5.0)
            message_rate = recent_5s / 5
            if message_rate >= self.MESSAGE_RATE_LIMIT * self.CRITICAL_THRESHOLD:
                return False, f"Critical: Message rate high ({message_rate:.1f} msg/s)"

        return True, "Rate status: Normal"

    def _log_warning_once(self, key: str, message: str, cooldown: int = 60) -> None:
        """防止相同警告重複輸出"""
        current_time = time.time()
        if key in self._warning_cooldown:
            if current_time - self._warning_cooldown[key] < cooldown:
                return

        self._warning_cooldown[key] = current_time
        logger.warning(message)

    async def safe_send_message(
        self, channel: Any, *args: Any, **kwargs: Any
    ) -> discord.Message | None:
        """安全發送訊息"""
        is_safe, msg = self.check_rate_limit_risk("message")

        if not is_safe:
            logger.error(f"Message cancelled due to rate limit: {msg}")
            return None

        try:
            # 使用 cast 解決 "Returning Any from function" 錯誤
            result = await channel.send(*args, **kwargs)
            return cast(discord.Message | None, result)
        except discord.HTTPException as e:
            if e.status == 429:
                logger.error(f"HTTP 429 received: {e}")
            raise

    async def _periodic_reset(self) -> None:
        """定期重置統計數據"""
        while self._monitoring:
            await asyncio.sleep(300)
            if self.stats.total_requests > 0:
                self._generate_report()
            self.stats.last_reset = time.time()

    def _generate_report(self) -> None:
        """生成速率統計報告"""
        current_time = time.time()
        time_elapsed = current_time - self.stats.last_reset
        rps = self.stats.total_requests / time_elapsed if time_elapsed > 0 else 0

        recent_rps = self._get_recent_count(60.0) / 60

        logger.info(
            f"Rate Stats (Last {time_elapsed / 60:.1f} min): "
            f"Total: {self.stats.total_requests}, "
            f"Avg: {rps:.2f} req/s, "
            f"Recent 1min: {recent_rps:.2f} req/s, "
            f"Limit hits: {self.stats.rate_limited_count}"
        )

    def get_stats_summary(self) -> dict[str, Any]:
        """獲取統計摘要"""
        recent_1min = self._get_recent_count(60.0)
        return {
            "total_requests": self.stats.total_requests,
            "rate_limited_count": self.stats.rate_limited_count,
            "recent_1min_requests": recent_1min,
            "recent_1min_rps": recent_1min / 60,
            "recent_errors": list(self.stats.rate_limit_errors)[-5:]
            if self.stats.rate_limit_errors
            else [],
        }
