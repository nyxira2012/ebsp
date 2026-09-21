from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from src.models import RegionConfig, MothershipConfig, InstanceConfig
from src.pve.enums import ZoneStatus
from src.pve.models import PveSessionData
from src.pve.session_manager import PveSessionManager
from src.factory import MechaFactory
from src.core.factory import SnapshotFactory
from src.user.repository import MothershipRepository, UserAssetRepository

class MothershipIntegrationService:
    """提供母舰系统与外部环境 (如 PVE, 背包, 商店) 集成的逻辑层/钩子."""

    @staticmethod
    def validate_region_entry(region: RegionConfig, mothership: MothershipConfig) -> bool:
        """准入校验。

        判断当前母舰是否具备进入指定区域的能力。

        Args:
            region (RegionConfig): 目标区域配置。
            mothership (MothershipConfig): 玩家当前母舰。

        Returns:
            bool: 是否允许进入。
        """
        return mothership.region_level >= region.min_region_level

    @staticmethod
    def get_max_movement_points(mothership: MothershipConfig) -> int:
        """获取最大移动点数。

        基于母舰引擎等级计算每回合可移动的点数。

        Args:
            mothership (MothershipConfig): 玩家当前母舰。

        Returns:
            int: 最大移动点数，公式为 engine_level + 1。
        """
        return mothership.engine_level + 1


    @staticmethod
    def calculate_regeneration(
        last_combat_time: float, 
        current_time: float, 
        mothership: MothershipConfig
    ) -> Tuple[int, int]:
        """战间恢复 (硬性续航支撑)
        
        基于母舰维生配置，按照现实时间戳推算恢复的绝对血量与能量。
        返回 (恢复的HP, 恢复的EN)
        """
        if current_time <= last_combat_time:
            return 0, 0
            
        minutes_elapsed = (current_time - last_combat_time) / 60.0
        
        # 为了避免小数值舍入，可以用积累或简单取整
        hp_regen = int(mothership.hp_regen_per_min * minutes_elapsed)
        en_regen = int(mothership.en_regen_per_min * minutes_elapsed)
        
        return hp_regen, en_regen

    @staticmethod
    def calculate_discard_ratio(mothership: MothershipConfig) -> float:
        """紧急撤退提现 (产出拦截与折损)
        
        主动认怂回城时的应急税率，代表需要抛弃物品的比例（这部分会随机丢弃）。
        0.7 代表没收 70% 临时战利品。
        """
        return mothership.emergency_extraction_tax

    @staticmethod
    def can_fit_in_cargo(
        current_inventory_size: int, 
        incoming_items_count: int, 
        mothership: MothershipConfig
    ) -> bool:
        """容量检查与战利品超载防线
        
        判断战利品拾取或 PVE 结算时，是否超出了母舰的货舱限制。如果为 False 则触发强制结算截断。
        """
        return (current_inventory_size + incoming_items_count) <= mothership.cargo_capacity

    @staticmethod
    def calculate_shop_ilvl_limit(mothership: MothershipConfig) -> int:
        """商店刷新上限
        
        决定商店允许刷出的装备 ilvl 的天花板。
        由于尚未建立完整的挂钩公式，这里提供一个默认基于代际和区域的乘数逻辑。
        """
        return mothership.region_level * 10 + mothership.generation * 5

    @staticmethod
    async def is_pve_session_active(session: "AsyncSession", user_id: int) -> bool:
        """检查用户当前是否处于活跃的 PVE 探索节点中。
        
        按 Doc 11 设定，处于活跃状态则阻断购舰与切换舰队。
        """
        from sqlalchemy import select
        from src.database.models import PveSession
        
        stmt = select(PveSession.id).where(
            PveSession.user_id == user_id, 
            PveSession.status == 'active'
        ).limit(1)
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

