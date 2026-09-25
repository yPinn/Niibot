# Discord

Niibot 使用兩個 Discord Application：production 一個，dev／staging 共用一個 nonprod
Application。dev 與 staging 不可同時啟動同一個 Bot token，避免兩個 Gateway session
重複處理事件。

## Developer Portal

兩個 Application 都依下列方式設定；名稱、圖示與 description 直接在 Portal 維護，不由 runtime
修改。

### Installation

- Installation Contexts：只開 **Guild Install**。
- Install Link：選 **Discord Provided Link**。
- Default Install Settings scopes：`bot`、`applications.commands`。
- production 若要讓網站使用者安裝，**Public Bot** 開啟；nonprod 關閉，只加入測試 guild。
- **Requires OAuth2 Code Grant** 關閉。本專案沒有 Discord user OAuth code exchange。
- OAuth2 Redirects 留空；安裝 Bot 不需要 localhost 或公開 callback。

Bot 權限不授予 Administrator，依功能選取：

- View Channels、Send Messages、Send Messages in Threads
- Embed Links、Attach Files、Read Message History
- Manage Messages
- View Audit Log
- Manage Channels、Manage Roles
- Kick Members、Ban Members、Moderate Members

Manage Channels／Roles 用於生日功能自動建立資源；Moderation 權限用於 `/mod`。Bot role
仍需位於要管理的 role／member 上方。

### Bot

- Server Members Intent：開啟。
- Message Content Intent：開啟。
- Presence Intent：關閉。

Members intent 供加入／離開、role、生日與 moderation；Message Content intent 供訊息日誌、
社群連結預覽與 `$` prefix 指令。程式沒有訂閱 presence event。

### Endpoints

- Interactions Endpoint URL：留空。Slash commands 由 discord.py Gateway 接收。
- Webhook Events：預設關閉；現有功能不依賴它。

若日後需要 Application／Entitlement Webhook Events，才設定：

```text
<API_URL>/api/discord/webhook
```

並把 Portal General Information 的 Public Key 寫入該環境 GitHub Variable
`DISCORD_PUBLIC_KEY`。Public Key 不是 secret。Endpoint 會驗證 Ed25519 signature，並依 Discord
契約對 PING 與 Event 回覆 `204` 空內容。

## 環境值

| 值                            | production                      | nonprod（dev／staging）               |
| ----------------------------- | ------------------------------- | ------------------------------------- |
| `DISCORD_BOT_TOKEN`           | production Bot token（Secret）  | nonprod Bot token（Secret）           |
| `DISCORD_PUBLIC_KEY`          | Webhook Events 啟用時才填       | Webhook Events 啟用時才填             |
| `VITE_DISCORD_BOT_INVITE_URL` | production Discord Install Link | nonprod Discord Install Link          |
| `DISCORD_GUILD_ID`            | 不設定；production 用 global    | 本機 dev 可填；staging CLI 用參數指定 |

`VITE_DISCORD_BOT_INVITE_URL` 是公開值，分別放在 Cloudflare Pages Production 與 Preview
環境。Discord token 放 GitHub environment Secret，不放 Cloudflare、不加引號。

## 指令發布

Bot 啟動不會自動同步 commands。先在 nonprod test guild 驗證，再發布 production global：

```bash
# staging：在目標 Discord container 內使用 nonprod token
npm run nb -- discord diff --env stg --guild <test-guild-id>
npm run nb -- discord sync --env stg --guild <test-guild-id>

# production：staging 驗證完成後才更新 global commands
npm run nb -- discord diff --env prod --global
npm run nb -- discord sync --env prod --global
```

dev 指令在本機執行；stg／prod 指令只會在所選 Compose project 的 `discord-bot`
container 執行，不讀 host 上的部署 token。`rm` 只清除明確選取的 guild 或 global scope。

## Rate limit

Discord REST limit 會依 route、resource 與 global bucket 改變，不在應用程式硬編碼。
discord.py 會讀取 rate-limit headers 並依 `retry_after` 排隊；Niibot 另外避免在 restart／reconnect
時同步 commands 或更新 Application metadata。若將來出現大量 fan-out 工作，再對該工作加入有界
queue／concurrency，而不是建立一個推估全域用量的計數器。

官方參考：

- [Application installation](https://docs.discord.com/developers/resources/application#install-links)
- [Gateway intents](https://docs.discord.com/developers/events/gateway#gateway-intents)
- [Application commands](https://docs.discord.com/developers/interactions/application-commands)
- [Webhook Events](https://docs.discord.com/developers/events/webhook-events)
- [Rate limits](https://docs.discord.com/developers/topics/rate-limits)
