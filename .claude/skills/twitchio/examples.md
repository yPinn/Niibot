# TwitchIO 3 範例

**函式庫版本**: 3.3.2 | **Python**: `>=3.11`

範例基於官方文件與套件原始碼；非對應任何特定專案。

---

## 最小 Bot（WebSocket EventSub）

```python
import asyncio
import logging

import twitchio
from twitchio import eventsub
from twitchio.ext import commands


class Bot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            client_id="...",
            client_secret="...",
            bot_id="BOT_ID",
            owner_id="OWNER_ID",
            prefix="!",
        )

    async def setup_hook(self) -> None:
        await self.add_component(General())
        await self.subscribe_websocket(
            eventsub.ChatMessageSubscription(
                broadcaster_user_id="CHANNEL_ID",
                user_id=self.bot_id,
            )
        )


class General(commands.Component):
    @commands.command()
    async def ping(self, ctx: commands.Context) -> None:
        await ctx.reply("Pong!")


def main() -> None:
    twitchio.utils.setup_logging(level=logging.INFO)

    async def runner() -> None:
        async with Bot() as bot:
            await bot.start()

    asyncio.run(runner())


main()
```

---

## AutoBot + Conduit（多頻道 / 長駐部署）

```python
import twitchio
from twitchio import eventsub
from twitchio.ext import commands


def build_subs(broadcaster_id: str, bot_id: str) -> list[eventsub.SubscriptionPayload]:
    return [
        eventsub.ChatMessageSubscription(broadcaster_user_id=broadcaster_id, user_id=bot_id),
        eventsub.StreamOnlineSubscription(broadcaster_user_id=broadcaster_id),
        eventsub.StreamOfflineSubscription(broadcaster_user_id=broadcaster_id),
        eventsub.ChannelFollowSubscription(
            broadcaster_user_id=broadcaster_id, moderator_user_id=bot_id
        ),
        eventsub.ChannelRaidSubscription(to_broadcaster_user_id=broadcaster_id),
        eventsub.ChannelPointsRedeemAddSubscription(broadcaster_user_id=broadcaster_id),
    ]


class Bot(commands.AutoBot):
    def __init__(self, subs: list[eventsub.SubscriptionPayload], conduit_id: str | None) -> None:
        super().__init__(
            client_id="...",
            client_secret="...",
            bot_id="BOT_ID",
            owner_id="OWNER_ID",
            prefix="!",
            subscriptions=subs,       # 新 Conduit 時自動 multi_subscribe
            conduit_id=conduit_id,    # None = 建新的；帶入既有 id 可跨重啟保留訂閱
        )

    async def setup_hook(self) -> None:
        await self.add_component(General())

    async def add_channel(self, broadcaster_id: str) -> None:
        """執行期新增頻道訂閱。"""
        resp = await self.multi_subscribe(build_subs(broadcaster_id, self.bot_id))
        if resp.errors:
            for err in resp.errors:
                print("subscribe failed:", err)


class General(commands.Component):
    @commands.command()
    async def ping(self, ctx: commands.Context) -> None:
        await ctx.reply("Pong!")
```

---

## 指令：參數與轉換

```python
class Fun(commands.Component):
    @commands.command()
    async def add(self, ctx: commands.Context, a: int, b: int) -> None:
        await ctx.reply(f"{a + b}")

    @commands.command()
    async def echo(self, ctx: commands.Context, *, msg: str) -> None:  # 吃到行尾
        await ctx.send(msg)

    @commands.command()
    async def greet(self, ctx: commands.Context, name: str | None = None) -> None:
        await ctx.reply(f"Hello {name or ctx.chatter.display_name}!")

    @commands.command()
    async def pick(self, ctx: commands.Context, *options: str) -> None:
        import random
        if options:
            await ctx.reply(random.choice(options))
```

---

## 指令群組

```python
class Config(commands.Component):
    @commands.group(invoke_fallback=True)
    async def config(self, ctx: commands.Context) -> None:
        # 只有在「沒有匹配 subcommand」時執行（invoke_fallback=True）
        await ctx.reply("!config show | !config set <key> <value>")

    @config.command()
    async def show(self, ctx: commands.Context) -> None:
        await ctx.reply("settings: ...")

    @config.command()
    async def set(self, ctx: commands.Context, key: str, value: str) -> None:
        await ctx.reply(f"set {key}={value}")
```

> 有 subcommand 時 group callback 完全不執行；group 的 early-return 對 subcommand 無效——
> subcommand 需自行守衛，或改用 Component-level guard。

---

## 守衛

```python
class Admin(commands.Component):
    # Component 級：套用所有指令（含 group subcommands）
    @commands.Component.guard()
    def _is_mod(self, ctx: commands.Context) -> bool:
        # .moderator 已涵蓋 lead mod 與 broadcaster
        return ctx.chatter.moderator

    @commands.command()
    async def clear(self, ctx: commands.Context) -> None:
        await ctx.reply("cleared")


class Owner(commands.Component):
    @commands.command()
    @commands.is_owner()           # 內建守衛工廠
    async def shutdown(self, ctx: commands.Context) -> None:
        await ctx.reply("bye")
        await ctx.bot.close()

    @commands.command()
    @commands.is_elevated()        # broadcaster / mod / VIP 任一
    async def special(self, ctx: commands.Context) -> None:
        await ctx.reply("ok")
```