class PveEntryService:
    """PVE 进入编排服务。

    该类负责整合工厂、仓库与管理器，完成战斗前的状态锁定与会话初始化。
    """
    
    @staticmethod
    async def _prepare_locked_config(
        db: AsyncSession,
        user_id: int,
        locked_mecha_ids: List[int],
        loader: Any,
        snapshot_factory: SnapshotFactory
    ) -> Dict[str, Any]:
        """构建战前锁定配置。

         Args:
            db (AsyncSession): 数据库异步会话。
            user_id (int): 玩家 ID。
            locked_mecha_ids (List[int]): 选定的机体 ID 列表；为空时取当前出战编队，
                仍无有效编队则回退演示机体（Doc 7 v2.3 §11.2 开发期放宽）。
            loader (Any): 资源加载器。
            snapshot_factory (SnapshotFactory): 快照工厂。

        Returns:
            Dict[str, Any]: 包含所有选定机体快照的配置字典。

        Raises:
            ValueError: 演示机体配置缺失（回退兜底也失败即缺陷级）。
        """
        locked_config = {"mechas": []}

        mecha_ids = list(locked_mecha_ids)
        if not mecha_ids:
            squad = await UserAssetRepository.get_active_squad(db, user_id)
            if squad is not None:
                mecha_ids = list(squad.mecha_ids)

        # 顺序构建机体快照：AsyncSession 绑定单连接，并发查询既无收益也不安全；
        # 编队通常 3-4 台，串行延迟可接受
        for user_mecha_id in mecha_ids:
            try:
                snapshot = await snapshot_factory.create_combat_snapshot(db, user_id, user_mecha_id)
            except Exception:
                continue  # 单台失败跳过，不阻断编队

            locked_config["mechas"].append({
                "user_mecha_id": user_mecha_id,
                "mecha_id": snapshot.instance_id,
                "max_hp": snapshot.final_max_hp,
                "max_en": snapshot.final_max_en,
                "snapshot_dict": snapshot.model_dump()
            })

        if not locked_config["mechas"]:
            # 开发期放宽（Doc 7 v2.3 §11.2）：编队不再是进入战斗的硬门槛——
            # 未锁定机体且无有效出战编队时回退演示机体，保证开发中随时可玩。
            # 必须用配置真实 ID mech_rx78：v2.2 拆除的 "rx78" 假 ID 曾让旧
            # 回退永远 KeyError 落空（那才是地雷，回退本身没问题）。
            try:
                demo_config = loader.get_mecha_config("mech_rx78")
                demo_snapshot = MechaFactory.create_mecha_snapshot(
                    demo_config, weapon_configs=loader.equipments
                )
            except KeyError as e:
                raise ValueError("出战编队无有效机体，且演示机体配置缺失") from e
            locked_config["mechas"].append({
                "mecha_id": demo_snapshot.instance_id,
                "max_hp": demo_snapshot.final_max_hp,
                "max_en": demo_snapshot.final_max_en,
                "snapshot_dict": demo_snapshot.model_dump(),
            })

        return locked_config

    @staticmethod
    async def resolve_current_mothership_config(
        db: AsyncSession, user_id: int, loader: Any
    ) -> MothershipConfig:
        """读玩家当前母舰配置（D13 拆雷：ms_01 假 ID 硬编码的替代，Doc 7 v2.2 §11.8）。

        解析机制单点维护：enter_region 缺省母舰与 engage/extract 的母舰读取
        都走这里。注册流程保证玩家有母舰记录（默认 light_corvette），记录
        缺失属数据缺陷 → ValueError；current_id 引用未知配置让 loader 的
        KeyError 上抛（API 层翻译为 404）。
        """
        db_mothership = await MothershipRepository.get_by_user_id(db, user_id)
        if not db_mothership:
            raise ValueError("未找到玩家母舰记录")
        return loader.get_mothership_config(db_mothership.data.get("current_id"))

    @classmethod
    async def enter_region(
        cls,
        db: AsyncSession,
        user_id: int,
        region_id: str,
        zone_id: str,
        mothership_id: Optional[str],
        locked_mecha_ids: Optional[List[int]],
        loader: Any,
        idempotency_key: Optional[str] = None
    ) -> PveSessionData:
        """进入 PVE 副本的完整编排流程。"""
        if mothership_id is None:
            # 缺省读玩家当前母舰（Doc 7 v2.2 §11.8：ms_01 假 ID 硬编码拆除）
            mothership_config = await cls.resolve_current_mothership_config(db, user_id, loader)
        else:
            mothership_config = loader.get_mothership_config(mothership_id)
        region_config = loader.get_region_config(region_id)
        
        # 0. 准入与进度校验
        if not MothershipIntegrationService.validate_region_entry(region_config, mothership_config):
            raise ValueError(f"Mothership region_level too low for {region_id}")
            
        from src.pve.progress_service import PveProgressService
        region_status = await PveProgressService.get_region_status(db, user_id, region_id, loader)
        zone_status = region_status.get(zone_id)
        if zone_status not in (ZoneStatus.UNLOCKED.value, ZoneStatus.CLEARED.value, ZoneStatus.AVAILABLE.value):
            raise ValueError(f"Zone {zone_id} is not accessible. Current status: {zone_status}")

        # 1. 初始化工厂
        snapshot_factory = SnapshotFactory(loader, UserAssetRepository())
        
        # 2. 准备锁定状态
        locked_config = await cls._prepare_locked_config(
            db, user_id, locked_mecha_ids or [], loader, snapshot_factory
        )
        
        # 3. 创建会话
        session_data = PveSessionManager.create_session(
            user_id=user_id,
            region_id=region_id,
            zone_id=zone_id,
            mothership_config=mothership_config,
            locked_config=locked_config,
            loader=loader
        )

        return session_data
