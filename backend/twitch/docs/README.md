# TwitchIO Bot 文檔

完整的 TwitchIO 多頻道機器人文檔索引。

## 📚 文檔列表

### 🚀 [部署指南](DEPLOYMENT.md)
- **本地開發** - 快速啟動開發環境
- **Docker 部署** - Docker / Docker Compose 容器化部署
- **Render 部署** - 雲端平台部署指南
- **OAuth 遠端配置** - 公開伺服器 OAuth 設定

**適合對象**: 想要部署 Bot 到生產環境的開發者

---

### 📖 [設定與權限指南](SETUP_GUIDE.md)
- **OAuth 授權流程** - Bot 帳號與頻道授權完整步驟
- **Scopes 說明** - 所有必需與可選的 OAuth scopes 詳解
- **權限架構** - Owner/Broadcaster/Moderator/User 權限系統
- **常見問題** - OAuth、權限、Channel Points 相關問答

**適合對象**: 需要理解授權流程和權限管理的開發者與管理員

---

### 🔧 [TwitchIO 3 API 使用指南](TWITCHIO3_API.md)
- **官方 API 正確用法** - TwitchIO 3 的最佳實踐
- **常見錯誤與修正** - 遷移與升級常見問題
- **類型註解指南** - Type hints 和 mypy 使用

**適合對象**: 正在開發組件或遇到 TwitchIO 3 API 問題的開發者

---

## 🔗 其他資源

返回 [主 README](../README.md) 查看：
- 快速開始指南
- 可用指令列表
- 資料庫結構
- 開發工具配置

查看 [database/](../database/) 目錄了解資料庫結構與初始化腳本。

---

## 📝 貢獻文檔

如果你發現文檔有誤或需要補充，歡迎提交 Pull Request！

**文檔規範**:
- 使用繁體中文
- 提供清晰的範例代碼
- 包含常見問題解答
- 保持簡潔易懂
