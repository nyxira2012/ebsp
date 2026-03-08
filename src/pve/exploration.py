from dataclasses import dataclass
from typing import List, Optional
from typing import List, Optional
from src.pve.models import MapGraph, MapNode
from src.pve.enums import NodeType

@dataclass
class MoveResult:
    """地图移动执行的结果数据封装。

    Attributes:
        reached_node_id (int): 角色最终实际停下的节点 ID。
        path_taken (List[int]): 实际走过的节点 ID 序列。
        truncated (bool): 移动是否因为障碍、机动力不足或遭遇战而被强制截断。
        truncation_reason (Optional[str]): 截断的具体原因 (如 "node_block", "hidden_encounter")。
        triggered_event (Optional[NodeType]): 目标节点所携带的事件类型（如有）。
        revealed_nodes (List[int]): 本次移动行为新揭示的节点 ID 列表。
    """
    reached_node_id: int          # 实际到达节点
    path_taken: List[int]         # 实际走过的路径
    truncated: bool               # 是否被截停
    truncation_reason: Optional[str]
    triggered_event: Optional[NodeType]  # 到达节点的事件类型
    revealed_nodes: List[int]     # 本次移动揭示的节点

class ExplorationController:
    """探索控制器。

    负责处理玩家在地图上的交互逻辑，如移动寻路、战争迷雾揭示以及截停判定。
    该类为纯逻辑封装，直接操作 MapGraph 状态。
    """
    

    @classmethod
    def move(cls, graph: MapGraph, current_node_id: int, target_node_id: int, max_movement_points: int) -> MoveResult:
        """执行网格路径移动。

        计算从当前点到目标点的路径，并根据玩家的机动力(MP)以及沿途的障碍物/事件进行截断判定。

        Args:
            graph (MapGraph): 当前地图图模型。
            current_node_id (int): 玩家当前所在节点 ID。
            target_node_id (int): 玩家点击的目标节点 ID。
            max_movement_points (int): 玩家本次移动允许消耗的最大点数。

        Returns:
            MoveResult: 包含最终达到的坐标、路径和截断信息的详细结果。
        """
        path = graph.find_path(current_node_id, target_node_id)
        if not path:
            # 不可达直接返回原节点
            return MoveResult(current_node_id, [current_node_id], True, "unreachable", None, [])
            
        # 抛去起点
        path = path[1:]
        
        # 判断机动力截断
        if len(path) > max_movement_points:
            path = path[:max_movement_points]
            
        actual_path = []
        truncated = False
        reason = None
        
        # 遍历路线上经过的点，判断截停
        for node_id in path:
            node = graph.get_node(node_id)
            if not node:
                break
                
            actual_path.append(node_id)
            
            # 明雷或未清理的障碍，会直接把玩家截停在这个点
            # 实际上停在阻挡格子，也就是这步算是踩上去触发事件
            if node.node_type in [NodeType.ENEMY_VISIBLE, NodeType.BOSS, NodeType.OBSTACLE] and not node.cleared:
                truncated = True
                reason = "node_block"
                break
            
            # 暗雷拦截逻辑
            if node.node_type == NodeType.ENEMY_HIDDEN and not node.cleared:
                truncated = True
                reason = "hidden_encounter"
                break
                
        if not actual_path:
            return MoveResult(current_node_id, [current_node_id], truncated, reason, None, [])
            
        reached_node_id = actual_path[-1]
        reached_node = graph.get_node(reached_node_id)
        
        revealed_nodes = []
        
        # 所有途中经过的点设为已揭示
        for nid in actual_path:
            n = graph.get_node(nid)
            if n and not n.revealed:
                n.revealed = True
                revealed_nodes.append(nid)
                
        # 停下的点如果是空地或者已被打通的，自动揭示它的邻居
        if reached_node and (reached_node.cleared or reached_node.node_type in [NodeType.EMPTY, NodeType.START]):
            for n_id in reached_node.neighbors:
                neighbor_node = graph.get_node(n_id)
                if neighbor_node and not neighbor_node.revealed:
                    neighbor_node.revealed = True
                    revealed_nodes.append(n_id)
                    
        return MoveResult(
            reached_node_id=reached_node_id,
            path_taken=actual_path,
            truncated=truncated,
            truncation_reason=reason,
            triggered_event=reached_node.node_type if reached_node and not reached_node.cleared else None,
            revealed_nodes=revealed_nodes
        )
