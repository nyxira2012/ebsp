import time
from typing import Optional, Dict, Any

from src.pve.models import PveSessionData, PveSquadState, PveEntityState, EventSequence
from src.pve.enums import SessionStatus
from src.pve.event_generator import EventSequenceGenerator
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

        该过程包含事件序列生成，以及根据战前锁定配置初始化队伍状态。

        Args:
            user_id (int): 所属玩家 ID。
            region_id (str): 目标副本区域 ID。
            mothership_config (Any): 母舰配置数据。
            locked_config (dict): 战前锁定的快照配置。
            loader (Any, optional): 资源加载器。

        Returns:
            PveSessionData: 创建成功的会话实例对象。
        """
        # 1. 尝试从 loader 获取区域配置，供事件序列生成使用
        region_config = None
        if loader:
            try:
                region_config = loader.get_region_config(region_id)
            except Exception:
                pass

        # 2. 生成事件序列（替代原地图生成）
        event_sequence: EventSequence = EventSequenceGenerator.generate(region_config)

        # 3. 构造队伍状态
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
            status=SessionStatus.ACTIVE,
            event_sequence=event_sequence,
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
