"""
分隊狀態管理模組
負責維護每個伺服器的分隊狀態
"""

import asyncio
from typing import Dict, List, Optional, Set, Any
import discord


class GuildPartyState:
    """單一伺服器的分隊狀態"""
    
    def __init__(self):
        self.lobby: Dict[int, str] = {}  # user_id -> display_name
        self.lock = asyncio.Lock()
        self.max_players: Optional[int] = None
        self.queue_creator: Optional[int] = None
        self.original_voice_channel: Optional[discord.VoiceChannel] = None
        self.current_teams: List[List[int]] = []  # [[team1_ids], [team2_ids], ...]
        self.team_settings: Dict[str, Any] = {}  # {'teams': int, 'players_per_team': int}
        self.active_views: Set[Any] = set()  # 追蹤活躍的 View 實例
        self.created_channels: List[discord.VoiceChannel] = []  # 創建的語音頻道
    
    async def cleanup_state(self):
        """清理所有狀態"""
        async with self.lock:
            self.lobby.clear()
            self.current_teams.clear()
            self.team_settings.clear()
            self.max_players = None
            self.queue_creator = None
            self.original_voice_channel = None
            
            # 停用所有活躍的 Views
            for view in self.active_views.copy():
                if hasattr(view, 'stop'):
                    view.stop()
            self.active_views.clear()
            
            # 清理創建的頻道記錄（實際刪除在別處處理）
            self.created_channels.clear()
    
    def add_player(self, user_id: int, display_name: str) -> bool:
        """
        添加玩家到隊列
        
        Returns:
            是否成功添加
        """
        if self.max_players and len(self.lobby) >= self.max_players:
            return False
            
        self.lobby[user_id] = display_name
        return True
    
    def remove_player(self, user_id: int) -> bool:
        """
        從隊列移除玩家
        
        Returns:
            是否成功移除
        """
        return self.lobby.pop(user_id, None) is not None
    
    def is_queue_creator(self, user_id: int) -> bool:
        """檢查用戶是否為隊列創建者"""
        return self.queue_creator == user_id
    
    def get_player_count(self) -> int:
        """取得當前玩家數"""
        return len(self.lobby)
    
    def get_player_list(self) -> List[str]:
        """取得玩家顯示名稱列表"""
        return list(self.lobby.values())
    
    def get_player_ids(self) -> List[int]:
        """取得玩家ID列表"""
        return list(self.lobby.keys())
    
    def is_player_in_lobby(self, user_id: int) -> bool:
        """檢查玩家是否在隊列中"""
        return user_id in self.lobby
    
    def set_teams(self, teams: List[List[int]]):
        """設定分隊結果"""
        self.current_teams = teams.copy()
    
    def get_teams(self) -> List[List[int]]:
        """取得當前分隊結果"""
        return self.current_teams.copy()
    
    def has_teams(self) -> bool:
        """檢查是否已分隊"""
        return bool(self.current_teams)


class PartyStateManager:
    """分隊狀態管理器"""
    
    def __init__(self):
        self.guild_states: Dict[int, GuildPartyState] = {}
        self._global_lock = asyncio.Lock()
    
    async def get_state(self, guild_id: int) -> GuildPartyState:
        """取得或創建伺服器狀態"""
        async with self._global_lock:
            if guild_id not in self.guild_states:
                self.guild_states[guild_id] = GuildPartyState()
            return self.guild_states[guild_id]
    
    async def cleanup_guild(self, guild_id: int):
        """清理指定伺服器的狀態"""
        async with self._global_lock:
            if guild_id in self.guild_states:
                await self.guild_states[guild_id].cleanup_state()
                del self.guild_states[guild_id]
    
    async def has_active_queue(self, guild_id: int) -> bool:
        """檢查伺服器是否有活躍隊列"""
        if guild_id not in self.guild_states:
            return False
        state = self.guild_states[guild_id]
        return state.get_player_count() > 0 or state.has_teams()
    
    async def get_all_active_guilds(self) -> List[int]:
        """取得所有有活躍隊列的伺服器ID"""
        active_guilds = []
        async with self._global_lock:
            for guild_id, state in self.guild_states.items():
                if state.get_player_count() > 0 or state.has_teams():
                    active_guilds.append(guild_id)
        return active_guilds