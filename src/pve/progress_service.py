import random
import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, List

from src.database.models import UserPveProgress
from src.loader import DataLoader
from src.pve.enums import ZoneStatus

class PveProgressService:
    """战略与战术层：PVE 大区域准入与小区域 (Zone) 进度管理服务"""

    @staticmethod
    async def get_or_create_progress(db: AsyncSession, user_id: int) -> UserPveProgress:
        """获取玩家的 PVE 进度记录，若无则自动创建"""
        stmt = select(UserPveProgress).where(UserPveProgress.user_id == user_id)
        result = await db.execute(stmt)
        progress = result.scalar_one_or_none()

        if not progress:
            progress = UserPveProgress(
                user_id=user_id,
                progress_data={},
                hidden_refresh_data={}
            )
            db.add(progress)
            await db.flush()
            
        return progress

    @classmethod
    async def initialize_progress(cls, db: AsyncSession, user_id: int, region_id: str, loader: DataLoader) -> UserPveProgress:
        """玩家首次进入大区域时，初始化该区域的进度状态，开放首发节点"""
        progress = await cls.get_or_create_progress(db, user_id)
        
        # 深拷贝以触发 SQLAlchemy JSON 字段更新
        progress_data = dict(progress.progress_data)
        
        if region_id not in progress_data:
            progress_data[region_id] = {}
            # 找到首发节点 (unlock_requires = None 且 is_hidden = False)
            region_config = loader.get_region_config(region_id)
            for zone in region_config.zones:
                if zone.unlock_requires is None and not zone.is_hidden:
                    progress_data[region_id][zone.zone_id] = ZoneStatus.UNLOCKED.value
                elif zone.is_hidden:
                    progress_data[region_id][zone.zone_id] = ZoneStatus.LOCKED.value  # 隐藏节点一开始统统锁住
                else:
                    progress_data[region_id][zone.zone_id] = ZoneStatus.LOCKED.value
            
            progress.progress_data = progress_data
            
        return progress

    @classmethod
    async def get_region_status(cls, db: AsyncSession, user_id: int, region_id: str, loader: DataLoader) -> Dict[str, str]:
        """获取大区域下所有 Zone 的解锁状态，并自动骰出隐藏节点的可用状态"""
        # 首先尝试初始化
        progress = await cls.initialize_progress(db, user_id, region_id, loader)
        
        status_dict = progress.progress_data.get(region_id, {})
        
        # 单次探索为周期的隐藏节点刷新
        # (每次拉取状态时骰出，但由于无单次探索的生命周期键，用当天的日期或临时标记持久化？
        # 用户需求：针对单次探索(就是当前活跃 session) => 我们不在进度表持久化刷新结果，
        # 而是在内存返回，或用一个标记来做。如果每次打开界面都刷新不好。
        # 简单起见，既然 PveSession 开始前会有选关，就说明不在 Session 内，所以隐藏节点刷新可以做在进入选关界面时，刷新一次当日/当次的状态，暂定当日如果没刷过就刷一次，退出后仍保留直到第二天。
        # 假设这里只是查询)
        
        # 我们在这里处理当日隐藏点刷新：
        # 根据需求 "隐藏点刷新针对单次探索"，这应该是在创建 PveSession (或进入区域时)
        # 但是选区域在 PveSession 创建前。因此我们需要在这个接口里临时决断隐藏点是否激活。
        # 这里用一种简单方式：记录当天该区域是否已经 roll 过隐藏点。
        
        today_key = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        
        hidden_data = dict(progress.hidden_refresh_data)
        if today_key not in hidden_data:
            hidden_data = {today_key: {}}
            
        region_hidden_cache = hidden_data[today_key].setdefault(region_id, {})
        data_changed = False
        
        region_config = loader.get_region_config(region_id)
        
        # 复制状态以供返回
        return_dict = dict(status_dict)
        
        for zone in region_config.zones:
            if zone.is_hidden:
                # 隐藏节点刷新条件: 前置节点已经被 cleared (或者没有前置)
                is_prereq_cleared = False
                if zone.unlock_requires is None:
                    is_prereq_cleared = True
                else:
                    is_prereq_cleared = (status_dict.get(zone.unlock_requires) == ZoneStatus.CLEARED.value)

                if is_prereq_cleared:
                    if zone.zone_id not in region_hidden_cache:
                        # 还没 roll 过，roll 一把
                        success = random.random() < (zone.spawn_chance or 0.0)
                        region_hidden_cache[zone.zone_id] = success
                        data_changed = True

                    if region_hidden_cache[zone.zone_id]:
                        # 成功刷新出来
                        return_dict[zone.zone_id] = ZoneStatus.AVAILABLE.value
                    else:
                        return_dict[zone.zone_id] = ZoneStatus.HIDDEN.value
                else:
                    return_dict[zone.zone_id] = ZoneStatus.LOCKED.value # 前置没打过，自然是锁的
                    
        if data_changed:
            progress.hidden_refresh_data = hidden_data
            # 在 API db 注入时会自动 commit
            
        return return_dict

    @classmethod
    async def mark_zone_cleared(cls, db: AsyncSession, user_id: int, region_id: str, zone_id: str, loader: DataLoader) -> List[str]:
        """通关后标记 cleared 并触发后续 Zone 的解锁，返回新解锁的 zone_id 列表"""
        progress = await cls.get_or_create_progress(db, user_id)
        progress_data = dict(progress.progress_data)
        
        if region_id not in progress_data:
            progress_data[region_id] = {}
        
        status_dict = progress_data[region_id]
        status_dict[zone_id] = ZoneStatus.CLEARED.value

        # 查找后续解锁节点
        new_unlocked = []
        region_config = loader.get_region_config(region_id)
        for zone in region_config.zones:
            if zone.unlock_requires == zone_id and status_dict.get(zone.zone_id) in (None, ZoneStatus.LOCKED.value):
                if not zone.is_hidden:
                    status_dict[zone.zone_id] = ZoneStatus.UNLOCKED.value
                    new_unlocked.append(zone.zone_id)
                # 隐藏节点不在此时解锁为 unlocked，而是等下次进入界面时通过 get_region_status 概率刷新。
                
        progress.progress_data = progress_data
        return new_unlocked
