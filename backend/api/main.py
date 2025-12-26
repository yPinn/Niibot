"""FastAPI server for frontend integration

這個 API server 專門處理前端的請求，與 TwitchIO bot 分離
主要功能：
- OAuth 認證流程
- 前端數據查詢
- 多平台擴展支持（Twitch, Discord 等）
"""

import logging
import os

from config import CORS_ORIGINS
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rich.console import Console
from rich.logging import RichHandler
from routers import auth, channels


def setup_logging():
    """設置日誌系統"""
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)

    console = Console(force_terminal=True, width=120)
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_level=True,
        show_path=False,
        markup=True,
    )
    rich_handler.setFormatter(
        logging.Formatter(fmt="%(message)s", datefmt="[%Y-%m-%d %H:%M:%S]")
    )

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%Y-%m-%d %H:%M:%S]",
        handlers=[rich_handler],
    )

    # 降低 uvicorn 存取日誌級別
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


setup_logging()

app = FastAPI(
    title="Niibot API",
    description="API server for Niibot frontend integration",
    version="1.0.0"
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 註冊路由
app.include_router(auth.router)
app.include_router(channels.router)


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
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_config=None  # 使用我們自己的日誌配置,不使用 uvicorn 預設的
    )
