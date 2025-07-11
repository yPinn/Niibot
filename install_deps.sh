#!/bin/bash
# Niibot 統一依賴安裝腳本

echo "🔧 Niibot 依賴安裝腳本"
echo "========================"

# 檢查 Python 版本
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
echo "📋 Python 版本: $python_version"

if [ ! $(python3 -c "print('3.8' <= '$python_version' <= '3.12')") = "True" ]; then
    echo "❌ 需要 Python 3.8-3.12，目前版本: $python_version"
    exit 1
fi

# 安裝基礎依賴
echo "📦 安裝基礎依賴..."
pip3 install -r requirements-base.txt

if [ $? -ne 0 ]; then
    echo "❌ 基礎依賴安裝失敗"
    exit 1
fi

# 詢問要安裝的平台
echo ""
echo "🤖 選擇要安裝的機器人平台:"
echo "1) Discord Bot 只"
echo "2) Twitch Bot 只"
echo "3) 兩個平台都要"
echo "4) 啟動器 (包含所有平台)"

read -p "請選擇 (1-4): " choice

case $choice in
    1)
        echo "📱 安裝 Discord Bot 依賴..."
        pip3 install -r discord-bot/requirements.txt
        ;;
    2)
        echo "🎮 安裝 Twitch Bot 依賴..."
        pip3 install -r twitch-bot/requirements.txt
        ;;
    3)
        echo "📱🎮 安裝所有平台依賴..."
        pip3 install -r discord-bot/requirements.txt
        pip3 install -r twitch-bot/requirements.txt
        ;;
    4)
        echo "🚀 安裝啟動器依賴 (包含所有平台)..."
        pip3 install -r requirements-launcher.txt
        ;;
    *)
        echo "❌ 無效選擇"
        exit 1
        ;;
esac

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 依賴安裝完成！"
    echo ""
    echo "📖 接下來的步驟:"
    echo "1. 複製配置檔案: cp config/*/*.env.example config/*/*.env"
    echo "2. 編輯配置檔案並填入必要的 Token"
    echo "3. 啟動機器人: python3 main.py [discord|twitch|both]"
else
    echo "❌ 依賴安裝失敗"
    exit 1
fi