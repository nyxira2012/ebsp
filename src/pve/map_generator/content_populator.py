import random
from typing import List, Dict

from src.pve.models import MapGraph
from src.pve.enums import NodeType

class ContentPopulator:
    """地图内容注入器。

    负责在仅有拓扑结构的 MapGraph 上，根据配置概率填充事件节点（如怪物、宝箱、障碍等）。
    """
    
    @staticmethod
    def populate(graph: MapGraph, config: dict) -> MapGraph:
        """依照配置规则填充地图内容。

        工作流：
        1. 设定 Boss 节点及守卫。
        2. 计算主路径并在沿途布置挑战。
        3. 在死胡同散布奖励。
        4. 在空地按概率铺设暗雷与障碍。

        Args:
            graph (MapGraph): 待填充的空拓扑地图。
            config (dict): 填充规则配置字典。

        Returns:
            MapGraph: 填充完毕的具备内容的地图。
        """
        # 提取配置参数（提供默认值兜底）
        boss_template = config.get("boss_template", "boss_default")
        elite_pool = config.get("elite_pool", ["elite_1", "elite_2"])
        normal_pool = config.get("normal_pool", ["mob_1", "mob_2"])
        hidden_encounter_rate = config.get("hidden_encounter_rate", 0.2)
        treasure_count_range = config.get("treasure_count", [1, 3])
        
        # 1. 设置 Boss 节点
        boss_node = graph.get_node(graph.boss_node_id)
        if boss_node:
            boss_node.node_type = NodeType.BOSS
            boss_node.event_id = boss_template
            
        # 2. 找到首末节点的最短路径，定义为主路
        # 使用 MapGraph 自带的寻路逻辑
        path = graph.find_path(graph.start_node_id, graph.boss_node_id)
        if not path:
            return graph # 异常防断路，原样返回
            
        main_path_set = set(path)
        
        # 3. 在走向 Boss 的最后几步布置守卫门神（咽喉点明雷）
        if len(path) > 2:
            guard_id = path[-2] # Boss前一个点
            guard_node = graph.get_node(guard_id)
            if guard_node and guard_node.node_type == NodeType.EMPTY:
                guard_node.node_type = NodeType.ENEMY_VISIBLE
                guard_node.event_id = random.choice(elite_pool)
                
        # 4. 找出所有的死胡同 (度数为1的节点，且不是主路、起点或终点)
        dead_ends = []
        for n_id, node in graph.nodes.items():
            if n_id == graph.start_node_id or n_id == graph.boss_node_id:
                continue
            edges = len(node.neighbors)
            if edges == 1 and n_id not in main_path_set:
                dead_ends.append(n_id)
                
        # 5. 在死胡同放宝箱
        num_treasures = random.randint(treasure_count_range[0], treasure_count_range[1])
        random.shuffle(dead_ends)
        for i, n_id in enumerate(dead_ends):
            if i >= num_treasures:
                break
            # 放宝箱
            treasure_node = graph.get_node(n_id)
            if treasure_node and treasure_node.node_type == NodeType.EMPTY:
                treasure_node.node_type = NodeType.TREASURE
                treasure_node.event_id = "random_chest"
                
        # 6. 在所有剩下的路上铺暗雷和资源点
        for n_id, node in graph.nodes.items():
            if node.node_type != NodeType.EMPTY:
                continue # 不要覆盖已经分配内容的地格
                
            if n_id == graph.start_node_id:
                continue
                
            # 依概率刷暗雷
            if random.random() < hidden_encounter_rate:
                node.node_type = NodeType.ENEMY_HIDDEN
                node.event_id = random.choice(normal_pool)
            elif random.random() < 0.05: # 5% 的低概率刷出拦路石
                node.node_type = NodeType.OBSTACLE
                node.event_id = "debris"
                
        return graph
