"""FastAPI server for frontend integration

這個 API server 專門處理前端的請求，與 TwitchIO bot 分離
主要功能：
- OAuth 認證流程
- 前端數據查詢
- 多平台擴展支持（Twitch, Discord 等）
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import auth

app = FastAPI(
    title="Niibot API",
    description="API server for Niibot frontend integration",
    version="1.0.0"
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 註冊路由
app.include_router(auth.router)


@app.get("/api/health")
async def health_check():
    """健康檢查"""
    return {"status": "ok", "service": "niibot-api"}


@app.get("/")
async def root():
    """API 根路徑"""
    return {
        "service": "Niibot API",
        "version": "1.0.0",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
