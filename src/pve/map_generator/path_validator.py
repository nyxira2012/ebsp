import copy
from typing import List, Optional

from src.pve.models import MapGraph

class PathValidator:
    """地图路径连通性校验器。

    用于确保生成的地图在算法逻辑上是“可解”的，并提供路径长度计算等辅助功能。
    """
    
    @staticmethod
    def is_solvable(graph: MapGraph) -> bool:
        """检查地图是否可以从起点到达终点。

        Args:
            graph (MapGraph): 待校验的地图图模型。

        Returns:
            bool: 如果存在通路则返回 True。
        """
        path = graph.find_path(graph.start_node_id, graph.boss_node_id)
        return path is not None and len(path) > 0
        
    @staticmethod
    def minimum_path_length(graph: MapGraph) -> int:
        """计算从起点到终点的最短路径步数。

        Args:
            graph (MapGraph): 目标地图。

        Returns:
            int: 步数，如果不可达则返回极大值。
        """
        path = graph.find_path(graph.start_node_id, graph.boss_node_id)
        if path is None:
            return 999999
        return len(path) - 1 # 扣除起点自己

    @staticmethod
    def is_chokepoint(graph: MapGraph, node_id: int) -> bool:
        """判定一个节点是否为“咽喉点”。

        如果移除某节点（或将其设为不通）后，起点到终点的路径中断，则该点即为咽喉点。

        Args:
            graph (MapGraph): 地图数据。
            node_id (int): 待判定的节点 ID。

        Returns:
            bool: 如果是关键路径上的唯一瓶颈则返回 True。
        """
        if node_id == graph.start_node_id or node_id == graph.boss_node_id:
            return False
            
        # 做图的一个克隆或者临时移除某点的连线边
        # 图的规模不大，复制一次无妨
        # 但我们用 BFS 遮蔽掉被斩断的节点更直观
        temp_graph = copy.deepcopy(graph)
        broken_node = temp_graph.get_node(node_id)
        if broken_node:
            broken_node.neighbors = [] # 这个点变孤岛不通车
            
        path = temp_graph.find_path(temp_graph.start_node_id, temp_graph.boss_node_id)
        return path is None # 如果切断后路断了，说明它是不可跳过的咽喉点
