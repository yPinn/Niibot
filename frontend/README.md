# Frontend

React SPA，部署在 Cloudflare Pages。CF Pages Functions 將 `/api/*`、`/health`、`/status` 代理到後端 API，瀏覽器全程只與 CF Pages 域名通訊。

> 以下所有指令均在 `frontend/` 目錄下執行。

## 技術棧

- **React 19 + TypeScript 5.9**：UI 框架與型別系統
- **Vite 7**（SWC）+ **React Router 7**：建置工具與客戶端路由
- **Tailwind CSS 4**：原子 CSS 樣式
- **shadcn/ui**（基於 Radix UI）：UI 元件庫、主題切換、Toast
- **Recharts**：數據圖表
- **Vitest + Testing Library**：單元測試

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

## 部署

推送到 GitHub 後由 Cloudflare Pages 自動建置。

| 項目          | 值                                                   |
| ------------- | ---------------------------------------------------- |
| Build command | `npm run build`                                      |
| Build output  | `dist`                                               |
| 環境變數      | `API_BACKEND`（後端位址，由 Cloudflare Tunnel 提供） |

Production build 自動移除所有 `console.*` 與 `debugger`（`esbuild.drop`）。
