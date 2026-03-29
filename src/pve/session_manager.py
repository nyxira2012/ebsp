import time
from typing import Optional, Dict, Any, List

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
    _user_index: Dict[int, int] = {}  # user_id -> session_id 二级索引
    _next_id: int = 1
    
    @classmethod
    def create_session(cls, user_id: int, region_id: str, zone_id: str, mothership_config: Any, locked_config: dict, loader: Any = None) -> PveSessionData:
        """初始化一个全新的 PVE 核心会话。"""
        # Guard user concurrency
        if cls.get_session_by_user(user_id):
            raise ValueError(f"User {user_id} already has an active PVE session")

        # 1. 获取区域与子区域配置
        zone_config = None
        if loader:
            try:
                zone_config = loader.get_zone_config(region_id, zone_id)
            except Exception:
                pass

        # 2. 生成事件序列
        event_sequence: EventSequence = EventSequenceGenerator.generate(zone_config)

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
            zone_id=zone_id,
            status=SessionStatus.ACTIVE,
            event_sequence=event_sequence,
            squad_state=squad_state,
            created_at=time.time(),
            last_heartbeat=time.time()
        )
        
        cls._sessions[cls._next_id] = session
        cls._user_index[user_id] = cls._next_id
        cls._next_id += 1
        return session

    @classmethod
    def get_session_by_user(cls, user_id: int) -> Optional[PveSessionData]:
        """根据用户 ID 获取会话（O(1) 通过二级索引）。

        Args:
            user_id (int): 目标用户 ID。

        Returns:
            Optional[PveSessionData]: 会话实例，若不存在则返回 None。
        """
        session_id = cls._user_index.get(user_id)
        if session_id:
            return cls._sessions.get(session_id)
        return None

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
        session = cls._sessions.get(session_id)
        if session:
            del cls._sessions[session_id]
            cls._user_index.pop(session.user_id, None)

    @classmethod
    def get_expired_sessions(cls, timeout_seconds: float) -> List[int]:
        """获取超时的会话 ID 列表。

        Args:
            timeout_seconds (float): 超时阈值（秒）。

        Returns:
            List[int]: 超时会话的 ID 列表。
        """
        now = time.time()
        return [
            sid for sid, session in cls._sessions.items()
            if now - session.last_heartbeat > timeout_seconds
        ]
