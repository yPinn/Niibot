# TwitchIO 3 API 參考

**函式庫版本**: 3.3.2 | **Python**: `>=3.11`（測試 3.11 / 3.12 / 3.13）| **aiohttp**: `>=3.9.1,<4`

來源：安裝套件原始碼 + <https://twitchio.dev/en/stable/> + 官方 changelog。

---

## 建構參數

### `Client`（kw-only）

| 參數 | 類型 | 必填 | 說明 |
| ---- | ---- | :--: | ---- |
| `client_id` | `str` | ✓ | Twitch App ID |
| `client_secret` | `str \| None` | – | App secret；DCF（Device Code Flow）時可省略 |
| `bot_id` | `str \| None` | – | Bot 帳號 User ID，**強烈建議**（讓 TwitchIO 在需要時用 bot 自身 token） |
| `redirect_uri` | `str \| None` | – | OAuth 回調（web adapter 用） |
| `scopes` | `twitchio.Scopes \| None` | – | OAuth 預設 scopes |
| `session` | `aiohttp.ClientSession \| None` | – | 自訂 session |
| `adapter` | `StarletteAdapter \| AiohttpAdapter \| None` | – | web adapter；預設 `AiohttpAdapter` |
| `fetch_client_user` | `bool` | – | 預設 `True`，登入時抓取並快取 bot 自身 `User`（需 `bot_id`） |

### `commands.Bot`（kw-only，繼承 Client 全部參數）

| 參數 | 類型 | 說明 |
| ---- | ---- | ---- |
| `bot_id` | `str` | 文件標為必填（DCF 例外）；`bot.bot_id` property 會 assert 非空 |
| `owner_id` | `str \| None` | bot 擁有者 User ID，預設 `None` |
| `prefix` | `str \| Iterable[str] \| Coroutine[..., str \| Iterable[str]]` | **必填** |

### `commands.AutoBot`（繼承 Bot；`client_secret` 為必填）

額外選項：`conduit_id`（重用既有 Conduit）、`shard_ids: list[int]`、`max_per_shard: int`、`subscriptions: list[SubscriptionPayload]`、`force_subscribe: bool`、`force_scale: bool`。

> shard 數 ≈ `max(len(subscriptions) / max_per_shard, 2)`，或 `len(shard_ids)`。多數 app 用 2–3 shard。

---

## 生命週期

```python
await bot.login(token=None, load_tokens=True, save_tokens=True)
await bot.start()          # 非阻塞
bot.run()                  # 阻塞（內部 start）
await bot.close()          # 卸載 modules/components 後關閉
await bot.login_dcf(...)   # Device Code Flow
await bot.start_dcf(...)
```

### 可覆寫鉤子

```python
async def setup_hook(self) -> None: ...
async def event_ready(self) -> None: ...
async def before_invoke(self, ctx: commands.Context) -> None: ...
async def after_invoke(self, ctx: commands.Context) -> None: ...
async def event_command_error(
    self, payload: commands.CommandErrorPayload
) -> None: ...
async def load_tokens(self, path: str | None = None) -> None: ...
async def save_tokens(self, path: str | None = None) -> None: ...
```

---

## 指令 API

```python
@commands.command(name=None, aliases=None, extras=None, guards_after_parsing=False)
@commands.group(name=None, aliases=None, invoke_fallback=False, ...)
@commands.cooldown(rate=..., per=..., key=commands.BucketType.chatter)

@commands.guard(predicate)          # predicate: (ctx) -> bool，可 sync / async
commands.is_owner()                 # 內建守衛工廠
commands.is_broadcaster()
commands.is_moderator()
commands.is_lead_moderator()
commands.is_vip()
commands.is_staff()
commands.is_elevated()              # broadcaster / mod / VIP 任一
```

`BucketType`：`default` | `user` | `channel` | `chatter`。

### Bot 指令 / Component / 模組管理

```python
bot.add_command(cmd)          # bot.get_command(name) / bot.remove_command(name)
await bot.add_component(c)    # bot.remove_component(name) / bot.get_component(name)
await bot.load_module("pkg.mod")      # 需 setup(bot)；unload_module / reload_module
bot.commands  bot.components  bot.modules
```

