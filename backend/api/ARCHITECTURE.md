# API Server 架構說明

## 資料夾結構

```
backend/api/
├── main.py              # FastAPI 主程式
├── config.py            # 配置管理
├── routers/             # 路由層 (HTTP 請求/響應)
│   ├── __init__.py
│   └── auth.py          # 認證相關路由 (Twitch OAuth, 使用者 API)
└── services/            # 服務層 (業務邏輯)
    ├── __init__.py
    ├── twitch.py        # Twitch 相關邏輯 (OAuth URL 生成, code 轉發)
    └── user.py          # 使用者相關邏輯 (使用者資料查詢)
```

## 分層架構

### 1. Routers 層 (路由層)
**職責**: 只處理 HTTP 請求和響應
- 接收 HTTP 請求
- 驗證請求參數
- 呼叫 services 層處理業務邏輯
- 返回 HTTP 響應

**範例**: `routers/auth.py`
```python
@router.get("/twitch/oauth")
async def get_twitch_oauth_url():
    oauth_url = twitch_service.generate_oauth_url()
    return {"oauth_url": oauth_url}
```

### 2. Services 層 (服務層)
**職責**: 處理所有業務邏輯
- OAuth URL 生成
- 與外部 API 通訊 (bot, Twitch API)
- 資料庫查詢 (未來)
- 錯誤處理和日誌記錄

**範例**: `services/twitch.py`
```python
def generate_oauth_url() -> str:
    # 生成 OAuth URL 的邏輯
    return oauth_url

async def forward_oauth_code_to_bot(code: str) -> tuple[bool, str | None]:
    # 轉發 OAuth code 到 bot 的邏輯
    return success, error_msg
```

### 3. Config 層 (配置層)
**職責**: 統一管理所有配置
- 環境變數載入
- URL 配置
- CORS 設定

## 優點

1. **關注點分離**: 每一層職責明確,易於維護
2. **可測試性**: Services 層可以獨立測試,不需要啟動 HTTP server
3. **可擴展性**: 新增平台 (Discord) 只需新增對應的 router 和 service
4. **可重用性**: Services 可以在不同的 router 中重用

## 未來擴展

### 新增 Discord 支援
```
routers/
├── auth.py          # Twitch 認證
└── discord_auth.py  # Discord 認證 (新增)

services/
├── twitch.py        # Twitch 邏輯
├── discord.py       # Discord 邏輯 (新增)
└── user.py          # 使用者邏輯 (共用)
```

### 新增資料庫層
```
services/
├── twitch.py
├── user.py
└── database.py      # 資料庫操作 (新增)
```

## API 路由

### 認證相關
- `GET /api/auth/twitch/oauth` - 取得 Twitch OAuth URL
- `GET /api/auth/twitch/callback` - 處理 Twitch OAuth 回調
- `GET /api/auth/user` - 取得當前使用者資訊

### 健康檢查
- `GET /api/health` - API 健康檢查
- `GET /` - API 根路徑資訊
