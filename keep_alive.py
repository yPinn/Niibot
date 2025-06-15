import threading
import time
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


def keep_alive():
    """啟動 Flask keep-alive 服務"""
    global _flask_ready
    
    # 在獨立執行緒中啟動 Flask
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = False
    flask_thread.start()
    
    # 簡單等待啟動
    time.sleep(2)
    
    BotLogger.system_event("保持連線", "Flask 伺服器已啟動")
    return True


def set_bot_ready(ready: bool = True):
    """設定機器人就緒狀態"""
    global _bot_ready
    _bot_ready = ready
    BotLogger.info("KeepAlive", f"機器人狀態更新: {'就緒' if ready else '未就緒'}")
