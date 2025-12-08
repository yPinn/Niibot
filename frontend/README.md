# Niibot Frontend

React + TypeScript + Vite 前端應用

## 技術棧

- **React 19** - UI 框架
- **TypeScript** - 型別安全
- **Vite** - 建置工具
- **Tailwind CSS** - 樣式框架
- **shadcn/ui** - UI 元件庫
- **React Router** - 路由管理

## 開發

```bash
# 安裝依賴
npm install

# 啟動開發伺服器 (http://localhost:3000)
npm run dev

# 建置生產版本
npm run build

# Lint 檢查
npm run lint

# Lint 自動修復
npm run lint:fix
```

## 專案結構

```
src/
├── api/              # API 調用層
├── components/       # React 元件
│   ├── ui/          # shadcn/ui 元件
│   └── layouts/     # 佈局元件
├── pages/           # 頁面元件
├── hooks/           # 自訂 Hooks
└── lib/             # 工具函數
```

## 環境變數

複製 `.env.example` 為 `.env` 並設定：

```bash
VITE_API_URL=http://localhost:8000
```

## API 整合

所有 API 調用統一在 `src/api/` 目錄管理：

- `config.ts` - API 端點配置
- `user.ts` - 使用者相關 API
- `TwitchOauth.ts` - Twitch OAuth API

開發環境 API 請求會通過 Vite proxy 轉發到後端。
