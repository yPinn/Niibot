# 預設指令擴充評估

評估日期：2026-09-29。原則是只有「多數頻道都適用、語意穩定、權限與失敗行為可以在 Commands 頁說清楚」的功能才進 builtin；頻道品牌內容留在可編輯 preset，管理工作流留在 Dashboard。

## 不新增 Twitch scope 的候選

| 候選               | 現有資料／能力                                                          | 風險與限制                                                                                                                                                                 | 建議                                                                                                      |
| ------------------ | ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `!vod`／`!lastvod` | API 已有 public Get Videos client，session service 也會同步 archive VOD | 頻道可關閉 VOD；剛下播時 Twitch 可能尚未產生；需清楚區分「沒有 VOD」與 provider 暫時失敗                                                                                   | **優先新增**，預設關閉，viewer/everyone；回覆最近一支 archive 的標題與 Twitch URL，不快取失敗成「沒有」。 |
| `!watchtime`       | `chatter_stats.watch_seconds` 與 attendance projection 已存在           | 目前每 60 秒依完整 chatters snapshot 累加，是「聊天室在線估計」而非播放器觀看證明；還需要既有 bot `moderator:read:chatters` 與 Bot MOD，且大頻道 snapshot 完整性會影響資料 | **暫緩 builtin**；若做，名稱與文案必須稱「聊天室在線時間」，先補資料完整度、起算日與缺資料揭露。          |
| `!lastseen`        | `last_message_at`／viewer analytics 已存在                              | 會公開個人活動時間；需 retention、opt-out、刪除與封鎖查詢策略，也要防止騷擾用途                                                                                            | **不進 builtin**，先完成 privacy policy 與頻道／觀眾 opt-out。                                            |
| `!socials`         | 可由 custom command 直接回覆                                            | 每個頻道內容不同，沒有中央 handler 或外接能力的價值；硬做 builtin 只會增加空設定                                                                                           | **做可編輯 preset**，首次建立仍停用並讓使用者填 URL。                                                     |

`!vod` 可用現有 app/public Helix 路徑，不需要新增 user scope。Twitch Get Videos 與完整 endpoint contract 以
[Twitch API Reference](https://dev.twitch.tv/docs/api/reference) 為準。

## 需要新 scope 或運營能力的候選

| 候選         | Token subject／scope                                                                                                                | Twitch 條件                                                                    | 失敗與降級                                                                   | 建議                                                                                       |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `!clip`      | live Create Clip：user token + `clips:edit`；VOD clip 新 API：broadcaster/editor 的 `channel:manage:clips` 或 `editor:manage:clips` | 直播／分類必須允許 clip，頻道可限制 follower/subscriber，建立是非同步          | 202 Accepted 後需 bounded polling；不可先回覆假 URL；無權限時導向重新授權    | **第二優先、opt-in builtin**。先選 live Create Clip 單一路徑，不同時混入 VOD offset 編輯。 |
| poll         | broadcaster token + `channel:manage:polls`                                                                                          | Affiliate／Partner；同時只能一個；2–5 選項                                     | 已有 poll 時明確回覆；建立與結束需保存 poll id／狀態                         | **Dashboard workflow 優先**，不先做任意文字 chat command。                                 |
| prediction   | broadcaster token + `channel:manage:predictions`                                                                                    | Affiliate／Partner；同時只能一個；2–10 outcomes；Channel Points 有實際資產影響 | 未 resolve／cancel 會阻擋下一個，24 小時未處理才退點；需完整 lifecycle/audit | **不做簡單預設指令**，必須先有狀態 UI、確認與 audit。                                      |
| announcement | active sender 的 bot token + `moderator:manage:announcements`，Bot 必須為 Mod；或 broadcaster 自己授權並作 moderator_id             | 每頻道每 2 秒一則；Shared Chat 的傳送範圍依 token 類型不同                     | rate limit 時不降級成普通訊息以免誤導；需明確選色與 Shared Chat policy       | **可做 Mod 工具**，但等 bot selection／scope preflight 穩定後再納入。                      |

官方權限與限制：

- [Twitch Clips](https://dev.twitch.tv/docs/api/clips)
- [Twitch Polls](https://dev.twitch.tv/docs/api/polls)
- [Twitch Predictions](https://dev.twitch.tv/docs/api/predictions)
- [Twitch Send Chat Announcement](https://dev.twitch.tv/docs/api/reference#send-chat-announcement)
- [Twitch OAuth scopes](https://dev.twitch.tv/docs/authentication/scopes/)

## 升格為 builtin 的 gate

1. Handler、中央 catalog、runtime namespace、usage count 與 Commands API 必須同時登錄。
2. Catalog 必須宣告 token subject、capability key、整條／寫入／效果模式、Bot MOD 與直播情境。
3. 缺 credential／scope／MOD 時要能在 Commands 頁給出可行動提示；不自動改寫 enabled。
4. 外部 mutation 要有 rate limit、idempotency 或明確重試邊界，不能把 provider timeout 當成功。
5. 涉及個人行為資料時，先完成 retention、可見範圍、opt-out 與刪除政策。
6. 頻道專屬文字／連結若用 custom preset 已足夠，不新增 builtin handler。

依這些 gate，近期排序是：`!vod` → `!clip`（opt-in scope）→ announcement；`!watchtime`
先修正產品命名與資料揭露；poll／prediction 留在有狀態 UI 的管理流程；`!lastseen` 暫不做。
