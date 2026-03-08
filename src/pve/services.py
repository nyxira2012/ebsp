from typing import Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from src.models import RegionConfig, MothershipConfig

class MothershipIntegrationService:
    """提供母舰系统与外部环境 (如 PVE, 背包, 商店) 集成的逻辑层/钩子."""

    @staticmethod
    def validate_region_entry(region: RegionConfig, mothership: MothershipConfig) -> bool:
        """准入校验 (宏观探索门槛)
        
        判断当前母舰是否具备进入指定区域的能力。
        """
        return mothership.region_level >= region.min_region_level

    @staticmethod
    def get_max_movement_points(mothership: MothershipConfig) -> int:
        """寻路与机动力 (微观寿命优化)
        
        基于母舰引擎等级，推演出微观点阵地图的最大合法跨越距离。
        - 引擎 Lv 1: 基础 1-2 格跨越 (简化为只返回 2 作为最大值，或后续配合系统演进)
        - 此处暂定公式：engine_level + 1 
          (如 Lv 1 -> 2, Lv 2 -> 3, Lv 3 -> 4 格)
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
        # TODO: 待 PveSession 逻辑完全落地。此处应查询 pve_sessions 表中状态为 'ACTIVE' 的记录。
        # 伪代码：
        # stmt = select(PveSession).where(user_id=user_id, status='ACTIVE')
        # result = await session.execute(stmt)
        # return result.scalar_one_or_none() is not None
        
        # 临时硬编码：默认不锁定
        return False
