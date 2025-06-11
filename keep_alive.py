import asyncio
import threading
from flask import Flask

app = Flask('')


@app.route('/')
def home():
    return "Bot is alive!"


def run_flask():
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)


def keep_alive():
    # 在完全獨立的執行緒中啟動 Flask
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # 給 Flask 一點時間啟動
    import time
    time.sleep(1)
