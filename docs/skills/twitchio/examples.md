# TwitchIO 3 範例

## 最小 Bot

```python
import twitchio
from twitchio.ext import commands, eventsub

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            client_id="...",
            client_secret="...",
            bot_id="BOT_ID",
            prefix="!"
        )

    async def setup_hook(self):
        await self.add_component(Commands())
        await self.subscribe_websocket(
            eventsub.ChatMessageSubscription(
                broadcaster_user_id="CHANNEL_ID",
                user_id=self.bot_id
            )
        )

class Commands(commands.Component):
    @commands.command()
    async def ping(self, ctx: commands.Context):
        await ctx.reply("Pong!")

Bot().run()
```

---

## 指令範例

### 帶參數

```python
@commands.command()
async def echo(self, ctx: commands.Context, *, msg: str):
    await ctx.send(msg)

@commands.command()
async def add(self, ctx: commands.Context, a: int, b: int):
    await ctx.reply(f"{a + b}")
```

### 用戶參數

```python
@commands.command()
async def hug(self, ctx: commands.Context, user: twitchio.User):
    await ctx.send(f"{ctx.author.display_name} hugs {user.display_name}!")
```

### 可選參數

```python
@commands.command()
async def greet(self, ctx: commands.Context, name: str = None):
    await ctx.reply(f"Hello {name or ctx.author.display_name}!")
```

### 可變參數

```python
import random

@commands.command()
async def pick(self, ctx: commands.Context, *options: str):
    if options:
        await ctx.reply(random.choice(options))
```

---

## 指令群組

```python
@commands.group()
async def config(self, ctx: commands.Context):
    if ctx.invoked_subcommand is None:
        await ctx.reply("!config show | !config set <key> <value>")

@config.command()
async def show(self, ctx: commands.Context):
    await ctx.reply("Settings: ...")

@config.command()
async def set(self, ctx: commands.Context, key: str, value: str):
    await ctx.reply(f"Set {key}={value}")
```

---

## 守衛

### 管理員限定

```python
@commands.Component.guard()
async def mod_only(self, ctx: commands.Context) -> bool:
    return ctx.author.is_mod or ctx.author.is_broadcaster
```

### 指令級別

```python
def owner_only():
    async def pred(ctx: commands.Context):
        return ctx.author.id == ctx.bot.owner_id
    return commands.guard(pred)

@commands.command()
@owner_only()
async def shutdown(self, ctx: commands.Context):
    await ctx.reply("Bye!")
    await ctx.bot.close()
```

---

## 事件監聽

```python
@commands.Component.listener()
async def event_message(self, payload: twitchio.ChatMessage):
    if payload.chatter.id == self.bot.bot_id:
        return
    print(f"{payload.chatter.name}: {payload.text}")

@commands.Component.listener()
async def event_follow(self, payload: twitchio.ChannelFollow):
    print(f"New follower: {payload.user.name}")

@commands.Component.listener()
async def event_subscription(self, payload: twitchio.ChannelSubscribe):
    print(f"New sub: {payload.user.name} (Tier {payload.tier})")
```

---

## 定時任務

```python
from twitchio.ext import routines
from datetime import timedelta

class MyComponent(commands.Component):
    async def component_load(self):
        self.announce.start()

    async def component_teardown(self):
        self.announce.cancel()

    @routines.routine(delta=timedelta(minutes=15))
    async def announce(self):
        # 執行定時邏輯
        pass

    @announce.error
    async def on_error(self, error: Exception):
        print(f"Error: {error}")
```

---

## 錯誤處理

```python
async def component_command_error(self, ctx: commands.Context, error: Exception):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply(f"Missing: {error.param.name}")
        return
    if isinstance(error, commands.GuardFailure):
        await ctx.reply("No permission")
        return
    await ctx.reply(f"Error: {error}")
```

---

## 等待輸入

```python
import asyncio

@commands.command()
async def confirm(self, ctx: commands.Context):
    await ctx.send("Type 'yes' to confirm (30s)")

    def check(msg: twitchio.ChatMessage):
        return msg.chatter.id == ctx.author.id and msg.text.lower() == "yes"

    try:
        await self.bot.wait_for("message", timeout=30, predicate=check)
        await ctx.reply("Confirmed!")
    except asyncio.TimeoutError:
        await ctx.reply("Timeout")
```

---

## API 查詢

```python
@commands.command()
async def live(self, ctx: commands.Context):
    async for stream in self.bot.fetch_streams(user_ids=[ctx.channel.user.id]):
        await ctx.reply(f"Live: {stream.title} ({stream.viewer_count} viewers)")
        return
    await ctx.reply("Offline")

@commands.command()
async def game(self, ctx: commands.Context, *, name: str):
    game = await self.bot.fetch_game(name=name)
    if game:
        await ctx.reply(f"{game.name} (ID: {game.id})")
```

---

## 自訂 Token 儲存

```python
import aiosqlite

class Bot(commands.Bot):
    async def setup_hook(self):
        async with aiosqlite.connect("bot.db") as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tokens (
                    user_id TEXT PRIMARY KEY,
                    access TEXT,
                    refresh TEXT
                )
            """)

    async def load_tokens(self, path=None):
        async with aiosqlite.connect("bot.db") as db:
            async with db.execute("SELECT * FROM tokens") as cur:
                async for row in cur:
                    await self.add_token(token=row[1], refresh=row[2])

    async def save_tokens(self, path=None):
        async with aiosqlite.connect("bot.db") as db:
            for uid, data in self.tokens.items():
                await db.execute(
                    "INSERT OR REPLACE INTO tokens VALUES (?,?,?)",
                    (uid, data.token, data.refresh)
                )
            await db.commit()
```
