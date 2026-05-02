# Frontend

Niibot 的網頁控制台，部署在 Cloudflare Pages。CF Pages Functions 將 `/api/*`、`/health`、`/status` 代理到後端 API，瀏覽器全程只與 CF Pages 域名通訊。

> 以下所有指令均在 `frontend/` 目錄下執行。

## 技術棧

| 工具                          | 用途                            |
| ----------------------------- | ------------------------------- |
| React 19 + TypeScript 5.9     | UI 框架與型別系統               |
| Vite 7（SWC）+ React Router 7 | 建置工具與頁面路由              |
| Tailwind CSS 4                | 樣式系統                        |
| shadcn/ui（基於 Radix UI）    | UI 元件庫（按鈕、卡片、側欄等） |
| Recharts                      | 數據圖表                        |
| Vitest + Testing Library      | 自動化測試                      |

## 前置需求

- [Node.js 22+](https://nodejs.org/)

## 開發

```bash
npm install     # 安裝套件（第一次或更新後執行）
npm run dev     # 啟動開發伺服器（localhost:3000）
```

連接本機後端時，在 `frontend/` 建立 `.env`（預設代理至 `localhost:8000`）：

```env
VITE_API_URL=http://localhost:8000
```

## 指令

| 指令                    | 說明                          |
| ----------------------- | ----------------------------- |
| `npm run build`         | 打包正式版本（含型別檢查）    |
| `npm run preview`       | 本機預覽打包結果              |
| `npm run lint`          | 掃描程式碼問題                |
| `npm run lint:fix`      | 自動修正程式碼問題            |
| `npm run format`        | 修正排版格式                  |
| `npm run format:check`  | 只檢查格式，不修改（CI 用）   |
| `npm run test`          | 執行測試（存檔自動重跑）      |
| `npm run test:coverage` | 測試＋覆蓋率報告（目標 80%+） |

## 結構

路徑別名 `@/` 指向 `src/`（定義於 `vite.config.ts`）。

```text
src/
├── api/            # API client — apiFetch、端點常數、各模組請求函式
├── components/
│   ├── ui/         # shadcn/ui 元件（Button、Card、Sidebar…）
│   ├── layouts/    # SidebarLayout（Dashboard 頁面外框）
│   └── ...         # 業務元件（AnalyticsChart、ProtectedRoute、ErrorBoundary…）
├── contexts/
│   ├── AuthContext.tsx          # 認證狀態、user、channels、401 全域攔截
│   ├── BotContext.tsx           # 目前活躍的 Bot 平台（twitch / discord）
│   └── ServiceStatusContext.tsx # Twitch / Discord / API 服務狀態（30s polling）
├── config/         # navigation.ts — Twitch 與 Discord sidebar 導覽設定
├── hooks/          # usePolling、useSortState、useBreadcrumbs、useDocumentTitle…
├── lib/
│   ├── apiCache.ts # 記憶體內 TTL 快取（上限 200 條）+ 請求合併（deduplication）
│   └── sort.ts     # 通用排序工具
├── pages/
│   ├── dashboard/  # Twitch Bot（Commands、Events、Overview、SystemStatus）
│   ├── modules/    # Timers、GameQueue、VideoQueue
│   ├── discord/    # Discord Dashboard
│   ├── docs/       # GetStarted、Terms、Privacy
│   └── ...         # Landing、Login、PublicCommands、Overlays、Settings
└── test/           # Vitest 設定（setup.ts）
functions/          # CF Pages Functions — /api/*、/health、/status 反向代理
```

### 路由架構

```text
/                                     → Landing（公開）
/terms, /privacy                      → Terms / Privacy（公開）
/:username/commands                   → PublicCommands（公開）
/donate/:username                     → DonatePage（公開）
/:username/{game,video}-queue/overlay → Overlay（OBS browser source）
/login                                → PublicOnlyRoute（已登入者重導）
/docs                                 → ProtectedRoute → GetStarted
/discord/dashboard                    → ProtectedRoute → Discord Bot
/dashboard, /commands…                → ProtectedRoute → SidebarLayout
```

## 部署

推送至 GitHub 後由 Cloudflare Pages 自動建置發布。

| 項目       | 值                                                   |
| ---------- | ---------------------------------------------------- |
| 建置指令   | `npm run build`                                      |
| 輸出資料夾 | `dist`                                               |
| 環境變數   | `API_BACKEND`（後端網址，由 Cloudflare Tunnel 提供） |

Production build 自動移除所有 `console.*` 與 `debugger`（`esbuild.drop`）。
