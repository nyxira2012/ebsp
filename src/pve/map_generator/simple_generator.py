from src.pve.models import MapGraph, MapNode
from src.pve.enums import NodeType

class SimpleMapGenerator:
    """极简直线地图生成器，仅用于 Phase 1 测试"""
    
    @staticmethod
    def generate(region_id: str, layer: int) -> MapGraph:
        """生成一个简单的 0 -> 1 -> 2 -> 3 直线地图"""
        nodes = {}
        
        # 节点 0: 起点 (已揭示)
        nodes[0] = MapNode(id=0, x=0, y=0, node_type=NodeType.START, revealed=True, cleared=True, neighbors=[1])
        # 节点 1: 安全区
        nodes[1] = MapNode(id=1, x=1, y=0, node_type=NodeType.EMPTY, revealed=False, neighbors=[0, 2])
        # 节点 2: 明雷守卫
        nodes[2] = MapNode(id=2, x=2, y=0, node_type=NodeType.ENEMY_VISIBLE, event_id="station_guard", revealed=False, neighbors=[1, 3])
        # 节点 3: Boss
        nodes[3] = MapNode(id=3, x=3, y=0, node_type=NodeType.BOSS, event_id="station_guardian", revealed=False, neighbors=[2])
        
        return MapGraph(
            width=4,
            height=1,
            nodes=nodes,
            start_node_id=0,
            boss_node_id=3
        )