---

## `commands.Context`

| 成員 | 類型 |
| ---- | ---- |
| `chatter` / `author` | `Chatter \| PartialUser` |
| `broadcaster` / `channel` | `PartialUser` |
| `source_broadcaster` | `PartialUser \| None`（Shared Chat） |
| `message` | `ChatMessage \| None` |
| `redemption` | `ChannelPointsRedemptionAdd \| ChannelPointsRedemptionUpdate \| None` |
| `payload` | `ChatMessage \| ChannelPointsRedemption*` |
| `command` / `component` | `Command \| RewardCommand \| None` / `Component \| None` |
| `invoked_subcommand` | `Command \| None` |
| `invoked_with` / `subcommand_trigger` | `str \| None` |
| `prefix` / `content` | `str` |
| `args` / `kwargs` | `list` / `dict` |
| `type` | `ContextType.MESSAGE \| ContextType.REWARD` |
| `failed` / `error_dispatched` | `bool` |
| `is_owner()` / `is_valid()` | `bool` |

```python
await ctx.send(content, *, me=False) -> SentMessage
await ctx.reply(content, *, me=False) -> SentMessage
await ctx.send_announcement(content, *, color=None)   # "blue"|"green"|"orange"|"purple"|"primary"
await ctx.send_translated(content, *, me=False, langcode=None)
await ctx.reply_translated(content, *, me=False, langcode=None)
await ctx.delete_message()                            # REWARD context 不可用
```

---

## `Chatter`（繼承 `PartialUser`）

自 `PartialUser`：`id: str`、`name: str`（lowercase）、`display_name: str`。

角色布林屬性（**無 `is_` 前綴**）：

| 屬性 | 備註 |
| ---- | ---- |
| `broadcaster` | |
| `moderator` | `_is_moderator or _is_lead_moderator or broadcaster` |
| `lead_moderator` | `_is_lead_moderator or broadcaster` |
| `vip` | |
| `subscriber` / `founder` | |
| `staff` / `admin` / `partner` | |
| `turbo` / `prime` | |
| `artist` | 頻道 artist |
| `no_audio` / `no_video` | |

其他：`channel: PartialUser`、`colour` / `color: Colour | None`、`badges: list[ChatMessageBadge]`。

---

## EventSub 訂閱類（`twitchio.eventsub`）

完整 `__all__`（3.3.2）常用摘錄——命名以此為準：

```text
聊天:  ChatMessageSubscription, ChatNotificationSubscription, ChatMessageDeleteSubscription,
       ChatClearSubscription, ChatClearUserMessagesSubscription, ChatSettingsUpdateSubscription,
       ChatUserMessageHoldSubscription, ChatUserMessageUpdateSubscription
頻道:  ChannelUpdateSubscription, ChannelFollowSubscription, ChannelRaidSubscription,
       ChannelBanSubscription, ChannelUnbanSubscription, ChannelUnbanRequestSubscription,
       ChannelUnbanRequestResolveSubscription, ChannelModerateSubscription/V2,
       ChannelModeratorAddSubscription, ChannelModeratorRemoveSubscription,
       ChannelVIPAddSubscription, ChannelVIPRemoveSubscription,
       ChannelWarningSendSubscription, ChannelWarningAcknowledgementSubscription,
       ChannelBitsUseSubscription, AdBreakBeginSubscription
訂閱:  ChannelSubscribeSubscription, ChannelSubscriptionGiftSubscription,
       ChannelSubscribeMessageSubscription, ChannelSubscriptionEndSubscription, ChannelCheerSubscription
頻道點數: ChannelPointsRewardAddSubscription, ChannelPointsRewardUpdateSubscription,
       ChannelPointsRewardRemoveSubscription, ChannelPointsRedeemAddSubscription,
       ChannelPointsRedeemUpdateSubscription, ChannelPointsAutoRedeemSubscription,
       ChannelPointsAutoRedeemV2Subscription, CustomPowerupRedeemAddSubscription
直播:  StreamOnlineSubscription, StreamOfflineSubscription
Shared Chat: SharedChatSessionBeginSubscription, SharedChatSessionUpdateSubscription,
       SharedChatSessionEndSubscription
其他:  GoalBegin/Progress/EndSubscription, HypeTrainBegin/Progress/EndSubscription,
       ChannelPollBegin/Progress/EndSubscription, ChannelPredictionBegin/Progress/Lock/EndSubscription,
       CharityCampaign*Subscription, ShieldModeBegin/EndSubscription,
       ShoutoutCreateSubscription, ShoutoutReceiveSubscription,
       SuspiciousUserMessageSubscription, SuspiciousUserUpdateSubscription,
       AutomodMessageHold(V2)/Update(V2)/SettingsUpdate/TermsUpdateSubscription,
       WhisperReceivedSubscription, UserUpdateSubscription,
       UserAuthorizationGrantSubscription, UserAuthorizationRevokeSubscription
```

