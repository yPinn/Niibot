import asyncio
import threading
import time
import requests
from flask import Flask, jsonify
from utils.logger import BotLogger

app = Flask('')

# 全域變數追蹤服務狀態
_flask_ready = False
_bot_ready = False


@app.route('/')
def home():
    return "Niibot is running!"


@app.route('/health')
def health():
    """健康檢查端點，提供詳細狀態資訊"""
    status = {
        "status": "healthy" if _flask_ready and _bot_ready else "starting",
        "flask_ready": _flask_ready,
        "bot_ready": _bot_ready,
        "timestamp": time.time()
    }
    return jsonify(status)


@app.route('/ping')
def ping():
    """簡單的 ping 端點，供 Uptime Robot 使用"""
    return "pong"


def run_flask():
    """運行 Flask 應用程式"""
    global _flask_ready
    import os
    
    port = int(os.environ.get("PORT", 8080))
    
    try:
        BotLogger.info("KeepAlive", f"啟動 Flask 伺服器於端口 {port}")
        _flask_ready = True
        app.run(
            host='0.0.0.0', 
            port=port, 
            debug=False, 
            use_reloader=False, 
            threaded=True,
            # 加入錯誤處理，避免崩潰
            use_debugger=False
        )
    except Exception as e:
        _flask_ready = False
        BotLogger.error("KeepAlive", "Flask 伺服器啟動失敗", e)
        raise


def verify_flask_startup(port: int, max_attempts: int = 10) -> bool:
    """驗證 Flask 伺服器是否成功啟動"""
    for attempt in range(max_attempts):
        try:
            response = requests.get(f"http://localhost:{port}/ping", timeout=2)
            if response.status_code == 200:
                BotLogger.info("KeepAlive", f"Flask 伺服器驗證成功 (嘗試 {attempt + 1})")
                return True
        except requests.exceptions.RequestException:
            pass
        
        time.sleep(0.5)
    
    BotLogger.warning("KeepAlive", f"Flask 伺服器驗證失敗，經過 {max_attempts} 次嘗試")
    return False


def keep_alive():
    """啟動並驗證 Flask keep-alive 服務"""
    global _flask_ready
    import os  # 確保 os 已導入
    
    # 在獨立執行緒中啟動 Flask，但不設為 daemon
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = False  # 確保不會隨主程序結束
    flask_thread.start()
    
    # 等待 Flask 啟動並驗證
    port = int(os.environ.get("PORT", 8080))
    startup_time = time.time()
    
    # 給 Flask 更多時間啟動（重要！）
    time.sleep(3)
    
    # 驗證服務是否正常
    if verify_flask_startup(port):
        elapsed = time.time() - startup_time
        BotLogger.system_event("保持連線", f"Flask 伺服器成功啟動並驗證 (耗時 {elapsed:.2f}s)")
        return True
    else:
        BotLogger.error("KeepAlive", "Flask 伺服器啟動驗證失敗")
        return False


def set_bot_ready(ready: bool = True):
    """設定機器人就緒狀態"""
    global _bot_ready
    _bot_ready = ready
    BotLogger.info("KeepAlive", f"機器人狀態更新: {'就緒' if ready else '未就緒'}")