---

## 冷卻

```python
@commands.cooldown(rate=2, per=10, key=commands.BucketType.chatter)
@commands.command()
async def spammy(self, ctx: commands.Context) -> None:
    await ctx.reply("ok")
```

---

## 事件監聽

```python
class Events(commands.Component):
    @commands.Component.listener()
    async def event_message(self, payload: twitchio.ChatMessage) -> None:
        if payload.chatter.id == self.bot.bot_id:
            return
        print(f"{payload.chatter.name}: {payload.text}")

    @commands.Component.listener()
    async def event_follow(self, payload: twitchio.ChannelFollow) -> None:
        await payload.broadcaster.send_message(
            message=f"welcome {payload.user.display_name}!",
            sender=self.bot.bot_id,
        )

    @commands.Component.listener()
    async def event_subscription(self, payload: twitchio.ChannelSubscribe) -> None:
        print(f"new sub: {payload.user.name} (tier {payload.tier})")

    @commands.Component.listener()
    async def event_raid(self, payload: twitchio.ChannelRaid) -> None:
        # from_broadcaster = 發起 raid 者；to_broadcaster = 被 raid 的頻道
        await payload.to_broadcaster.send_shoutout(
            to_broadcaster=payload.from_broadcaster.id,
            moderator=self.bot.bot_id,
        )

    @commands.Component.listener()
    async def event_stream_online(self, payload: twitchio.StreamOnline) -> None:
        # payload.broadcaster (PartialUser), payload.type, payload.started_at
        print(f"{payload.broadcaster.name} went live ({payload.type})")

    @commands.Component.listener()
    async def event_stream_offline(self, payload: twitchio.StreamOffline) -> None:
        print(f"{payload.broadcaster.name} went offline")

    @commands.Component.listener()
    async def event_custom_redemption_add(
        self, payload: twitchio.ChannelPointsRedemptionAdd
    ) -> None:
        print(f"{payload.user.name} redeemed {payload.reward.title}")
```

---

## 定時任務

```python
from datetime import timedelta

from twitchio.ext import commands, routines


class Announcer(commands.Component):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def component_load(self) -> None:
        self.announce.start()

    async def component_teardown(self) -> None:
        self.announce.cancel()

    @routines.routine(delta=timedelta(minutes=15))
    async def announce(self) -> None:
        user = self.bot.create_partialuser("CHANNEL_ID")
        await user.send_message(message="don't forget to follow!", sender=self.bot.bot_id)

    @announce.error
    async def _on_error(self, error: Exception) -> None:
        print("routine error:", error)
```

---

## 錯誤處理

```python
class Handled(commands.Component):
    async def component_command_error(
        self, payload: commands.CommandErrorPayload
    ) -> bool | None:
        error = payload.exception
        ctx = payload.context

        if isinstance(error, commands.CommandNotFound):
            return False  # 靜默
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(f"missing: {error.param.name}")
            return False
        if isinstance(error, commands.GuardFailure):
            await ctx.reply("no permission")
            return False
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(f"slow down ({error.remaining:.0f}s)")
            return False
        return None  # 繼續往 Bot 層 event_command_error 傳
```

---

## 開台狀態查詢

```python
class Live(commands.Component):
    @commands.command()
    async def live(self, ctx: commands.Context) -> None:
        stream = await ctx.broadcaster.fetch_stream()   # Stream | None，可 await
        if stream:
            await ctx.reply(f"live: {stream.title} ({stream.viewer_count} viewers)")
        else:
            await ctx.reply("offline")
```

`bot.fetch_streams(...)` 則是 `HTTPAsyncIterator`（不可 await）：

```python
async for s in bot.fetch_streams(user_ids=["1", "2", "3"]):
    print(s.user.name, s.viewer_count)
```

---

## 自訂 Token 儲存（DB）

```python
import asyncpg

from twitchio.ext import commands


class Bot(commands.AutoBot):
    def __init__(self, pool: asyncpg.Pool, **kwargs) -> None:
        self.pool = pool
        super().__init__(**kwargs)

    async def load_tokens(self, path: str | None = None) -> None:
        rows = await self.pool.fetch("SELECT token, refresh FROM tokens")
        for row in rows:
            await self.add_token(row["token"], row["refresh"])

    async def save_tokens(self, path: str | None = None) -> None:
        async with self.pool.acquire() as conn:
            for user_id, data in self.tokens.items():
                await conn.execute(
                    """
                    INSERT INTO tokens (user_id, token, refresh)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id)
                    DO UPDATE SET token = EXCLUDED.token, refresh = EXCLUDED.refresh
                    """,
                    user_id, data.token, data.refresh,
                )

    async def event_token_refreshed(self, payload: "twitchio.TokenRefreshedPayload") -> None:
        await self.save_tokens()
```
