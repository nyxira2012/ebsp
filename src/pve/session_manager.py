import time
from typing import Optional, Dict, Any

from src.pve.models import PveSessionData, PveSquadState, PveEntityState
from src.pve.enums import SessionStatus
from src.pve.map_generator.tile_map_generator import TileMapGenerator
from src.factory import MechaFactory

class PveSessionManager:
    """PVE 会话生命周期管理器。

    负责在内存中管理所有活跃的 PVE 副本会话，包括初始化创建、按 ID 查询以及销毁。
    目前处于 Phase 2 内存实现阶段。
    """
    
    _sessions: Dict[int, PveSessionData] = {}
    _next_id: int = 1
    
    @classmethod
    def create_session(cls, user_id: int, region_id: str, mothership_config: Any, locked_config: dict, loader: Any = None) -> PveSessionData:
        """初始化一个全新的 PVE 核心会话。

        该过程包含地图生成、地格事件散布、以及根据战前锁定配置初始化队伍状态。

        Args:
            user_id (int): 所属玩家 ID。
            region_id (str): 目标副本区域 ID。
            mothership_config (Any): 母舰配置数据。
            locked_config (dict): 战前锁定的快照配置。
            loader (Any, optional): 资源加载器。

        Returns:
            PveSessionData: 创建成功的会话实例对象。
        """
        # 1. 临时准入检查（由上层处理，或在这）
        
        # 2. 生成地图 (调用 MapGenerator)
        mg = TileMapGenerator()
        
        # 尝试从 loader 解析 region_id，决定地图大区长宽
        grid_w, grid_h = 4, 4
        if loader:
            try:
                region_config = loader.get_region_config(region_id)
                r_size = getattr(region_config, 'map_size', [4, 4])
                grid_w, grid_h = r_size[0], r_size[1]
            except Exception:
                pass
                
        graph = mg.generate(grid_w=grid_w, grid_h=grid_h)
        
        from src.pve.map_generator.content_populator import ContentPopulator
        config = {
            "boss_template": "boss_default",
            "elite_pool": ["elite_1", "elite_2"],
            "normal_pool": ["mob_1", "mob_2"],
            "hidden_encounter_rate": 0.20,
            "treasure_count": [1, 3]
        }
        graph = ContentPopulator.populate(graph, config)
        
        # 3. 构造队伍状态
        # 从 locked_config 与 factory 构造真实战前状态
        members = []
        mechas_config = locked_config.get("mechas", [])
        
        for m_data in mechas_config:
            members.append(
                PveEntityState(
                    entity_id=m_data.get("mecha_id", "fallback_id"),
                    current_hp=m_data.get("max_hp", 1000),
                    current_en=m_data.get("max_en", 100),
                    max_hp=m_data.get("max_hp", 1000),
                    max_en=m_data.get("max_en", 100),
                    last_combat_time=time.time(),
                    is_alive=True
                )
            )
            
        squad_state = PveSquadState(members=members, locked_config=locked_config)
        
        # 4. 初始化会话
        session = PveSessionData(
            session_id=cls._next_id,
            user_id=user_id,
            region_id=region_id,
            current_layer=1,
            current_node_id=graph.start_node_id,
            status=SessionStatus.ACTIVE,
            map_graph=graph,
            squad_state=squad_state,
            created_at=time.time(),
            last_heartbeat=time.time()
        )
        
        cls._sessions[cls._next_id] = session
        cls._next_id += 1
        return session

    @classmethod
    def get_session(cls, session_id: int) -> Optional[PveSessionData]:
        """获取指定 ID 的会话实例。

        Args:
            session_id (int): 目标会话 ID。

        Returns:
            Optional[PveSessionData]: 会话实例，若不存在则返回 None。
        """
        session = cls._sessions.get(session_id)
        if session:
            session.last_heartbeat = time.time()
        return session
        
    @classmethod
    def destroy_session(cls, session_id: int):
        """销毁内存中的指定会话。

        Args:
            session_id (int): 要销毁的会话 ID。
        """
        if session_id in cls._sessions:
            del cls._sessions[session_id]
