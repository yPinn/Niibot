# Niibot Party系統更新摘要

## 修改檔案清單

### 1. bot.py
- 新增 get_deployment_info import
- 更新 ?test 指令顯示部署資訊

### 2. cogs/party.py  
- 移除自動超時機制
- 新增 TeamsManageView 分隊後管理界面
- 改善按鈕交互和embed更新
- 新增管理員權限支持
- 修正重新分隊設定保存問題
- 更新術語：隊長 → Host

### 3. cogs/party_modules/state_manager.py
- 新增 original_message 狀態追蹤
- 改善活躍隊列檢查邏輯

### 4. cogs/party_modules/voice_manager.py  
- 簡化分類名稱為「🎯 分隊進行中」
- 實現實時監控語音頻道
- 新增自動清理機制
- 移除舊的延遲清理功能

### 5. utils/util.py
- 新增 get_deployment_info() 函數

## 主要功能改進

1. **分隊結果公開顯示** - 所有人可見，直接@用戶
2. **手動控制隊列生命週期** - 移除自動超時
3. **實時語音頻道監控** - 30秒檢查，空頻道自動清理  
4. **管理員權限支持** - 管理員可執行分隊操作
5. **改善重新分隊功能** - 可多次使用同樣設定分隊

## 部署資訊功能
- ?test 指令現在會顯示部署平台、環境、主機等資訊
- 方便判斷是否有多個實例運行

## 提交訊息
```
feat: 全面優化Party分隊系統UX和功能

完整更新說明請參考 CHANGES_SUMMARY.md
```