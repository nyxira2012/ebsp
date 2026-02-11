
"""
快照工厂 (Snapshot Factory)
负责将静态配置 (Config) 聚合为运行时快照 (Snapshot)。
核心逻辑参考 doc/4.stat_equip_design.md
"""

from typing import List, Dict, Optional, Tuple
from .models import (
    MechaConfig, PilotConfig, EquipmentConfig,
    MechaSnapshot, WeaponSnapshot, WeaponType, SlotType
)
from .config import Config

class SnapshotFactory:
    """快照生成工厂"""
    
    @staticmethod
    def create_mecha_snapshot(
        mecha_conf: MechaConfig,
        pilot_conf: PilotConfig,
        equipments: List[EquipmentConfig] = [],
        sub_pilots: List[PilotConfig] = [], # 副驾驶视为虚拟装备
        upgrade_level: int = 0, # 机体改造等级
        will: int = 100
    ) -> MechaSnapshot:
        """
        生成机体运行时快照
        
        计算流程:
        1. 基础属性 (Level 0) + 改造加成
        2. 装备修正 (累加 Stat Modifiers)
        3. 副驾驶修正 (累加 Stat Modifiers)
        4. 驾驶员修正 (五维影响) -> 这个是在 Combat Resolver 中动态计算，还是在这里预计算？
           根据设计文档，Hit/Crit/Dodge等概率由"硬件(机体+装备)"决定，
           然后 Pilot Stats 作为 Attack/Defense Power 的修正，或最终概率的修正。
           MechaSnapshot 存储的是 "硬件性能" + "驾驶员能力备份"。
           
        5. 生成 WeaponSnapshot 列表 (合并固定武器和装备武器)
        """
        
        # 1. 基础属性处理
        # 改造加成 (示例：简单的线性加成，实际可能查表)
        hp_up = upgrade_level * 200
        en_up = upgrade_level * 5
        armor_up = upgrade_level * 20
        mobility_up = upgrade_level * 2
        hit_up = upgrade_level * 1
        
        base_hp = mecha_conf.init_hp + hp_up
        base_en = mecha_conf.init_en + en_up
        base_armor = mecha_conf.init_armor + armor_up
        base_mobility = mecha_conf.init_mobility + mobility_up
        
        base_hit = mecha_conf.init_hit + hit_up
        base_prec = mecha_conf.init_precision
        base_crit = mecha_conf.init_crit
        
        base_dodge = mecha_conf.init_dodge
        base_parry = mecha_conf.init_parry
        base_block = mecha_conf.init_block
        base_block_red = mecha_conf.init_block_red
        
        # 2. 装备与副驾驶修正聚合
        # 副驾驶转换为虚拟装备 (TODO: 需要定义转换逻辑，这里简化为无属性修正或特定逻辑)
        # 假设 EquipmentConfig 和 PilotConfig 结构不同，需要分别处理
        
        modifiers: Dict[str, float] = {}
        
        def add_mod(key: str, value: float):
            modifiers[key] = modifiers.get(key, 0.0) + value
            
        # 遍历装备
        for eq in equipments:
            for stat, val in eq.stat_modifiers.items():
                add_mod(stat, val)
                
        # 遍历副驾驶 (根据设计，副驾驶提供精神指令和被动技能，也能提供属性修正?)
        # 假设副驾驶的 stat_modifiers 存在于某个字段，或者硬编码转换
        # 这里暂时忽略副驾驶的直接属性修正，除非 doc 有明确映射
        
        # 3. 应用修正
        final_hp = int(base_hp + modifiers.get("max_hp", 0))
        final_en = int(base_en + modifiers.get("max_en", 0))
        final_armor = int(base_armor + modifiers.get("armor", 0))
        final_mobility = int(base_mobility + modifiers.get("mobility", 0))
        
        final_hit = base_hit + modifiers.get("hit_rate", 0)
        final_prec = base_prec + modifiers.get("precision", 0)
        final_crit = base_crit + modifiers.get("crit_rate", 0)
        
        final_dodge = base_dodge + modifiers.get("dodge_rate", 0)
        final_parry = base_parry + modifiers.get("parry_rate", 0)
        final_block = base_block + modifiers.get("block_rate", 0)
        
        # 4. 武器快照生成
        weapon_snapshots: List[WeaponSnapshot] = []
        
        # 处理内置武器 (需要从 id 查找 Config，这里假设有 loader，暂且跳过查找，
        # 实际应传入 WeaponConfigs 列表或由 caller 准备好)
        # 为了演示，我们假设 caller 已经解析好了武器配置，或者我们需要一个 weapon_lookup
        # 这里先只处理 equipments 中的武器
        
        # 处理装备提供的武器
        for eq in equipments:
            if eq.type == "WEAPON" and eq.weapon_type:
                w_type = eq.weapon_type
                if isinstance(w_type, str): # Handle potential string vs Enum
                    try:
                        w_type = WeaponType(w_type)
                    except ValueError:
                        w_type = WeaponType.SHOOTING # Fallback
                
                ws = WeaponSnapshot(
                    uid=f"{eq.id}_{id(eq)}", # 临时唯一ID
                    definition_id=eq.id,
                    name=eq.name,
                    type=w_type,
                    final_power=eq.weapon_power or 1000,
                    range_min=eq.weapon_range_min or 1,
                    range_max=eq.weapon_range_max or 1,
                    en_cost=eq.weapon_en_cost or 0,
                    will_req=eq.weapon_will_req,
                    anim_id=eq.weapon_anim_id,
                    hit_mod=0.0, # 初始修正
                    crit_mod=0.0,
                    tags=eq.weapon_tags
                )
                weapon_snapshots.append(ws)

        # 5. 组装 Pilot Backup
        pilot_backup = {
            "stat_shooting": pilot_conf.stat_shooting,
            "stat_melee": pilot_conf.stat_melee,
            "stat_awakening": pilot_conf.stat_awakening,
            "stat_defense": pilot_conf.stat_defense,
            "stat_reaction": pilot_conf.stat_reaction,
        }
        
        return MechaSnapshot(
            instance_id=f"{mecha_conf.id}_inst_{pilot_conf.id}",
            mecha_name=mecha_conf.name,
            main_portrait=pilot_conf.portrait_id,
            sub_portrait=sub_pilots[0].portrait_id if sub_pilots else None,
            model_asset=mecha_conf.model_asset,
            
            final_max_hp=final_hp,
            current_hp=final_hp,
            final_max_en=final_en,
            current_en=final_en,
            
            final_armor=final_armor,
            final_mobility=final_mobility,
            
            final_hit=final_hit,
            final_precision=final_prec,
            final_crit=final_crit,
            
            final_dodge=final_dodge,
            final_parry=final_parry,
            final_block=final_block,
            block_reduction=base_block_red, # 暂无修正
            
            weapons=weapon_snapshots,
            skills=pilot_conf.innate_skills + [s for eq in equipments for s in eq.passive_skills],
            pilot_stats_backup=pilot_backup,
            current_will=will
        )
