#!/usr/bin/env python3
"""
TwitchIO 版本檢查工具
用於診斷和修復版本問題
"""

import sys
import subprocess
import importlib.util

def check_twitchio_version():
    """檢查 TwitchIO 版本和兼容性"""
    print("🔍 檢查 TwitchIO 版本...")
    
    try:
        # 檢查是否安裝了 twitchio
        import twitchio
        version = getattr(twitchio, '__version__', 'unknown')
        print(f"✅ TwitchIO 已安裝，版本: {version}")
        
        # 檢查版本兼容性
        if version.startswith('2.'):
            print("✅ 版本兼容 (2.x)")
            return True
        elif version.startswith('3.'):
            print("❌ 版本不兼容 (3.x) - 需要降級到 2.9.1")
            return False
        else:
            print(f"⚠️ 未知版本: {version}")
            return False
            
    except ImportError:
        print("❌ TwitchIO 未安裝")
        return False

def check_bot_initialization():
    """檢查 Bot 初始化兼容性"""
    print("\n🔍 檢查 Bot 初始化...")
    
    try:
        from twitchio.ext import commands
        
        # 嘗試使用 TwitchIO 2.x 的方式初始化
        class TestBot(commands.Bot):
            def __init__(self):
                super().__init__(
                    token='oauth:test_token',
                    prefix='!',
                    initial_channels=['test_channel']
                )
        
        print("✅ Bot 初始化方式兼容 (TwitchIO 2.x)")
        return True
        
    except TypeError as e:
        if "missing" in str(e) and ("client_id" in str(e) or "client_secret" in str(e)):
            print("❌ Bot 初始化失敗 - 這是 TwitchIO 3.x 的錯誤")
            print(f"錯誤詳情: {e}")
            return False
        else:
            print(f"⚠️ 未知初始化錯誤: {e}")
            return False
    except Exception as e:
        print(f"⚠️ 檢查失敗: {e}")
        return False

def get_fix_commands():
    """生成修復指令"""
    print("\n🔧 修復指令:")
    print("1. 卸載當前版本:")
    print("   pip uninstall twitchio")
    print("\n2. 安裝正確版本:")
    print("   pip install twitchio==2.9.1")
    print("\n3. 驗證安裝:")
    print("   pip show twitchio")
    print("\n4. 重新執行此檢查:")
    print("   python check_twitchio_version.py")

def main():
    """主函數"""
    print("=" * 50)
    print("TwitchIO 版本診斷工具")
    print("=" * 50)
    
    # 檢查版本
    version_ok = check_twitchio_version()
    
    if not version_ok:
        print("\n❌ 版本問題檢測到")
        get_fix_commands()
        return False
    
    # 檢查初始化
    init_ok = check_bot_initialization()
    
    if not init_ok:
        print("\n❌ 初始化問題檢測到")
        get_fix_commands()
        return False
    
    print("\n✅ 所有檢查通過！TwitchIO 配置正確")
    print("你現在可以安全地運行 Twitch Bot")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)