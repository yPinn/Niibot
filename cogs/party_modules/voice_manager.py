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
        self.created_categories: Dict[int, discord.CategoryChannel] = {}  # guild_id -> category
        self.monitored_channels: Dict[int, List[discord.VoiceChannel]] = {}  # guild_id -> channels
    
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
        temp_category = None
        
        try:
            # 創建臨時分類夾
            temp_category = await self._create_temp_category(guild)
            if temp_category:
                category = temp_category
                self.created_categories[guild.id] = temp_category
            
            for i in range(team_count):
                channel_name = f"🔥｜Team {i + 1}"
                
                # 檢查是否已存在同名頻道（在臨時分類中）
                if category:
                    existing_channel = discord.utils.get(category.voice_channels, name=channel_name)
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
            # 清理已創建的分類夾
            if temp_category:
                try:
                    await temp_category.delete(reason="權限不足，清理臨時分類")
                except:
                    pass
            raise
        except Exception as e:
            BotLogger.error("VoiceManager", f"創建語音頻道失敗: {e}", e)
            # 清理已創建的頻道和分類夾
            await self._cleanup_channels(created_channels)
            if temp_category:
                try:
                    await temp_category.delete(reason="創建失敗，清理臨時分類")
                except:
                    pass
            raise
            
        # 開始監控這些頻道
        if created_channels:
            self.monitored_channels[guild.id] = created_channels
            self._start_realtime_monitoring(guild.id)
        
        return created_channels
        
    async def _create_temp_category(self, guild: discord.Guild) -> Optional[discord.CategoryChannel]:
        """創建臨時分隊分類夾"""
        try:
            category_name = "🎯 分隊進行中"
            
            # 檢查是否已存在相同名稱的分類
            existing_category = discord.utils.get(guild.categories, name=category_name)
            if existing_category:
                return existing_category
            
            # 創建新分類
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True),
                guild.me: discord.PermissionOverwrite(manage_channels=True, view_channel=True)
            }
            
            category = await guild.create_category(
                name=category_name,
                overwrites=overwrites,
                reason="分隊系統創建臨時分類"
            )
            
            BotLogger.info("VoiceManager", f"創建臨時分類: {category_name}")
            return category
            
        except discord.Forbidden:
            BotLogger.warning("VoiceManager", "沒有創建分類的權限，將使用現有分類")
            return None
        except Exception as e:
            BotLogger.error("VoiceManager", f"創建臨時分類失敗: {e}", e)
            return None
    
    def _start_realtime_monitoring(self, guild_id: int):
        """開始實時監控語音頻道"""
        # 取消之前的監控任務
        if guild_id in self.cleanup_tasks:
            self.cleanup_tasks[guild_id].cancel()
        
        # 創建新的監控任務
        self.cleanup_tasks[guild_id] = asyncio.create_task(
            self._monitor_channels_realtime(guild_id)
        )
        
        BotLogger.info("VoiceManager", f"開始實時監控語音頻道: {guild_id}")
    
    async def _monitor_channels_realtime(self, guild_id: int):
        """實時監控語音頻道，檢測是否為空"""
        try:
            while guild_id in self.monitored_channels:
                channels = self.monitored_channels[guild_id]
                if not channels:
                    break
                
                # 檢查每個頻道是否為空
                empty_channels = []
                remaining_channels = []
                
                for channel in channels:
                    try:
                        # 重新獲取頻道以確保資訊是最新的
                        fresh_channel = self.bot.get_channel(channel.id)
                        if not fresh_channel:
                            # 頻道已被刪除
                            continue
                        
                        if len(fresh_channel.members) == 0:
                            empty_channels.append(fresh_channel)
                        else:
                            remaining_channels.append(fresh_channel)
                            
                    except Exception as e:
                        BotLogger.warning("VoiceManager", f"檢查頻道狀態失敗: {e}")
                        remaining_channels.append(channel)
                
                # 如果所有頻道都空了，清理整個分隊資源
                if empty_channels and not remaining_channels:
                    BotLogger.info("VoiceManager", f"所有分隊頻道皆為空，開始清理: {guild_id}")
                    await self._cleanup_all_empty_channels(guild_id, empty_channels)
                    break
                
                # 更新監控列表
                self.monitored_channels[guild_id] = remaining_channels
                
                # 等待30秒後再次檢查
                await asyncio.sleep(30)
                
        except asyncio.CancelledError:
            BotLogger.debug("VoiceManager", f"實時監控任務被取消: {guild_id}")
        except Exception as e:
            BotLogger.error("VoiceManager", f"實時監控失敗: {e}", e)
        finally:
            # 清理監控記錄
            if guild_id in self.monitored_channels:
                del self.monitored_channels[guild_id]
    
    async def _cleanup_all_empty_channels(self, guild_id: int, channels: List[discord.VoiceChannel]):
        """清理所有空的語音頻道和分類夾"""
        try:
            # 刪除語音頻道
            for channel in channels:
                try:
                    await channel.delete(reason="分隊系統檢測到頻道為空，自動清理")
                    BotLogger.info("VoiceManager", f"已清理空頻道: {channel.name}")
                except Exception as e:
                    BotLogger.warning("VoiceManager", f"刪除頻道失敗: {e}")
            
            # 清理臨時分類夾（如果為空）
            if guild_id in self.created_categories:
                category = self.created_categories[guild_id]
                try:
                    # 重新檢查分類是否為空
                    fresh_category = self.bot.get_channel(category.id)
                    if fresh_category and len(fresh_category.channels) == 0:
                        await fresh_category.delete(reason="分隊系統檢測到分類為空，自動清理")
                        BotLogger.info("VoiceManager", f"已清理空分類: {category.name}")
                        del self.created_categories[guild_id]
                except Exception as e:
                    BotLogger.warning("VoiceManager", f"刪除分類失敗: {e}")
            
            # 停止監控
            if guild_id in self.monitored_channels:
                del self.monitored_channels[guild_id]
                
        except Exception as e:
            BotLogger.error("VoiceManager", f"清理空頻道失敗: {e}", e)
    
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
    
    # 已移除舊的延遲清理功能，現在使用實時監控
    
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
        
        # 也清理監控記錄
        if guild_id in self.monitored_channels:
            del self.monitored_channels[guild_id]
            BotLogger.debug("VoiceManager", f"已清理監控記錄: {guild_id}")

    async def cleanup_all_team_resources(self, guild_id: int, channels: List[discord.VoiceChannel]) -> Dict[str, int]:
        """清理所有分隊資源（頻道和分類夾）"""
        stats = {'channels_deleted': 0, 'category_deleted': 0, 'members_moved': 0}
        
        try:
            # 取消定時清理任務和監控
            self.cancel_cleanup(guild_id)
            
            # 先移動所有玩家
            if guild_id in self.created_categories:
                category = self.created_categories[guild_id]
                # 嘗試找到合適的目標頻道
                target_channel = await self._find_suitable_target_channel(category.guild)
                
                if target_channel:
                    for channel in channels:
                        for member in channel.members:
                            try:
                                await member.move_to(target_channel, reason="分隊結束，移動到合適頻道")
                                stats['members_moved'] += 1
                            except:
                                pass
            
            # 刪除語音頻道
            for channel in channels:
                try:
                    await channel.delete(reason="分隊結束，清理臨時頻道")
                    stats['channels_deleted'] += 1
                    BotLogger.info("VoiceManager", f"已刪除語音頻道: {channel.name}")
                except Exception as e:
                    BotLogger.warning("VoiceManager", f"刪除頻道失敗: {e}")
            
            # 刪除臨時分類夾（如果為空）
            if guild_id in self.created_categories:
                category = self.created_categories[guild_id]
                try:
                    # 檢查分類是否為空
                    if len(category.channels) == 0:
                        await category.delete(reason="分隊結束，清理空的臨時分類")
                        stats['category_deleted'] = 1
                        BotLogger.info("VoiceManager", f"已刪除臨時分類: {category.name}")
                        del self.created_categories[guild_id]
                    else:
                        BotLogger.info("VoiceManager", f"臨時分類非空，保留: {category.name}")
                except Exception as e:
                    BotLogger.warning("VoiceManager", f"刪除分類失敗: {e}")
                    
        except Exception as e:
            BotLogger.error("VoiceManager", f"清理資源失敗: {e}", e)
            
        return stats
    
    async def _find_suitable_target_channel(self, guild: discord.Guild) -> Optional[discord.VoiceChannel]:
        """尋找合適的目標語音頻道"""
        # 優先尋找非臨時的語音頻道
        for channel in guild.voice_channels:
            # 跳過臨時分類中的頻道
            if channel.category and "分隊進行中" in channel.category.name:
                continue
            # 尋找有人的頻道
            if len(channel.members) > 0:
                return channel
        
        # 如果沒有找到有人的頻道，返回第一個非臨時頻道
        for channel in guild.voice_channels:
            if channel.category and "分隊進行中" in channel.category.name:
                continue
            return channel
            
        return None
    
    async def get_suitable_category(self, guild: discord.Guild) -> Optional[discord.CategoryChannel]:
        """尋找適合的頻道分類"""
        # 尋找名稱包含 "遊戲" 或 "Game" 的分類
        for category in guild.categories:
            if any(keyword in category.name.lower() for keyword in ['遊戲', 'game', '語音', 'voice']):
                return category
        
        # 如果沒有找到，返回第一個分類
        return guild.categories[0] if guild.categories else None