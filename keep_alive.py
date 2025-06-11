from threading import Thread

from flask import Flask

app = Flask('')


@app.route('/')
def home():
    return "Bot is alive!"


def run():
    import os
    port = int(os.environ.get("PORT", 8080))  # Render 會自動設定 PORT 環境變數
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


def keep_alive():
    t = Thread(target=run, daemon=True)  # daemon=True 確保主程式結束時 Flask 也會結束
    t.start()
