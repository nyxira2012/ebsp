from typing import List, Dict, Optional, Any
from pydantic import BaseModel, ConfigDict, Field
from .enums import SessionStatus, EventType

# -----------------
# 事件序列 (Event Sequence)
# 替代小地图的 PVE 推进机制
# -----------------
class PveEvent(BaseModel):
    """事件序列中的单个事件。

    Attributes:
        index (int): 事件在序列中的位置索引（0 开始）。
        event_type (EventType): 事件类型 (COMBAT/ELITE_COMBAT/BOSS_COMBAT/LOOT/EVENT)。
        event_id (Optional[str]): 关联的资源 ID，如敌人模板 ID 或战利品配置 ID。
        cleared (bool): 该事件是否已处理完毕。
        rewards (List[Dict[str, Any]]): 该事件结算后已产生的临时战利品。
    """
    index: int
    event_type: EventType
    event_id: Optional[str] = None
    cleared: bool = False
    rewards: List[Dict[str, Any]] = Field(default_factory=list)

class EventSequence(BaseModel):
    """事件序列。

    替代点阵地图的简化推进机制。每次进入大区域后，服务端随机生成一条线性事件列表。

    Attributes:
        events (List[PveEvent]): 有序的事件列表。
        current_index (int): 当前看到的事件索引 (未开始为 0)。
        total_events (int): 序列中的总事件数。
    """
    events: List[PveEvent] = Field(default_factory=list)
    current_index: int = 0

    @property
    def total_events(self) -> int:
        """事件序列的总事件数。"""
        return len(self.events)

    def current_event(self) -> Optional["PveEvent"]:
        """获取当前待处理的事件。

        Returns:
            Optional[PveEvent]: 当前事件，若序列已完成则返回 None。
        """
        if self.current_index < len(self.events):
            return self.events[self.current_index]
        return None

    def advance(self) -> bool:
        """推进到下一个事件。

        Returns:
            bool: 如果序列未完成则返回 True，序列已结束则返回 False。
        """
        if self.current_index < len(self.events):
            self.current_index += 1
            return self.current_index < len(self.events)
        return False

    def is_complete(self) -> bool:
        """检查序列是否已全部完成。

        Returns:
            bool: 所有事件已处理完毕则返回 True。
        """
        return self.current_index >= len(self.events)

# -----------------
# 状态记录 (State)
# -----------------
class PveEntityState(BaseModel):
    """
    跨战斗状态快照。
    
    负责记录机体在 PVE 会话中的动态数据（如当前血量、能量、是否阵亡等）。
    这些数据会在战斗前后由 BattleBridge 进行同步和更新。
    """
    entity_id: str                    # 机体实例 ID
    current_hp: int
    current_en: int
    max_hp: int
    max_en: int
    last_combat_time: float           # 上次战斗结束的时间戳，用于计算战间恢复
    is_alive: bool = True

class PveSquadState(BaseModel):
    """己方队伍在 PVE 里的状态与锁死配置"""
    members: List[PveEntityState] = Field(default_factory=list)
    locked_config: Dict[str, Any] = Field(default_factory=dict)

class PveEnemyState(BaseModel):
    """特定事件中敌方NPC的残血/特殊状态"""
    event_index: int
    entity_state: PveEntityState
    enemy_template_id: str

# -----------------
# 战后收益 (Rewards)
# -----------------
class PvePendingRewards(BaseModel):
    """临时背包 / 风险存放栈"""
    equipments: List[Dict[str, Any]] = Field(default_factory=list)
    items: List[Dict[str, Any]] = Field(default_factory=list)

# -----------------
# 会话根 (Session)
# -----------------
class PveSessionData(BaseModel):
    """
    PVE 会话完整状态包。
    
    它是 PVE 模块的核心上下文，记录了事件序列、队伍状态、敌方状态以及待结算的战利品。
    该对象可以被全量 JSON 序列化并存储在数据库中用于断线续连。
    """
    session_id: int                   # 会话唯一 ID
    user_id: int                      # 所属玩家 ID
    region_id: str                    # 副本区域唯一 ID
    current_layer: int = 1            # 当前所在的层级 (多层副本扩展用)
    status: SessionStatus = SessionStatus.ACTIVE
    
    event_sequence: EventSequence     # 事件序列 (替代原小地图)
    
    squad_state: PveSquadState
    enemy_states: Dict[int, PveEnemyState] = Field(default_factory=dict)  # key: 事件索引
    
    pending_rewards: PvePendingRewards = Field(default_factory=PvePendingRewards)
    credits_earned: int = 0
    
    created_at: float
    last_heartbeat: float
