import pytest
from src.pve.map_generator import TileMapGenerator, ContentPopulator, PathValidator
from src.pve.enums import NodeType

def test_tile_generation_and_population():
    """测试真正的地块拼装和连通性！"""
    
    # 1. 组装空地块（固定3x3）
    gen = TileMapGenerator(tiles_path="data/pve_tiles.json")
    
    # 试着在 2x2 的大格局网格中（总计6x6 = 36格子面积）铺路
    graph = gen.generate(grid_w=2, grid_h=2)
    
    # a. 起点终点检查
    start_node = graph.get_node(graph.start_node_id)
    boss_node = graph.get_node(graph.boss_node_id)
    assert start_node is not None
    assert boss_node is not None
    assert start_node.node_type == NodeType.START
    
    # b. 最核心：检查拼出来的地图是不是死路
    # 必须保证能从起点走到终点
    assert PathValidator.is_solvable(graph) is True
    
    # c. 路径长度
    plen = PathValidator.minimum_path_length(graph)
    assert plen > 2  # Boss不在脸前起码
    
    # 2. 撒上怪和宝箱 (Populate)
    mock_config = {
        "boss_template": "omega_boss",
        "elite_pool": ["mega_guard"],
        "normal_pool": ["zaku", "dom"],
        "hidden_encounter_rate": 0.5,
        "treasure_count": [1, 2] # 必定有至少一个死胡同出宝箱
    }
    
    populated_graph = ContentPopulator.populate(graph, mock_config)
    
    # d. 检验内容是否写入成功
    # Boss 点有没刷成红名
    p_boss_node = populated_graph.get_node(populated_graph.boss_node_id)
    assert p_boss_node.node_type == NodeType.BOSS
    assert p_boss_node.event_id == "omega_boss"
    
    # 咽喉守卫门神存在（在长路里）
    found_elite = any([n for n in populated_graph.nodes.values() if n.node_type == NodeType.ENEMY_VISIBLE and n.event_id == "mega_guard"])
    assert found_elite is True
    
    # 是不是散布了暗雷
    hiddens = [n for n in populated_graph.nodes.values() if n.node_type == NodeType.ENEMY_HIDDEN]
    # 连通网上大概率触发暗雷 (36格子如果有一半是路，0.5概率应该至少有一两个)
    assert len(hiddens) > 0
    
    print(f"Gen Success! Tot nodes: {len(populated_graph.nodes)}, Hidden: {len(hiddens)}, shortest_path: {plen}")
    
