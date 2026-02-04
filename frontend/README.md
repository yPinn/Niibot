# Niibot Frontend

React 19 + TypeScript + Vite + Tailwind CSS。部署於 Cloudflare Pages。

## 啟動

```bash
cp .env.example .env
npm install && npm run dev
```

## 結構

```
src/
├── api/          # API 調用
├── components/   # 元件
├── pages/        # 頁面
├── contexts/     # React Context
└── lib/          # 工具函數
functions/        # CF Pages Functions（API 反向代理）
```

## 部署

- Cloudflare Pages 自動從 `main` 部署
- `functions/api/[[path]].ts` 將 `/api/*` 代理至後端
- 後端 URL 透過 CF Pages 環境變數 `API_BACKEND` 設定（非 `.env`）

## 環境變數

**開發**（`.env`）：

```env
VITE_API_URL=http://localhost:8000
```

**生產**（CF Pages Dashboard）：

- `API_BACKEND` — 後端 URL（如 `https://xxx.onrender.com`）
