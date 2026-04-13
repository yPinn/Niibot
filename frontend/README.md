# Frontend

React SPA，部署在 Cloudflare Pages。CF Pages Functions 將 `/api/*`、`/health`、`/status` 代理到後端 API，瀏覽器全程只與 CF Pages 域名通訊。

> 以下所有指令均在 `frontend/` 目錄下執行。

## 前置需求

- Node.js 20+

## 開發

```bash
npm install
npm run dev   # Vite dev server（localhost:3000）
```

連接後端時在 `.env` 設定（未設定則 proxy 指向 `localhost:8000`）：

```env
VITE_API_URL=http://localhost:8000
```

## 指令

```bash
npm run build          # TypeScript 型別檢查 + Vite build
npm run lint           # ESLint
npm run format         # Prettier 格式修正（寫入）
npm run format:check   # Prettier 格式檢查（唯讀，CI 用）
npm run test           # Vitest（watch mode）
npm run test:coverage  # 測試 + 覆蓋率報告（閾值 80%）
```

## 結構

路徑別名 `@/` 指向 `src/`（定義於 `vite.config.ts`）。

```text
src/
├── api/            # API client — apiFetch、端點常數、各模組請求函式
├── components/
│   ├── ui/         # shadcn-style 基礎元件（Button、Card、Sidebar…）
│   ├── layouts/    # SidebarLayout（Dashboard 頁面外框）
│   └── ...         # 業務元件（AnalyticsChart、ProtectedRoute、ErrorBoundary…）
├── contexts/
│   ├── AuthContext.tsx          # 認證狀態、user、channels、401 全域攔截
│   ├── BotContext.tsx           # 目前活躍的 Bot 平台（twitch / discord）
│   └── ServiceStatusContext.tsx # Twitch / Discord / API 服務狀態（30s polling）
├── config/         # navigation.ts — Twitch 與 Discord sidebar 導覽設定
├── hooks/          # usePolling、useSortState、useBreadcrumbs、useDocumentTitle…
├── lib/
│   ├── apiCache.ts # 記憶體內 TTL 快取 + 請求合併（deduplication）
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
/                             → Landing（公開）
/:username/commands           → PublicCommands（公開）
/donate/:username             → DonatePage（公開）
/:username/{game,video}-queue/overlay → Overlay（OBS browser source）
/login                        → PublicOnlyRoute（已登入者重導）
/dashboard, /commands…        → ProtectedRoute → SidebarLayout
```

Overlay 路由使用 `<Suspense fallback={null}>`，避免 chunk 載入時對 OBS 瀏覽器來源顯示 spinner。

### Context 提供者順序

```text
AuthProvider
  └── ThemeProvider
        └── ServiceStatusProvider   ← 依賴 user，auth 後才開始 polling
              └── BotProvider       ← 依賴 user，決定 activeBot 平台
                    └── ErrorBoundary
```

### apiFetch 行為

- 503 自動重試一次（間隔 1.5 秒）
- 401 觸發全域 `auth:unauthorized` 自訂事件 → `AuthContext` 清除狀態並跳轉 `/login`

## 技術棧

### 核心

| 套件                              | 版本 | 用途               |
| --------------------------------- | ---- | ------------------ |
| React                             | 19   | UI 框架            |
| TypeScript                        | ~5.9 | 型別系統           |
| Vite + `@vitejs/plugin-react-swc` | 7    | 建置工具，SWC 編譯 |
| React Router v7                   | 7.10 | 客戶端路由         |

### 樣式

| 套件                                  | 版本 | 用途                     |
| ------------------------------------- | ---- | ------------------------ |
| Tailwind CSS v4 + `@tailwindcss/vite` | 4.1  | 原子 CSS，Vite plugin    |
| `tw-animate-css`                      | 1.4  | Tailwind v4 動畫類別     |
| `clsx` + `tailwind-merge`             | —    | className 合併           |
| `motion`                              | 12   | 動畫（預計引入，未使用） |

### UI 元件

| 套件                           | 版本   | 用途             |
| ------------------------------ | ------ | ---------------- |
| Radix UI (`@radix-ui/react-*`) | 各版本 | 無障礙原語元件   |
| `class-variance-authority`     | 0.7    | 元件 variant API |
| `next-themes`                  | 0.4    | 深色／淺色主題   |
| `sonner`                       | 2.0    | Toast 通知       |
| `recharts`                     | 3.7    | 數據圖表         |

### 測試

| 套件                              | 版本 | 用途     |
| --------------------------------- | ---- | -------- |
| Vitest + `@testing-library/react` | 4.0  | 單元測試 |

## 部署

推送到 GitHub 後由 Cloudflare Pages 自動建置。

| 項目          | 值                                                   |
| ------------- | ---------------------------------------------------- |
| Build command | `npm run build`                                      |
| Build output  | `dist`                                               |
| 環境變數      | `API_BACKEND`（後端位址，由 Cloudflare Tunnel 提供） |

Production build 自動移除所有 `console.*` 與 `debugger`（`esbuild.drop`）。
