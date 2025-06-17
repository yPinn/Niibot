# 指令參數驗證改進報告

## 🎯 改進目標
確保所有需要參數的指令在用戶未提供必要參數時，顯示友好的使用提示。

## ✅ 已改進的指令

### **Eat 模組** (`cogs/eat.py`)
1. **`?additem`** - 需要分類和餐點名稱
   - 錯誤提示：`❌ 請提供分類和餐點名稱，例如：\`?additem 主餐 蛋餅\``

2. **`?delitem`** - 需要分類和餐點名稱
   - 錯誤提示：`❌ 請提供分類和餐點名稱，例如：\`?delitem 主餐 蛋餅\``

3. **`?menu`** - 需要分類名稱
   - 錯誤提示：`❓ 請輸入要查看的分類，例如：\`?menu 主餐\``

4. **`?delcat`** - 需要分類名稱
   - 錯誤提示：`❌ 請提供要刪除的分類名稱，例如：\`?delcat 早餐\``

### **EmojiTool 模組** (`cogs/emojitool.py`)
5. **`?emoji_add`** - 需要名稱和表情符號
   - 錯誤提示：`❌ 請提供名稱和表情符號，例如：\`?emoji_add smile 😀\``
   - 額外處理：權限錯誤提示

6. **`?keyword_add`** - 需要關鍵字和回覆內容
   - 錯誤提示：`❌ 請提供關鍵字和回覆內容，例如：\`?keyword_add hello 你好！\``
   - 額外處理：權限錯誤提示

## ✅ 已確認正常的指令

### **Clear 模組** (`cogs/clear.py`)
- **`?clear`** - 已有完整的錯誤處理器，包括參數錯誤和權限錯誤

### **Draw 模組** (`cogs/draw.py`)
- **`?draw`** - 已有完整的參數驗證和使用提示

### **Reply 模組** (`cogs/reply.py`)
- **`?cc`** - 已有良好的參數驗證邏輯

### **Party 模組** (`cogs/party.py`)
- **`?queue`** - 參數為可選，有預設值

### **Clock 模組** (`cogs/clock.py`)
- 所有指令都不需要參數

### **Listener 模組** (`cogs/listener.py`)
- 所有指令都有可選參數和預設值

### **Tinder 模組** (`cogs/tinder.py`)
- **`?t`** - 不需要參數

## 🔧 實現方法

### 錯誤處理器模式
```python
@command_name.error
async def command_error(self, ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ 使用提示訊息，例如：`?command 參數`")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ 您沒有權限使用此指令")
    else:
        BotLogger.error("ModuleName", f"command 指令錯誤: {error}")
```

### 提示訊息格式
- 使用 ❌ 或 ❓ 開頭
- 提供具體的使用範例
- 使用反引號標記指令格式
- 簡潔明瞭的說明

## 📊 改進效果

### **用戶體驗提升**
- 清楚的錯誤提示
- 具體的使用範例
- 友好的錯誤訊息

### **維護性提升**
- 統一的錯誤處理模式
- 完整的日誌記錄
- 更好的除錯資訊

## 🧪 測試建議

### 參數錯誤測試
```bash
# 測試各種參數缺失情況
?additem          # 缺少所有參數
?additem 主餐      # 缺少餐點名稱
?delitem          # 缺少所有參數
?menu             # 缺少分類
?emoji_add        # 缺少所有參數
?keyword_add      # 缺少所有參數
```

### 權限錯誤測試
```bash
# 使用沒有權限的帳號測試
?emoji_add test 😀
?keyword_add hello 你好
```

## 📈 結果

所有需要參數的指令現在都有適當的錯誤處理和用戶友好的提示訊息，大幅提升了用戶體驗和系統的健壯性。