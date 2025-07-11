# Niibot 升級指南 v2.1

## 🔄 重大更新說明

本次更新解決了資料檔案重複和依賴版本衝突問題，提升了系統的一致性和可維護性。

### ✨ 主要改善

#### 1. 統一資料管理
- **新增**: `shared/data/` 作為統一資料目錄
- **新增**: `shared/utils/data_manager.py` 統一資料管理器
- **移除**: 重複的資料檔案 (`data/`, `twitch-bot/data/` 中的 eat.json 和 draw_history.json)
- **保留**: Discord Bot 的完整資料作為主要資料源

#### 2. 版本統一管理
- **新增**: `requirements-base.txt` 基礎依賴定義
- **更新**: 所有 requirements 檔案採用統一版本
- **新增**: `install_deps.sh` 一鍵安裝腳本

#### 3. 建議依賴版本

```txt
# 核心依賴 (統一版本)
aiofiles==24.1.0          # 從 23.2.1 升級
python-dotenv==1.1.0       # 從 1.0.0 升級
aiohttp==3.10.12           # 從 >=3.9.0 升級
discord.py==2.5.2          # 保持不變
twitchio==2.9.1            # 保持穩定 2.x
Flask==3.1.1               # 保持不變
pytz==2024.2               # 保持不變

# 新增依賴
psutil==6.1.0              # 系統監控
asyncio-throttle==1.0.2    # 異步限流
watchdog==6.0.0            # 檔案監控
asyncio-mqtt==0.16.2       # MQTT 支援
```

## 🛠️ 升級步驟

### 自動升級 (推薦)

```bash
# 1. 執行安裝腳本
chmod +x install_deps.sh
./install_deps.sh

# 2. 選擇要安裝的平台 (選項 4 包含所有平台)
```

### 手動升級

```bash
# 1. 安裝基礎依賴
pip install -r requirements-base.txt

# 2. 根據需要安裝平台特定依賴
pip install -r discord-bot/requirements.txt  # Discord Bot
pip install -r twitch-bot/requirements.txt   # Twitch Bot
# 或
pip install -r requirements-launcher.txt     # 所有平台
```

### 資料遷移 (自動完成)

資料已自動遷移到 `shared/data/`：
- ✅ `shared/data/eat.json` - 來自 Discord Bot 的完整資料
- ✅ `shared/data/draw_history.json` - 來自 Discord Bot 的記錄

## 🔧 配置更新

### 資料路徑變更
```python
# 舊路徑 (自動相容)
config.data_dir  # 現在指向 'shared/data'

# 新方式 (建議)
from shared.utils.data_manager import data_manager
data = await data_manager.load_eat_data()
```

### 統一資料管理器使用

```python
# 導入統一資料管理器
from shared.utils.data_manager import data_manager

# 異步操作
eat_data = await data_manager.load_eat_data()
await data_manager.save_eat_data(eat_data)

draw_history = await data_manager.load_draw_history()
await data_manager.save_draw_history(draw_history)

# 同步操作 (向下相容)
eat_data = data_manager.load_json_sync("eat.json")
data_manager.save_json_sync("eat.json", eat_data)
```

## 🚨 注意事項

### 向下相容性
- ✅ 現有程式碼無需修改
- ✅ 配置檔案保持不變
- ✅ 指令和功能正常運作

### 檔案變更
- ❌ 移除：`data/eat.json`, `data/draw_history.json`
- ❌ 移除：`twitch-bot/data/eat.json`, `twitch-bot/data/draw_history.json`
- ✅ 新增：`shared/data/eat.json`, `shared/data/draw_history.json`
- ✅ 新增：`shared/utils/data_manager.py`
- ✅ 新增：`requirements-base.txt`, `install_deps.sh`

### 資料安全
- 🔄 自動備份：資料管理器會建立 `.bak.*` 備份檔案
- 🧹 自動清理：可設定保留天數清理舊備份

## 🧪 測試建議

### 基本功能測試

```bash
# 1. 語法檢查
python3 -m py_compile main.py
python3 -m py_compile shared/config/modular_config.py
python3 -m py_compile shared/utils/data_manager.py

# 2. 啟動測試
python3 main.py discord --env local  # Discord Bot
python3 main.py twitch --env local   # Twitch Bot

# 3. 功能測試
# - Discord: 測試 /eat, /draw 指令
# - Twitch: 測試 ?eat, ?draw 指令
```

### 資料存取測試

```python
# 測試統一資料管理器
from shared.utils.data_manager import data_manager

# 測試資料載入
eat_data = data_manager.load_json_sync("eat.json")
print(f"載入 {len(eat_data.get('主餐', []))} 個主餐選項")

# 測試備份功能
success = data_manager.save_json_sync("test.json", {"test": True})
print(f"測試儲存: {'成功' if success else '失敗'}")
```

## 🐛 故障排除

### 常見問題

**Q: 找不到資料檔案**
```bash
# 檢查資料目錄
ls -la shared/data/
# 應該看到 eat.json 和 draw_history.json
```

**Q: 依賴版本衝突**
```bash
# 重新安裝依賴
pip uninstall -y aiofiles python-dotenv aiohttp
pip install -r requirements-base.txt
```

**Q: 啟動失敗**
```bash
# 檢查配置檔案
python3 -c "from shared.config.modular_config import config; print(config.get_config_summary())"
```

### 回滾方案

如果遇到問題，可以暫時回滾：

```bash
# 1. 恢復舊的資料檔案
cp discord-bot/data/eat.json data/
cp discord-bot/data/draw_history.json data/
cp discord-bot/data/eat.json twitch-bot/data/
cp discord-bot/data/draw_history.json twitch-bot/data/

# 2. 使用舊的 requirements 檔案
git checkout HEAD~1 -- requirements-launcher.txt
git checkout HEAD~1 -- discord-bot/requirements.txt
git checkout HEAD~1 -- twitch-bot/requirements.txt
```

## 📈 效能提升

### 預期改善
- 🗂️ **資料一致性**: 消除多份拷貝的同步問題
- 📦 **依賴管理**: 統一版本減少衝突風險
- 🔧 **維護性**: 統一接口簡化維護工作
- 💾 **備份機制**: 自動備份保護資料安全

### 版本升級效益
- **aiofiles**: 24.1.0 提供更好的異步檔案操作效能
- **aiohttp**: 3.10.12 修復安全性問題並提升穩定性
- **python-dotenv**: 1.1.0 改善配置載入效能
- **watchdog**: 6.0.0 更好的跨平台檔案監控支援

---

**升級完成後請測試所有核心功能，如有問題請參考故障排除或回滾方案。**