from enum import Enum

class EventType(str, Enum):
    """PVE 事件序列的事件类型枚举

    用于 EventSequence 中每个 PveEvent 的类型标识。
    """
    COMBAT = "COMBAT"               # 普通战斗 (随机敌人遭遇战)
    ELITE_COMBAT = "ELITE_COMBAT"   # 精英战斗 (强制遭遇，必须战斗)
    BOSS_COMBAT = "BOSS_COMBAT"     # Boss 战斗 (序列末尾最终挑战)
    LOOT = "LOOT"                   # 获取 (无战斗直接获得道具/装备)
    EVENT = "EVENT"                 # 随机事件 (剧情选项、陷阱、补给等)

class SessionStatus(str, Enum):
    """PVE 会话生命周期状态"""
    ACTIVE = "active"       # 进行中
    PAUSED = "paused"       # 已暂停 (预留)
    COMPLETED = "completed" # 已通关
    FAILED = "failed"       # 已失败/阵亡
    EXTRACTED = "extracted" # 已撤离结算

class ZoneStatus(str, Enum):
    """PVE 区域节点状态"""
    LOCKED = "locked"       # 已锁定 (未解锁)
    UNLOCKED = "unlocked"   # 已解锁 (可进入)
    CLEARED = "cleared"     # 已通关
    AVAILABLE = "available" # 可见 (隐藏节点刷新后可见)
    HIDDEN = "hidden"       # 隐藏 (不可见)

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