參數常見於 `broadcaster_user_id`；部分另需 `user_id`（聊天）、`moderator_user_id`（follow / mod-scoped）、
`to_broadcaster_user_id` / `from_broadcaster_user_id`（raid）、`reward_id`（特定 reward 的 redeem）。

### 訂閱 / 管理方法

```python
await bot.subscribe_websocket(payload, *, as_bot=None, token_for=None, socket_id=None)
  # as_bot 在 Client 預設 False、在 Bot 預設 True
await bot.subscribe_webhook(payload, *, callback_url=..., eventsub_secret=...)
resp = await bot.multi_subscribe(subs, *, wait=True, stop_on_error=False)   # AutoClient/AutoBot
  # resp.success: list[MultiSubscribeSuccess(subscription, response)]
  # resp.errors:  list[MultiSubscribeError(subscription, error)]
  # response 是 Twitch 原始回應 dict：訂閱 id 在 response["data"][0]["id"]（非 response["id"]）
  # wait=False 回傳 asyncio.Task

await bot.fetch_eventsub_subscriptions()
await bot.delete_eventsub_subscription(sub_id)
await bot.delete_all_eventsub_subscriptions()
```

---

## 事件 ↔ Payload 對照（`twitchio.ext` 事件；名稱來自 `events.pyi`）

| 事件 | Payload |
| ---- | ------- |
| `event_ready` | — |
| `event_token_refreshed` | `TokenRefreshedPayload` |
| `event_oauth_authorized` | `UserTokenPayload` |
| `event_subscription_revoked` | `SubscriptionRevoked` |
| `event_message` | `ChatMessage` |
| `event_message_whisper` | `Whisper` |
| `event_message_delete` | `ChatMessageDelete` |
| `event_chat_notification` | `ChatNotification` |
| `event_chat_clear` / `event_chat_clear_user` | `ChannelChatClear` / `ChannelChatClearUserMessages` |
| `event_chat_settings_update` | `ChatSettingsUpdate` |
| `event_bits_use` | `ChannelBitsUse` |
| `event_custom_power_up_redemption_add` | `CustomPowerupRedemptionAdd` |
| `event_channel_update` | `ChannelUpdate` |
| `event_follow` | `ChannelFollow` |
| `event_ad_break` | `ChannelAdBreakBegin` |
| `event_cheer` | `ChannelCheer` |
| `event_raid` | `ChannelRaid` |
| `event_subscription` | `ChannelSubscribe` |
| `event_subscription_end` | `ChannelSubscriptionEnd` |
| `event_subscription_gift` | `ChannelSubscriptionGift` |
| `event_subscription_message` | `ChannelSubscriptionMessage` |
| `event_ban` / `event_unban` | `ChannelBan` / `ChannelUnban` |
| `event_unban_request` / `event_unban_request_resolve` | `ChannelUnbanRequest` / `ChannelUnbanRequestResolve` |
| `event_warning_send` / `event_warning_acknowledge` | `ChannelWarningSend` / `ChannelWarningAcknowledge` |
| `event_mod_action` | `ChannelModerate` |
| `event_moderator_add` / `event_moderator_remove` | `ChannelModeratorAdd` / `ChannelModeratorRemove` |
| `event_vip_add` / `event_vip_remove` | `ChannelVIPAdd` / `ChannelVIPRemove` |
| `event_automatic_redemption_add` | `ChannelPointsAutoRedeemAdd` |
| `event_custom_reward_add` / `_update` / `_remove` | `ChannelPointsRewardAdd` / `Update` / `Remove` |
| `event_custom_redemption_add` / `_update` | `ChannelPointsRedemptionAdd` / `Update` |
| `event_poll_begin` / `_progress` / `_end` | `ChannelPollBegin` / `Progress` / `End` |
| `event_prediction_begin` / `_progress` / `_lock` / `_end` | `ChannelPrediction*` |
| `event_suspicious_user_message` / `_update` | `SuspiciousUserMessage` / `SuspiciousUserUpdate` |
| `event_charity_campaign_start` / `_progress` / `_stop` / `_donate` | `CharityCampaign*` / `CharityCampaignDonation` |
| `event_goal_begin` / `_progress` / `_end` | `GoalBegin` / `Progress` / `End` |
| `event_hype_train` / `_progress` / `_end` | `HypeTrainBegin` / `Progress` / `End` |
| `event_shield_mode_begin` / `_end` | `ShieldModeBegin` / `End` |
| `event_shoutout_create` / `_receive` | `ShoutoutCreate` / `ShoutoutReceive` |
| `event_shared_chat_begin` / `_update` / `_end` | `SharedChatSessionBegin` / `Update` / `End` |
| `event_stream_online` / `event_stream_offline` | `StreamOnline` / `StreamOffline` |
| `event_user_update` | `UserUpdate` |
| `event_user_authorization_grant` / `_revoke` | `UserAuthorizationGrant` / `Revoke` |

