from typing import List, Dict, Optional, Any
from pydantic import BaseModel, ConfigDict, Field
from .enums import SessionStatus, NodeType, EventType

# -----------------
# 微观地图 (Map)
# -----------------
class MapNode(BaseModel):
    """地图上的单个节点。

    Attributes:
        id (int): 节点全局唯一 ID。
        x (int): 节点逻辑 X 坐标。
        y (int): 节点逻辑 Y 坐标。
        node_type (NodeType): 节点类型 (如 START, BOSS, ENEMY_VISIBLE)。
        event_id (Optional[str]): 关联的事件或配置 ID (如敌人模板 ID)。
        revealed (bool): 该地块是否已对玩家揭示（战争迷雾）。
        cleared (bool): 该地块的事件是否已被处理完毕。
        neighbors (List[int]): 相邻节点的 ID 列表。
    """
    id: int
    x: int
    y: int
    node_type: NodeType = NodeType.EMPTY
    event_id: Optional[str] = None
    revealed: bool = False
    cleared: bool = False
    neighbors: List[int] = Field(default_factory=list)

class MapGraph(BaseModel):
    """点阵地图的核心图数据结构。

    使用邻接表存储拓扑关系，支持非规则网格。

    Attributes:
        width (int): 网格参考宽度。
        height (int): 网格参考高度。
        nodes (Dict[int, MapNode]): 节点 ID 到节点对象的映射字典。
        start_node_id (int): 玩家初始传送点的节点 ID。
        boss_node_id (int): 最终关底目标点的节点 ID。
    """
    width: int
    height: int
    nodes: Dict[int, MapNode] = Field(default_factory=dict)
    start_node_id: int = 0
    boss_node_id: int = 0

    def get_node(self, node_id: int) -> Optional[MapNode]:
        """获取指定 ID 的节点。

        Args:
            node_id (int): 目标节点 ID。

        Returns:
            Optional[MapNode]: 节点实例，若不存在则返回 None。
        """
        return self.nodes.get(node_id)

    def get_neighbors(self, node_id: int) -> List[MapNode]:
        """获取指定节点的所有相邻节点对象。

        Args:
            node_id (int): 核心节点 ID。

        Returns:
            List[MapNode]: 相邻节点的实例列表。
        """
        node = self.get_node(node_id)
        if not node:
            return []
        return [self.nodes[n_id] for n_id in node.neighbors if n_id in self.nodes]

    def find_path(self, start_id: int, end_id: int) -> Optional[List[int]]:
        """计算两个节点之间的最短路径。

        使用 BFS 算法实现。

        Args:
            start_id (int): 起始节点 ID。
            end_id (int): 终点节点 ID。

        Returns:
            Optional[List[int]]: 包含路径上所有节点 ID 的列表（含起终点）。
                如果路径不连通，则返回 None。
        """
        from collections import deque
        if start_id == end_id:
            return [start_id]
            
        queue = deque([[start_id]])
        visited = {start_id}
        
        while queue:
            path = queue.popleft()
            curr = path[-1]
            if curr == end_id:
                return path
                
            node = self.get_node(curr)
            if not node:
                continue
                
            for neighbor_id in node.neighbors:
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append(path + [neighbor_id])
                    
        return None

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
        """TODO 列表长度。"""
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
    """特定格子敌方NPC残血/特殊状态"""
    node_id: int
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
