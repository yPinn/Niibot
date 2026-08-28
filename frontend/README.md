# Frontend

Niibot 的網頁控制台，部署在 Cloudflare Pages。CF Pages Functions 將 `/api/*`、`/health`、`/status` 代理到後端 API，瀏覽器全程只與 CF Pages 域名通訊。

> 以下所有指令均在 `frontend/` 目錄下執行。

## 技術棧

| 工具                       | 用途                            |
| -------------------------- | ------------------------------- |
| React 19 + TypeScript      | UI 框架與型別系統               |
| Vite（SWC）+ React Router  | 建置工具與頁面路由              |
| Tailwind CSS 4             | 樣式系統                        |
| shadcn/ui（基於 Radix UI） | UI 元件庫（按鈕、卡片、側欄等） |
| Motion                     | 動畫與轉場                      |
| Recharts                   | 數據圖表                        |
| Vitest + Testing Library   | 自動化測試                      |

精確版本見 `package.json`。

## 前置需求

- Node.js — 版本見 `.nvmrc`

## 開發

```bash
npm install     # 安裝套件（第一次或更新後執行）
npm run dev     # 啟動開發伺服器（localhost:3000）
```

連接本機後端時，在 `frontend/` 建立 `.env`（參考 `.env.example`）：

```env
VITE_API_URL=http://localhost:8000  # 後端代理目標（預設 localhost:8000）
VITE_BOT_USERNAME=niibot_           # Bot 帳號名，抑制自身的「授予 Mod」提示
VITE_DISCORD_COMMUNITY_URL=         # Discord 社群邀請連結（側欄／說明橫幅／條款頁）
VITE_DISCORD_BOT_INVITE_URL=        # 把 Bot 加入自己伺服器的 OAuth 連結
VITE_SUPPORT_ECPAY_URL=             # 贊助頁 ECPay 連結
VITE_ENVIRONMENT=                   # 部署環境：production 鎖定 WIP 頁面；staging/dev 不鎖
```

完整欄位說明見 [docs/guides/environment.md](../docs/guides/environment.md)。

> 部署時於 Cloudflare Pages 設定：staging 須明確設 `VITE_ENVIRONMENT=staging` 才解鎖；
> 未設定者一律保持鎖定（fail-safe）。

## 指令

| 指令                   | 說明                          |
| ---------------------- | ----------------------------- |
| `npm run build`        | 打包正式版本（含型別檢查）    |
| `npm run preview`      | 本機預覽打包結果              |
| `npm run typecheck`    | 只執行型別檢查，不打包        |
| `npm run lint`         | 掃描程式碼問題                |
| `npm run lint:fix`     | 自動修正程式碼問題            |
| `npm run format`       | 修正排版格式                  |
| `npm run format:check` | 只檢查格式，不修改（CI 用）   |
| `npm run test`         | 執行測試（存檔自動重跑）      |
| `npm run test:cov`     | 測試＋覆蓋率報告（目標 80%+） |

## 結構

路徑別名 `@/` 指向 `src/`（定義於 `vite.config.ts`）。