> 2.x → 3.x：payload 使用者一律為 `PartialUser` 物件（`.id` / `.name`），非扁平 `event.broadcaster_user_id` 字串。

### `ChatMessage` 屬性

`broadcaster: PartialUser`、`chatter: PartialUser`、`id: str`、`text: str`、
`type: Literal["text","channel_points_highlighted","channel_points_sub_only","user_intro","power_ups_message_effect","power_ups_gigantified_emote"]`、
`reply: ChatMessageReply | None`、`fragments`、`colour: Colour | None`、
`channel_points_id: str | None`、`channel_points_animation_id: str | None`、`cheer: ChatMessageCheer | None`、
`badges: list[ChatMessageBadge]`、`source_broadcaster: PartialUser | None`、`source_id: str | None`、
`source_badges`、`source_only: bool | None`。
方法：`await msg.delete()`、`await msg.pin()` / `update_pin()` / `unpin()`（3.3.0+）。

### `StreamOnline` / `StreamOffline`

| Payload | 屬性 |
| ------- | ---- |
| `StreamOnline` | `broadcaster: PartialUser`、`id: str`、`type`（`"live"`\|`"playlist"`\|`"watch_party"`\|`"premiere"`\|`"rerun"`）、`started_at: datetime` |
| `StreamOffline` | `broadcaster: PartialUser`（無其他欄位） |

---

## 資料查詢（節錄）

```python
# 使用者
await bot.fetch_users(ids=[...], logins=[...])        # -> list[User]
bot.create_partialuser(user_id, user_login=None)     # 建 PartialUser（不打 API）

# 開台狀態
await partial_user.fetch_stream()                    # -> Stream | None（可 await）
bot.fetch_streams(*, user_ids=None, user_logins=None, game_ids=None,
                  languages=None, type="all")        # -> HTTPAsyncIterator[Stream]（async for）

# Stream 屬性: user(PartialUser), game_id, game_name(str|None), type, title,
#              viewer_count(int), started_at(datetime), language, thumbnail_url, tags, is_mature

# 頻道 / 遊戲 / clips
await bot.fetch_channels(broadcaster_ids=[...])
await bot.fetch_game(id=None, name=None, igdb_id=None)
bot.fetch_top_games()                                # HTTPAsyncIterator
partial_user.fetch_clips(...)                        # HTTPAsyncIterator
```

