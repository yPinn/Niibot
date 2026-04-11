# Frontend

React SPA，部署在 Cloudflare Pages。CF Pages Functions 將 `/api/*`、`/health`、`/status` 代理到後端 API，瀏覽器全程只與 CF Pages 域名通訊。

## 技術棧

- React 19 + TypeScript + Vite
- Tailwind CSS v4
- Vitest + @testing-library/react

## 結構

```text
src/
├── api/            # API client 函式（apiFetch、user、twitch、discord 等）
├── components/     # 共用 UI 元件
├── contexts/       # React Context（AuthContext）
├── hooks/          # 共用 hooks（usePolling、useSortState 等）
├── lib/            # 共用工具（apiCache、sort）
├── pages/          # 頁面元件
│   ├── dashboard/  # Twitch Bot dashboard（Commands、Events、Overview、SystemStatus）
│   ├── modules/    # 模組頁面（Timers、VideoQueue、GameQueue）
│   ├── discord/    # Discord dashboard
│   └── ...         # 公開頁面（PublicCommands、Settings、Overlays）
└── test/           # 測試設定（setup.ts）
functions/          # CF Pages Functions — API 反向代理
```

## 前置需求

- Node 20+

> 以下所有指令均在 `frontend/` 目錄下執行。

## 開發

```bash
cd frontend
npm install
npm run dev        # 啟動 Vite dev server（localhost:5173）
```

開發時若需連接後端，在 `.env` 設定：

```env
VITE_API_URL=http://localhost:8000
```

## 指令

```bash
npm run build          # TypeScript 型別檢查 + Vite build
npm run lint           # ESLint
npm run format         # Prettier 格式檢查
npm run test           # Vitest（watch mode）
npm run test:coverage  # 測試 + 覆蓋率報告（閾值 80%）
```

## 部署

推送到 GitHub 後由 Cloudflare Pages 自動建置。Build 設定：

| 項目          | 值                                                   |
| ------------- | ---------------------------------------------------- |
| Build command | `npm run build`                                      |
| Build output  | `dist`                                               |
| 環境變數      | `API_BACKEND`（後端位址，由 Cloudflare Tunnel 提供） |
