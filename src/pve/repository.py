import json
from typing import Optional, Dict

class PveRepository:
    """负责将 PveSessionData 在 Pydantic 和 SQLAlchemy ORM JSONB 之间做互换和存储
    """
    
    @staticmethod
    def get_by_user(db_session, user_id: int):
        from src.database.models import PveSession
        from sqlalchemy import select
        stmt = select(PveSession).where(PveSession.user_id == user_id, PveSession.status.in_(["active", "paused"]))
        # 因为在异步上下文中，暂不写死 await，由服务层去执行
        return stmt
        
    @staticmethod
    def save_or_update(db_session, pve_session_data):
        """Phase 2 中会调用它将内存模型固化进 DB JSON 字段"""
        from src.database.models import PveSession
        
        # pve_session_data.model_dump() 是 Pydantic 字典
        dumped = pve_session_data.model_dump()
        
        rec = PveSession(
            user_id=pve_session_data.user_id,
            status=pve_session_data.status.value,
            region_id=pve_session_data.region_id,
            zone_id=pve_session_data.zone_id,
            session_data=dumped, # Pydantic v2 直接扔dict即可, SQLAlchemy 会序列化为 JSON
            idempotency_key=f"pve_{pve_session_data.user_id}_{pve_session_data.session_id}"
        )
        db_session.add(rec)
