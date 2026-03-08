import json
import random
from typing import List, Dict, Optional, Tuple

from src.pve.models import MapGraph, MapNode
from src.pve.enums import NodeType

class TileMapGenerator:
    """预制件拼接地图生成器 (Tile-based Procedural Generation)。

    该类通过宏观 Random Walk 与微观 Chunk 展开相结合的方式，动态生成连通的 PVE 图案。
    """
    
    def __init__(self, tiles_path: str = "data/pve_tiles.json"):
        """初始化生成器并加载预制件。

        Args:
            tiles_path (str): 预制件 JSON 文件的绝对或相对路径。
        """
        with open(tiles_path, "r", encoding="utf-8") as f:
            self.tiles = json.load(f)
            
        self.start_tiles = [t for t in self.tiles if "start_point" in t["id"]]
        if not self.start_tiles:
            self.start_tiles = [self.tiles[0]] # fallback
            
        self.boss_tiles = [t for t in self.tiles if "boss_room" in t["id"]]
        if not self.boss_tiles:
            self.boss_tiles = [self.tiles[-1]]
            
        self.normal_tiles = [t for t in self.tiles if "cross" in t["id"]]
        if not self.normal_tiles:
            # Fallback if no cross is found
            self.normal_tiles = [t for t in self.tiles if "start_point" not in t["id"] and "boss_room" not in t["id"]]

    def generate(self, grid_w: int, grid_h: int) -> MapGraph:
        """根据指定的宏观网格尺寸生成地图。

        Args:
            grid_w (int): 宏观网格的宽度（以 Chunk 为单位）。
            grid_h (int): 宏观网格的高度（以 Chunk 为单位）。

        Returns:
            MapGraph: 生成的全局连通图结构。
        """
        # 每个大网格的尺寸（目前固定3x3）
        chunk_size = 3 
        
        # 1. 生成一条主干道 (Random Walk 从左上到右下)
        cx, cy = 0, 0
        target_x, target_y = grid_w - 1, grid_h - 1
        path = [(cx, cy)]
        
        while cx != target_x or cy != target_y:
            moves = []
            if cx < target_x: moves.append((1, 0))
            if cy < target_y: moves.append((0, 1))
            
            dx, dy = random.choice(moves)
            cx += dx
            cy += dy
            path.append((cx, cy))
            
        # 1.5 增加发散的分支枝丫
        branch_tiles = []
        num_branches = int((grid_w + grid_h) / 2)
        for _ in range(num_branches):
            bx, by = random.choice(path)
            b_moves = [(1,0), (0,1), (-1,0), (0,-1)]
            for _step in range(random.randint(1, 2)):
                dx, dy = random.choice(b_moves)
                nx, ny = bx + dx, by + dy
                # 不在主路径且不超出网格，则算作有效分支地块
                if 0 <= nx < grid_w and 0 <= ny < grid_h and (nx, ny) not in path and (nx, ny) not in branch_tiles:
                    branch_tiles.append((nx, ny))
                    bx, by = nx, ny

        # 2. 为路径上的点分配地块 (Chunk)
        placed_chunks = {} # (chunk_x, chunk_y) -> tile_dict
        
        for i, (px, py) in enumerate(path):
            if i == 0:
                chunk = random.choice(self.start_tiles)
            elif i == len(path) - 1:
                chunk = random.choice(self.boss_tiles)
            else:
                chunk = random.choice(self.normal_tiles)
                
            placed_chunks[(px, py)] = chunk
            
        for (bx, by) in branch_tiles:
            placed_chunks[(bx, by)] = random.choice(self.normal_tiles)
            
        # 3. 将 Chunk 展开并汇聚成单个大图 MapGraph
        # 计算全局尺寸
        full_width = grid_w * chunk_size
        full_height = grid_h * chunk_size
        
        global_nodes = {}
        node_id_counter = 0
        start_node_id = 0
        boss_node_id = 0
        
        # 为了连通性，我们需要记录每个 Chunk 在全局坐标系下的边界开孔 (entry_points)
        # 用 {(gx, gy): node_id} 查字典
        node_lookup = {}
        
        # 第一遍展开
        for (px, py), chunk in placed_chunks.items():
            base_x = px * chunk_size
            base_y = py * chunk_size
            
            # 建立这个区块内部的映射表 local_index -> global_node_id
            local_to_global = {}
            
            for local_idx, n_def in enumerate(chunk["nodes"]):
                lx = n_def["x"]
                ly = n_def["y"]
                attrs = n_def.get("attrs", {})
                
                ntype = NodeType.EMPTY
                if attrs.get("is_start"):
                    ntype = NodeType.START
                elif attrs.get("is_boss"):
                    ntype = NodeType.BOSS
                    
                global_x = base_x + lx
                global_y = base_y + ly
                
                node = MapNode(
                    id=node_id_counter,
                    x=global_x,
                    y=global_y,
                    node_type=ntype,
                    revealed=False if ntype != NodeType.START else True,
                    cleared=True if ntype == NodeType.START else False
                )
                
                global_nodes[node_id_counter] = node
                local_to_global[local_idx] = node_id_counter
                node_lookup[(global_x, global_y)] = node_id_counter
                
                if ntype == NodeType.START:
                    start_node_id = node_id_counter
                if ntype == NodeType.BOSS:
                    boss_node_id = node_id_counter
                    
                node_id_counter += 1
                
            # 连接区块内部的边
            for edge in chunk["edges"]:
                n1_local, n2_local = edge
                # 只在连边的节点存在时增加
                if n1_local in local_to_global and n2_local in local_to_global:
                    nid1 = local_to_global[n1_local]
                    nid2 = local_to_global[n2_local]
                    global_nodes[nid1].neighbors.append(nid2)
                    global_nodes[nid2].neighbors.append(nid1)
                
        # 4. 缝合 Chunk 之间的交界边
        # 只要坐标相邻，就算是连上了
        for (gx, gy), nid in list(node_lookup.items()):
            for dx, dy in [(0,1), (1,0), (0,-1), (-1,0)]:
                nx, ny = gx + dx, gy + dy
                neighbor_id = node_lookup.get((nx, ny))
                if neighbor_id is not None and neighbor_id != nid:
                    if neighbor_id not in global_nodes[nid].neighbors:
                        global_nodes[nid].neighbors.append(neighbor_id)
                        
        map_graph = MapGraph(
            width=full_width,
            height=full_height,
            nodes=global_nodes,
            start_node_id=start_node_id,
            boss_node_id=boss_node_id
        )
        
        return map_graph
