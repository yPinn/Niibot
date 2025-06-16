"""
語音頻道管理模組
負責創建和管理分隊用的語音頻道
"""

import asyncio
from typing import List, Optional, Dict
import discord
from utils.logger import BotLogger


class VoiceChannelManager:
    """語音頻道管理器"""
    
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_tasks: Dict[int, asyncio.Task] = {}  # guild_id -> cleanup_task
    
    async def create_team_channels(self, guild: discord.Guild, team_count: int, 
                                 category: Optional[discord.CategoryChannel] = None) -> List[discord.VoiceChannel]:
        """
        創建分隊語音頻道
        
        Args:
            guild: Discord 伺服器
            team_count: 隊伍數量
            category: 頻道分類（可選）
            
        Returns:
            創建的語音頻道列表
        """
        created_channels = []
        
        try:
            for i in range(team_count):
                channel_name = f"🔥｜Team {i + 1}"
                
                # 檢查是否已存在同名頻道
                existing_channel = discord.utils.get(guild.voice_channels, name=channel_name)
                if existing_channel:
                    created_channels.append(existing_channel)
                    BotLogger.info("VoiceManager", f"使用現有頻道: {channel_name}")
                    continue
                
                # 創建新頻道
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(connect=True, speak=True),
                    guild.me: discord.PermissionOverwrite(connect=True, manage_channels=True, move_members=True)
                }
                
                channel = await guild.create_voice_channel(
                    name=channel_name,
                    category=category,
                    overwrites=overwrites,
                    reason="分隊系統自動創建"
                )
                created_channels.append(channel)
                BotLogger.info("VoiceManager", f"創建語音頻道: {channel_name}")
                
        except discord.Forbidden:
            BotLogger.error("VoiceManager", "沒有創建語音頻道的權限")
            raise
        except Exception as e:
            BotLogger.error("VoiceManager", f"創建語音頻道失敗: {e}", e)
            # 清理已創建的頻道
            await self._cleanup_channels(created_channels)
            raise
            
        return created_channels
    
    async def move_players_to_teams(self, guild: discord.Guild, teams: List[List[int]], 
                                  channels: List[discord.VoiceChannel]) -> Dict[str, int]:
        """
        將玩家移動到對應的語音頻道
        
        Args:
            guild: Discord 伺服器
            teams: 分隊結果 [[team1_user_ids], [team2_user_ids], ...]
            channels: 目標語音頻道列表
            
        Returns:
            移動結果統計 {'moved': count, 'failed': count}
        """
        stats = {'moved': 0, 'failed': 0}
        
        if len(channels) < len(teams):
            BotLogger.warning("VoiceManager", f"頻道數量不足: {len(channels)} < {len(teams)}")
            return stats
        
        try:
            for team_index, team_members in enumerate(teams):
                if team_index >= len(channels):
                    break
                    
                target_channel = channels[team_index]
                
                for user_id in team_members:
                    try:
                        member = guild.get_member(user_id)
                        if not member:
                            BotLogger.warning("VoiceManager", f"找不到成員: {user_id}")
                            stats['failed'] += 1
                            continue
                            
                        if not member.voice or not member.voice.channel:
                            BotLogger.debug("VoiceManager", f"成員 {member.display_name} 不在語音頻道中")
                            stats['failed'] += 1
                            continue
                            
                        await member.move_to(target_channel, reason="分隊系統自動移動")
                        stats['moved'] += 1
                        BotLogger.debug("VoiceManager", f"移動 {member.display_name} 到 {target_channel.name}")
                        
                        # 避免移動過快被限制
                        await asyncio.sleep(0.5)
                        
                    except discord.Forbidden:
                        BotLogger.warning("VoiceManager", f"沒有移動成員的權限: {user_id}")
                        stats['failed'] += 1
                    except discord.HTTPException as e:
                        BotLogger.warning("VoiceManager", f"移動成員失敗: {user_id}, 錯誤: {e}")
                        stats['failed'] += 1
                    except Exception as e:
                        BotLogger.error("VoiceManager", f"移動成員時發生未知錯誤: {e}", e)
                        stats['failed'] += 1
                        
        except Exception as e:
            BotLogger.error("VoiceManager", f"批量移動玩家失敗: {e}", e)
            
        BotLogger.info("VoiceManager", f"移動完成: 成功 {stats['moved']}, 失敗 {stats['failed']}")
        return stats
    
    async def schedule_cleanup(self, guild_id: int, channels: List[discord.VoiceChannel], 
                             delay_minutes: int = 30):
        """
        排程清理空的語音頻道
        
        Args:
            guild_id: 伺服器ID
            channels: 要監控的頻道列表
            delay_minutes: 延遲清理時間（分鐘）
        """
        # 取消之前的清理任務
        if guild_id in self.cleanup_tasks:
            self.cleanup_tasks[guild_id].cancel()
        
        # 創建新的清理任務
        self.cleanup_tasks[guild_id] = asyncio.create_task(
            self._cleanup_empty_channels_delayed(channels, delay_minutes * 60)
        )
        
        BotLogger.info("VoiceManager", f"排程 {delay_minutes} 分鐘後清理空頻道")
    
    async def _cleanup_empty_channels_delayed(self, channels: List[discord.VoiceChannel], delay_seconds: int):
        """延遲清理空的語音頻道"""
        try:
            await asyncio.sleep(delay_seconds)
            
            for channel in channels:
                try:
                    # 重新獲取頻道以確保資訊是最新的
                    fresh_channel = self.bot.get_channel(channel.id)
                    if not fresh_channel:
                        continue
                        
                    if len(fresh_channel.members) == 0:
                        await fresh_channel.delete(reason="分隊系統自動清理空頻道")
                        BotLogger.info("VoiceManager", f"已清理空頻道: {fresh_channel.name}")
                    else:
                        BotLogger.debug("VoiceManager", f"頻道非空，跳過清理: {fresh_channel.name}")
                        
                except discord.NotFound:
                    # 頻道已被刪除
                    pass
                except discord.Forbidden:
                    BotLogger.warning("VoiceManager", f"沒有刪除頻道的權限: {channel.name}")
                except Exception as e:
                    BotLogger.error("VoiceManager", f"清理頻道失敗: {e}", e)
                    
        except asyncio.CancelledError:
            BotLogger.debug("VoiceManager", "清理任務被取消")
        except Exception as e:
            BotLogger.error("VoiceManager", f"延遲清理任務失敗: {e}", e)
    
    async def _cleanup_channels(self, channels: List[discord.VoiceChannel]):
        """立即清理頻道"""
        for channel in channels:
            try:
                await channel.delete(reason="分隊系統錯誤清理")
                BotLogger.info("VoiceManager", f"已清理頻道: {channel.name}")
            except Exception as e:
                BotLogger.warning("VoiceManager", f"清理頻道失敗: {e}")
    
    def cancel_cleanup(self, guild_id: int):
        """取消清理任務"""
        if guild_id in self.cleanup_tasks:
            self.cleanup_tasks[guild_id].cancel()
            del self.cleanup_tasks[guild_id]
            BotLogger.debug("VoiceManager", f"已取消清理任務: {guild_id}")
    
    async def get_suitable_category(self, guild: discord.Guild) -> Optional[discord.CategoryChannel]:
        """尋找適合的頻道分類"""
        # 尋找名稱包含 "遊戲" 或 "Game" 的分類
        for category in guild.categories:
            if any(keyword in category.name.lower() for keyword in ['遊戲', 'game', '語音', 'voice']):
                return category
        
        # 如果沒有找到，返回第一個分類
        return guild.categories[0] if guild.categories else None