from enum import Enum

class SessionStatus(str, Enum):
    """PVE 会话生命周期状态"""
    ACTIVE = "active"       # 进行中
    PAUSED = "paused"       # 已暂停 (预留)
    COMPLETED = "completed" # 已通关
    FAILED = "failed"       # 已失败/阵亡
    EXTRACTED = "extracted" # 已撤离结算

class NodeType(str, Enum):
    """地图网格点类型枚举"""
    EMPTY = "EMPTY"                   # 空地
    ENEMY_VISIBLE = "ENEMY_VISIBLE"   # 明雷 (可见敌人，会截停玩家)
    ENEMY_HIDDEN = "ENEMY_HIDDEN"     # 暗雷 (不可见，路过随机触发)
    BOSS = "BOSS"                     # 关底 BOSS 点
    TREASURE = "TREASURE"             # 宝箱/资源点
    OBSTACLE = "OBSTACLE"             # 障碍物 (需清理或绕路)
    EXIT = "EXIT"                     # 撤离点
    START = "START"                   # 起点

class CombatOutcome(str, Enum):
    """战斗结算结果"""
    WIN = "WIN"
    LOSE = "LOSE"
    DRAW = "DRAW"

class ExitMethod(str, Enum):
    """会话退出/结算方式"""
    BOSS_CLEAR = "BOSS_CLEAR"         # 击杀 BOSS 正常通关
    VOLUNTARY_EXIT = "VOLUNTARY_EXIT" # 玩家主动在撤离点安全撤退
    EMERGENCY_EXIT = "EMERGENCY_EXIT" # 玩家在非撤离点紧急强行撤退 (有折损)
    DEFEATED = "DEFEATED"             # 战斗失败导致全军覆没 (大面积折损)
