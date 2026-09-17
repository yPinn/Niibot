# Niibot 文件

依用途分五類。找「怎麼動手」看 `guides/`，找「某個值是什麼」看 `reference/`，
找「為什麼這樣設計」看 `architecture/`，找可 review 的設計樣本看 `examples/`。

## architecture/ — 系統設計

| 文件                                                                                      | 內容                                                                    |
| ----------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| [overview.md](architecture/overview.md)                                                   | 服務拓樸、跨程序訊號、AI provider 鏈、部署拓樸、資料流範例              |
| [admission-and-tenancy.md](architecture/admission-and-tenancy.md)                         | 身分／入會／多租戶三層拆分、狀態機、schema rollout（migration 076–084） |
| [bot-accounts-and-collaboration.md](architecture/bot-accounts-and-collaboration.md)       | Bot OAuth、租戶私有帳號、Owner／MOD、Twitch MOD 同步的目標架構          |
| [attendance-and-community-overlays.md](architecture/attendance-and-community-overlays.md) | 被動出席、主動簽到與社群 Overlay 的資料邊界                             |
| [roleplay-character-system-v1.md](architecture/roleplay-character-system-v1.md)           | 角色系統 V1、非技術建立流程、runtime 摘要、OOC 與分享邊界               |

## guides/ — 操作步驟

| 文件                                    | 內容                                                             |
| --------------------------------------- | ---------------------------------------------------------------- |
| [development.md](guides/development.md) | 本機把服務跑起來：env 範本、`uv`、`npm`、Docker Compose profiles |
| [deployment.md](guides/deployment.md)   | 三環境 Compose overlay、CI/CD 密鑰同步、`staging.sh`、版本標記   |
| [environment.md](guides/environment.md) | 所有環境變數檔案的唯一總表                                       |

## reference/ — 查詢用

| 文件                                           | 內容                                     |
| ---------------------------------------------- | ---------------------------------------- |
| [api-endpoints.md](reference/api-endpoints.md) | Dashboard API 路由前綴與安全機制         |
| [static-data.md](reference/static-data.md)     | `backend/data/` 靜態檔案與 AI 知識包格式 |
| [versioning.md](reference/versioning.md)       | 版本號規範（`git describe` 衍生）        |

## integrations/ — 外部／旁掛服務

| 文件                                      | 內容                                      |
| ----------------------------------------- | ----------------------------------------- |
| [instafix.md](integrations/instafix.md)   | Instagram OG proxy（Docker 服務）         |
| [fixtweet.md](integrations/fixtweet.md)   | X／Twitter OG proxy（Cloudflare Workers） |
| [scrapling.md](integrations/scrapling.md) | Threads 抓取 sidecar                      |

## examples/ — 設計範例

| 文件                                                                    | 內容                                                     |
| ----------------------------------------------------------------------- | -------------------------------------------------------- |
| [roleplay/rem-character-set.md](examples/roleplay/rem-character-set.md) | 以雷姆驗證世界優先、故事進度、角色所知與演繹摘要的設定集 |