```text
src/
├── api/            # API client — apiFetch、端點常數、各模組請求函式
├── components/
│   ├── ui/         # shadcn/ui 元件（Button、Card、Sidebar…）
│   ├── layouts/    # SidebarLayout（Dashboard 頁面外框）
│   └── ...         # 業務元件（PageHeader、AnalyticsChart、ProtectedRoute、ErrorBoundary…）
├── contexts/
│   ├── AuthContext.tsx          # 認證狀態、user、channels、401 全域攔截
│   ├── BotContext.tsx           # 目前活躍的 Bot 平台（twitch / discord）
│   └── ServiceStatusContext.tsx # Twitch / Discord / API 服務狀態（30s polling）
├── config/         # navigation.ts — Twitch 與 Discord sidebar 導覽設定
├── hooks/          # usePolling、useSortState、useOptimisticToggle、useInputInsert、
│                   #   useAbortableFetch、useBreadcrumbs、useDocumentTitle、useGrantMod、useOnboardingStatus
├── lib/
│   ├── apiCache.ts  # 記憶體內 TTL 快取（上限 200 條）+ 請求合併；CACHE_KEYS 集中管理所有快取鍵
│   ├── sort.ts      # 通用排序工具（nameSort、ROLE_ORDER）
│   ├── format.ts    # 日期時間格式化輔助函式
│   ├── sanitize.ts  # DOMPurify 包裝（ANSI HTML 消毒，用於 Admin Monitor）
│   ├── clipboard.ts # Clipboard API 複製工具
│   ├── motion.ts    # Motion 共用動畫 variant
│   ├── insights-suggestions.ts  # Insights 頁的建議行動推導
│   ├── onboarding-status.ts     # 設定完成度判斷
│   └── utils.ts     # cn()（Tailwind class 合併）
├── pages/
│   ├── dashboard/  # Twitch Bot（Commands、Events、Overview、Timers）
│   ├── modules/    # AI、ChatOverlay、GameQueue、VideoQueue、Crosshairs
│   ├── analytics/  # Insights（觀眾分析）、Matcher（頻道重疊分析）
│   ├── discord/    # Discord Dashboard
│   ├── crosshairs/ # 公開準星庫（/:username/crosshairs）
│   ├── admin/      # 管理員頁面（OwnerRoute）
│   ├── activate/   # 啟用碼頁面
│   ├── docs/       # GetStarted、Releases
│   └── ...         # Landing、Login、PublicCommands、Overlays、Settings、DonatePage、Support、NotFound
└── test/           # Vitest 設定（setup.ts）
functions/          # CF Pages Functions — /api/*、/health、/status 反向代理
```

### 路由架構

```text
公開路由
  /                              Landing
  /terms, /privacy               Terms / Privacy
  /:username/commands            PublicCommands
  /:username/crosshairs          CrosshairRepo（公開準星庫）
  /donate/:username              DonatePage
  /:username/game-queue/overlay  GameQueueOverlay（OBS browser source）
  /:username/video-queue/overlay VideoQueueOverlay（OBS browser source）
  /activate                      ActivatePage（啟用碼）
  /support                       Support（贊助頁）
  /login                         LoginPage（PublicOnlyRoute，已登入者重導）
  *                              NotFound（404）

ProtectedRoute → SidebarLayout（需登入）
  /dashboard                     Overview
  /commands                      Commands（內建 / 自訂指令）
  /events                        Events（EventSub / 點數兌換綁定）
  /analytics/insights            Insights（觀眾分析）
  /analytics/matcher             Matcher（頻道觀眾重疊分析）
  /settings                      Settings（斗內金流設定）
  /timers                        Timers
  /modules/game-queue            GameQueue（遊戲排隊管理）
  /modules/video-queue           VideoQueue（YouTube 點播管理）
  /modules/crosshairs            CrosshairModule（準星管理）
  /modules/ai                    AIModule（AI 助手設定）
  /discord                       DiscordDashboard
  /docs/get-started              GetStarted
  /docs/releases                 Releases（版本更新說明）

OwnerRoute（限擁有者）
  /admin                         AdminPage
  /admin/monitor                 AdminMonitor
  /admin/modules                 AdminModules

/dev/typography                  TypographyDemo（僅開發用）
```

## 部署

推送至 GitHub 後由 Cloudflare Pages 自動建置發布。

| 項目       | 值                                                   |
| ---------- | ---------------------------------------------------- |
| 建置指令   | `npm run build`                                      |
| 輸出資料夾 | `dist`                                               |
| 環境變數   | `API_BACKEND`（後端網址，由 Cloudflare Tunnel 提供） |

Production build 自動移除所有 `console.*` 與 `debugger`（`esbuild.drop`）。
