# 指令匯入、匯出與跨 Bot 相容性

## 支援邊界

| 來源           | 入口             | 可保留                                                        | 必須複核                                                                                                      |
| -------------- | ---------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Nightbot       | OAuth 唯讀匯入   | 自訂回應、別名轉呼叫、最低身分、冷卻、預設指令啟用狀態        | 不支援的變數、Regular 近似角色、預設指令語意差異                                                              |
| StreamElements | 公開頻道資料匯入 | 自訂回應、aliases、keywords、最低身分、冷卻、預設指令啟用狀態 | 忠誠點數、whisper、remote API／具名計數器、Regular／Super Moderator 近似角色、followage／quote 語意與資料差異 |
| Fossabot       | CSV              | 公開文件能人工匯出的自訂指令文字                              | 尚無可核實的官方 export schema／API，故不猜測直接 adapter                                                     |
| ChiwaBots      | CSV              | 官方通用 `command,response` 格式                              | backup 內部 command schema 未公開；沒有去識別化真實 fixture 前不解析 ZIP 內容                                 |
| 其他 Bot       | CSV              | `command,response`，以及下列 Niibot 選用欄位                  | 來源專屬變數、腳本、點數、媒體與管理操作                                                                      |

參考來源：

- [Nightbot Commands](https://docs.nightbot.tv/control-panel/commands)
- [Nightbot !winner](https://docs.nightbot.tv/commands/winner)
- [StreamElements Default Commands](https://docs.streamelements.com/chatbot/commands/default)
- [StreamElements !level](https://docs.streamelements.com/chatbot/commands/default/level)
- [StreamElements !followage](https://docs.streamelements.com/chatbot/commands/default/followage)
- [StreamElements !quote](https://docs.streamelements.com/chatbot/commands/default/quote)
- [Fossabot Default Commands](https://docs.fossabot.com/commands/default/)
- [Fossabot Creating Commands](https://docs.fossabot.com/commands/Creating-Commands/)
- [ChiwaBots CSV Import](https://chiwabots.com/docs/import/)
- [ChiwaBots Backup](https://chiwabots.com/docs/backup/)

## CSV 契約

檔案必須是 UTF-8 CSV，大小上限 512 KiB、最多 500 筆。必要欄位只有：

```csv
command,response
discord,加入 Discord：https://example.com
```

Niibot 完整格式另支援：

```csv
niibot_version,command,response,enabled,min_role,cooldown,aliases
1,discord,加入 Discord：https://example.com,false,everyone,15,dc|社群
```

| 欄位             | 規則                                                                                                                                                                          |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `niibot_version` | Niibot 匯出目前為 `1`；用來安全還原為避免試算表公式注入而加上的前置 `'`。未知版本會拒絕，不猜測解碼。原文若本來就是 `'=` 等形式，匯出會加成 `''=`，重新匯入仍保留原本單引號。 |
| `command`        | 必填；可含或不含 `!`，匯入時會正規化。                                                                                                                                        |
| `response`       | 必填；最長 450 字。任何 eval、remote API 或不支援變數都只會顯示在預覽，不會寫入 runtime。                                                                                     |
| `enabled`        | 選填；接受 true/false、1/0、yes/no、on/off、enabled/disabled。未提供時安全預設停用。                                                                                          |
| `min_role`       | 選填；`everyone`、`subscriber`、`vip`、`moderator`、`broadcaster`。未提供或無法辨識時設為 broadcaster 並要求複核。                                                            |
| `cooldown`       | 選填；0–86400 秒。未提供時使用頻道預設。                                                                                                                                      |
| `aliases`        | 選填；以 `\|`、`;` 或 `,` 分隔。撞到內建、runtime 或其他列的名稱會略過該 alias 並標示。                                                                                       |

匯出只包含自訂指令，不包含 Niibot builtin 或關鍵字觸發器。輸出採 UTF-8 BOM，且所有可能被試算表當成公式的文字都會先中和；Niibot 自己重新匯入時會依 `niibot_version` 無損還原。

## 預設指令轉換

### Nightbot

| Nightbot                                             | Niibot       | 判定                                                                                    |
| ---------------------------------------------------- | ------------ | --------------------------------------------------------------------------------------- |
| `commands`                                           | `help`       | REVIEW：只保留指令列表；Nightbot 的新增／編輯／刪除子指令不轉換，觸發名稱改為 `!help`。 |
| `game`、`title`、`tags`                              | 同名 builtin | 保留 everyone 查詢；修改仍由 Niibot handler 強制 Mod 以上。                             |
| `marker`                                             | `marker`     | 保留冷卻，但最低身分不得低於 moderator；仍需直播中、開啟 VOD、非 rerun／premiere。      |
| `winner`                                             | `winner`     | REVIEW：Nightbot 從近 10 分鐘發言者抽選；Niibot 從目前 Twitch chatters 名單抽選。       |
| `commercial`、`filters`、`poll`、`regulars`、`songs` | 無           | UNSUPPORTED：不把不同功能硬套成相似名稱。                                               |

### StreamElements

目前只把 `accountage`、`commands`、`followage`、`quote`、`uptime` 與 `vanish → del`
視為可接受的 builtin 對應。`followage` 一律標為 REVIEW，因 StreamElements 可指定其他使用者與頻道，
而 Niibot 只查發話者在目前頻道的追隨時間。`quote` 也一律 REVIEW：匯入只會啟用 Niibot 的空白語錄庫，
不會搬移 StreamElements 已保存的語錄，指定編號與移除子指令也不完全相同。點數、watchtime、raffle、
song request、store、overlay、`settitle`、`setgame` 等平台功能不會因名稱相近就轉成 Niibot 指令。

所有來源的 command name 與 alias 都在預覽階段對照同一份 Niibot namespace；跨列、既有自訂指令、
builtin alias 或 runtime 管理指令發生衝突時，不會等到套用後才靜默遺失。舊版資料若已占用 builtin
canonical name，migration 會改成可辨識的 `__legacy_*` 名稱並停用，保留回覆與 aliases 供人工復原。

### Fossabot

公開文件顯示 `commands`、`uptime`、`accountage`、`title` 與 `vanish` 有直接或接近的 Niibot 對應；
`game` 額外回傳遊玩時間／Steam 連結，`followage` 可查任意兩位使用者，若日後有可核實的 export schema，
這兩項必須標為 REVIEW。`clip`、media requests、nuke、votekick、dictionary、counter 與
command-management 類不應自動對應。

截至 2026-09-29，Fossabot 公開文件沒有提供可驗證的 custom-command export schema 或 API contract，因此 Niibot 只提供 CSV mapping guide，不實作猜測式 adapter。

### ChiwaBots backup

官方只保證 backup 是可改副檔名後開啟的壓縮封裝，並未公開 command section 的檔名、版本或欄位 schema。
Niibot 保留既有的 bounded ZIP validator，但沒有去識別化真實 fixture 與 schema version gate 前，
不讀取或猜測其中指令資料。可先使用 ChiwaBots 官方支援的 `command,response` CSV 再匯入 Niibot。
