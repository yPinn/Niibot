"""
分隊邏輯模組
負責處理隊伍分組的核心算法
"""

import random
from typing import List, Tuple, Optional


class TeamDivider:
    """分隊邏輯處理器"""
    
    @staticmethod
    def calculate_optimal_teams(total_players: int, teams: Optional[int] = None, 
                              players_per_team: Optional[int] = None) -> Tuple[int, int]:
        """
        計算最佳分隊配置
        
        Args:
            total_players: 總玩家數
            teams: 期望隊伍數（可選）
            players_per_team: 每隊玩家數（可選）
            
        Returns:
            Tuple[隊伍數, 每隊玩家數]
        """
        if teams and players_per_team:
            # 兩個參數都指定，檢查是否合理
            if teams * players_per_team <= total_players:
                return teams, players_per_team
            else:
                # 調整為最大可能的配置
                return teams, total_players // teams
                
        elif teams:
            # 只指定隊伍數
            players_per_team = total_players // teams
            return teams, max(1, players_per_team)
            
        elif players_per_team:
            # 只指定每隊人數
            teams = total_players // players_per_team
            return max(1, teams), players_per_team
            
        else:
            # 自動計算最佳配置
            return TeamDivider._auto_calculate_teams(total_players)
    
    @staticmethod
    def _auto_calculate_teams(total_players: int) -> Tuple[int, int]:
        """自動計算最佳分隊配置"""
        if total_players <= 1:
            return 1, 1
        elif total_players <= 4:
            return 2, total_players // 2
        elif total_players <= 6:
            return 2, 3
        elif total_players <= 8:
            return 2, 4
        elif total_players <= 12:
            return 3, 4
        else:
            # 大群組：優先4人一隊
            teams = total_players // 4
            players_per_team = 4
            return teams, players_per_team
    
    @staticmethod
    def divide_players(player_ids: List[str], teams: int, players_per_team: int) -> List[List[str]]:
        """
        執行分隊操作
        
        Args:
            player_ids: 玩家ID列表
            teams: 隊伍數
            players_per_team: 每隊玩家數
            
        Returns:
            分隊結果列表
        """
        if not player_ids:
            return []
            
        # 洗牌確保隨機性
        shuffled_players = player_ids.copy()
        random.shuffle(shuffled_players)
        
        # 計算實際可分配的玩家數
        max_players = teams * players_per_team
        players_to_divide = shuffled_players[:max_players]
        
        # 執行分隊
        team_lists = []
        for i in range(teams):
            start = i * players_per_team
            end = start + players_per_team
            team = players_to_divide[start:end]
            if team:  # 只添加非空隊伍
                team_lists.append(team)
                
        return team_lists
    
    @staticmethod
    def validate_team_config(total_players: int, teams: int, players_per_team: int) -> Tuple[bool, str]:
        """
        驗證分隊配置是否合理
        
        Returns:
            Tuple[是否有效, 錯誤訊息]
        """
        if teams < 1:
            return False, "隊伍數必須至少為 1"
            
        if players_per_team < 1:
            return False, "每隊人數必須至少為 1"
            
        if teams > total_players:
            return False, f"隊伍數 ({teams}) 不能超過總人數 ({total_players})"
            
        if teams * players_per_team > total_players * 1.5:
            return False, "分隊配置會浪費太多玩家位置"
            
        return True, ""
    
    @staticmethod
    def get_unused_players(player_ids: List[str], teams: int, players_per_team: int) -> List[str]:
        """取得未分隊的玩家列表"""
        max_players = teams * players_per_team
        return player_ids[max_players:] if len(player_ids) > max_players else []