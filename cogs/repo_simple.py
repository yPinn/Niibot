"""
簡化版準心代碼庫 - 用於測試基本功能
如果主版本有問題，可以暫時使用這個版本
"""

import discord
from discord.ext import commands
from utils.logger import BotLogger
from utils import util


class SimpleRepo(commands.Cog):
    """簡化版準心代碼庫 - 只有基本功能，無UI組件"""
    
    def __init__(self, bot):
        self.bot = bot
        self.data_file = "repo.json"
    
    async def _load_crosshairs(self) -> list:
        """載入準心資料"""
        try:
            file_path = util.get_data_file_path(self.data_file)
            data = await util.read_json(file_path)
            if isinstance(data, dict):
                return data.get('crosshairs', [])
            return data or []
        except Exception as e:
            BotLogger.error("SimpleRepo", f"載入準心資料失敗: {e}")
            return []

    @commands.command(name="repo_simple", aliases=["簡單準心"], help="簡單版準心代碼庫")
    async def repo_simple(self, ctx, *, search_term: str = None):
        """簡化版準心瀏覽 - 不使用複雜UI"""
        try:
            crosshairs = await self._load_crosshairs()
            
            if not crosshairs:
                embed = discord.Embed(
                    title="📦 準心代碼庫", 
                    description="目前沒有準心資料",
                    color=discord.Color.orange()
                )
                await ctx.send(embed=embed)
                return
            
            # 搜尋過濾
            if search_term:
                search_term = search_term.lower()
                filtered = [
                    ch for ch in crosshairs 
                    if (search_term in ch.get('game', '').lower() or 
                        search_term in ch.get('tag', '').lower())
                ]
                
                if not filtered:
                    embed = discord.Embed(
                        title="🔍 搜尋結果",
                        description=f"沒有找到包含 '{search_term}' 的準心",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
                    return
                
                crosshairs = filtered
            
            # 按遊戲分組
            games = {}
            for ch in crosshairs:
                game = ch.get('game', '未知遊戲')
                if game not in games:
                    games[game] = []
                games[game].append(ch)
            
            # 建立簡單的列表回覆
            embed = discord.Embed(
                title="🎯 準心代碼庫" + (f" - 搜尋: {search_term}" if search_term else ""),
                description=f"共找到 {len(crosshairs)} 個準心",
                color=discord.Color.blue()
            )
            
            for game, items in games.items():
                emoji = "🎯" if game == "Valorant" else "🔫" if game == "CS2" else "⚡" if "Apex" in game else "🎮"
                game_info = []
                for ch in items[:3]:  # 每個遊戲最多顯示3個
                    ch_id = ch.get('id', 'N/A')
                    tag = ch.get('tag', '無標籤')
                    has_image = "🖼️" if ch.get('image_url') else "❌"
                    game_info.append(f"`{ch_id}` {tag} {has_image}")
                
                if len(items) > 3:
                    game_info.append(f"... 還有 {len(items) - 3} 個")
                
                embed.add_field(
                    name=f"{emoji} {game} ({len(items)}個)",
                    value="\n".join(game_info) or "無資料", 
                    inline=False
                )
            
            embed.set_footer(text="使用 ?repo_get <ID> 查看完整準心代碼")
            await ctx.send(embed=embed)
            
            BotLogger.command_used("repo_simple", ctx.author.id, ctx.guild.id if ctx.guild else 0, 
                                   f"簡單瀏覽: {search_term or 'all'}")
            
        except Exception as e:
            BotLogger.error("SimpleRepo", f"簡單瀏覽失敗: {e}")
            import traceback
            traceback.print_exc()
            await ctx.send(f"❌ 簡單版載入失敗: {str(e)[:100]}")

    @commands.command(name="repo_get", aliases=["準心詳情"], help="查看指定準心的完整資料")
    async def repo_get(self, ctx, crosshair_id: str):
        """查看指定ID的準心詳細資料"""
        try:
            crosshairs = await self._load_crosshairs()
            
            # 尋找準心
            target_crosshair = None
            for ch in crosshairs:
                if str(ch.get('id', '')).lower() == crosshair_id.lower():
                    target_crosshair = ch
                    break
            
            if not target_crosshair:
                embed = discord.Embed(
                    title="❌ 找不到準心",
                    description=f"ID `{crosshair_id}` 的準心不存在",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return
            
            # 建立詳細資料
            game = target_crosshair.get('game', '未知遊戲')
            tag = target_crosshair.get('tag', '無標籤')
            code = target_crosshair.get('code', '無代碼')
            image_url = target_crosshair.get('image_url')
            
            embed = discord.Embed(
                title=f"🎯 {tag}",
                description=f"**遊戲：** {game}\n**ID：** `{crosshair_id}`",
                color=discord.Color.green()
            )
            
            # 準心代碼
            if len(code) > 1000:
                embed.add_field(
                    name="📋 準心代碼 (已截斷)",
                    value=f"```\n{code[:900]}...\n```",
                    inline=False
                )
            else:
                embed.add_field(
                    name="📋 準心代碼",
                    value=f"```\n{code}\n```",
                    inline=False
                )
            
            # 設定圖片
            if image_url and image_url.strip():
                embed.set_image(url=image_url)
            else:
                embed.add_field(
                    name="🖼️ 預覽圖片",
                    value="無預覽圖片",
                    inline=True
                )
            
            await ctx.send(embed=embed)
            
            BotLogger.command_used("repo_get", ctx.author.id, ctx.guild.id if ctx.guild else 0, 
                                   f"查看準心: {crosshair_id}")
            
        except Exception as e:
            BotLogger.error("SimpleRepo", f"查看準心失敗: {e}")
            await ctx.send("❌ 查看準心時發生錯誤")


async def setup(bot):
    await bot.add_cog(SimpleRepo(bot))