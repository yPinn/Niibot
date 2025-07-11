# TwitchIO 版本問題解決方案

## 問題描述
收到錯誤：`Bot.__init__() missing 3 required keyword-only arguments: 'client_id', 'client_secret', and 'bot_id'`

這表示本地環境安裝了 TwitchIO 3.x，但專案設計為使用 TwitchIO 2.x。

## 解決步驟

### 1. 檢查當前版本
```bash
pip list | grep twitchio
```

### 2. 如果顯示 TwitchIO 3.x，執行降級
```bash
# 卸載當前版本
pip uninstall twitchio

# 安裝指定版本
pip install twitchio==2.9.1
```

### 3. 驗證版本
```bash
pip show twitchio
```
應顯示：`Version: 2.9.1`

### 4. 如果使用虛擬環境
```bash
# 確認在正確的虛擬環境中
which python
which pip

# 重新安裝依賴
pip install -r twitch-bot/requirements.txt
```

### 5. 清除快取（如果需要）
```bash
pip cache purge
```

## 版本差異說明

### TwitchIO 2.x (專案使用)
```python
# 簡化初始化
super().__init__(
    token=bot_token,
    prefix='!',
    initial_channels=['channel_name']
)
```

### TwitchIO 3.x (會出錯)
```python
# 需要額外參數
super().__init__(
    token=bot_token,
    client_id='your_client_id',      # 新增必要參數
    client_secret='your_secret',     # 新增必要參數
    bot_id='your_bot_id',           # 新增必要參數
    prefix='!'
)
```

## 確認修復成功

執行測試：
```bash
cd twitch-bot
python bot.py
```

應該看到日誌顯示：
- "Twitch Bot 初始化完成 (TwitchIO 2.9.1)"
- "Bot準備就緒"
- 沒有版本相關錯誤

## 注意事項

1. **不要升級到 TwitchIO 3.x**，除非願意重寫代碼
2. **確保虛擬環境隔離**，避免版本衝突
3. **requirements.txt 已鎖定版本**為 2.9.1
4. **如果仍有問題**，檢查是否有多個 Python 環境

## 替代解決方案

如果降級困難，可以創建新的虛擬環境：

```bash
# 創建新環境
python -m venv niibot_env

# 啟動環境
source niibot_env/bin/activate  # Linux/Mac
# 或
niibot_env\Scripts\activate     # Windows

# 安裝依賴
pip install -r twitch-bot/requirements.txt
```