> `token_for=None`（3.3.0+）在多數 Helix 方法上 = 明確使用預設 app token。

---

## PartialUser 傳訊 / 版務（節錄）

```python
await user.send_message(message, sender, *, token_for=None, reply_to_message_id=None, pin=False)
await user.send_announcement(*, moderator, message, color=None)
await user.send_shoutout(*, to_broadcaster, moderator, token_for=MISSING)
await user.ban_user(...) / user.timeout_user(...) / user.unban_user(...)
await user.fetch_channel_info() / user.fetch_followers(...) / user.fetch_moderators(...)
await user.fetch_custom_rewards(...) / user.create_custom_reward(...)
await user.fetch_pinned_message() / user.pin_message(...) / user.unpin_message(...)   # 3.3.0+
```

`bot.http`：公開 property（3.3.0+）。優先使用模型方法，僅在缺少對應封裝時才用 `bot.http`。

---

## Token 管理

```python
await bot.add_token(token, refresh)     # -> ValidateTokenPayload
await bot.remove_token(user_id)         # -> TokenMappingData | None
await bot.load_tokens(path=None)        # 預設 .tio.tokens.json
await bot.save_tokens(path=None)
bot.tokens                              # 目前管理中的映射
```

覆寫 `load_tokens` / `save_tokens` 改用 DB：

```python
async def load_tokens(self, path: str | None = None) -> None:
    async for row in db.fetch("SELECT token, refresh FROM tokens"):
        await self.add_token(row["token"], row["refresh"])

async def save_tokens(self, path: str | None = None) -> None:
    for uid, data in self.tokens.items():
        await db.execute("INSERT ... ON CONFLICT ...", uid, data.token, data.refresh)
```

---

## Routines（`twitchio.ext.routines`）

```python
@routines.routine(*, delta=None, time=None, name=None, iterations=None,
                  wait_first=False, wait_remainder=False, max_attempts=5, stop_on_error=False)
```

| 參數 | 說明 |
| ---- | ---- |
| `delta` / `time` | 間隔（`timedelta`）**或** 每日時間（`datetime`）；互斥、擇一必填 |
| `iterations` | 執行次數上限（`None` = 無限） |
| `wait_first` | 首次執行前先等一個週期（預設 `False` = 立即跑第一次） |
| `wait_remainder` | 只等「到下次排程的剩餘時間」 |
| `max_attempts` | 連續錯誤上限（預設 5） |
| `stop_on_error` | 遇未處理錯誤即停止 |

```python
r.start(*args, **kwargs)   # -> asyncio.Task；args 轉傳給 callback
r.stop()                   # 跑完當前迭代後停止
r.cancel()                 # 立即取消
r.restart(*, force=True)
r.change_interval(delta=..., time=...)

@r.before_routine / @r.after_routine / @r.error
```

---

## 更新紀錄重點（3.2.0 → 3.3.2）

- **3.3.2 / 3.3.1**：bugfix（pin 端點改用 query params、duration 修正）。
- **3.3.0**：Device Code Flow（`login_dcf` / `start_dcf`，`client_secret`、`bot_id` 變選填）；
  `Client.http` 公開 property；`token_for=None` 於多數 Helix 方法 = 預設 app token；
  指令可由 reply 觸發；Pinned Message API、Suspicious Chat User API、Custom Powerup；
  `CustomPowerupRedeemAddSubscription` / `event_custom_power_up_redemption_add`；
  `moderator` 屬性對 Lead Moderator 回傳 `True`；`send_message` 加 `pin` 參數。
- **3.2.0**：`UserAuthorisation` 模型、`fetch_auth` / `fetch_auth_by_users`；
  `PartialUser.fetch_stream()`（單數 helper）；`fetch_hype_train_status`（取代 `fetch_hype_train_events`）；
  `Chatter.lead_moderator` 屬性 + `commands.is_lead_moderator()` 守衛；
  `ChatMessage.delete()` / `Chatter.delete_message()`；`Scopes.from_url()`；
  `create_clip(has_delay=...)` 已棄用。
