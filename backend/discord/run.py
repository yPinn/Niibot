"""
Discord Bot 快速啟動腳本
用於開發和測試
"""

import sys
from pathlib import Path

# 將 backend 目錄加入 Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# 啟動 Bot
if __name__ == "__main__":
    import asyncio

    from discord.bot import main

    asyncio.run(main())
