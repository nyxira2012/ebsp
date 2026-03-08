import random
from typing import Dict, List, Optional, Tuple, Any
from src.loader import DataLoader
from src.models import EquipmentConfig, AffixConfig

class EquipmentGenerator:
    """物品生成器 - 负责创造具有随机潜力的装备 (Doc 8)"""
    
    # 属性词条档位字典: { 档位: (概率权重, T值) }
    TIER_WEIGHTS = {
        0: 39.0, # T0 (空)
        1: 35.0, # T1 (低档)
        2: 18.0, # T2 (中档)
        3: 7.0,  # T3 (高档)
        4: 1.0   # T4 (顶级)
    }
    
    SKILL_CHANCE = 0.005 # 技能槽 0.5% 概率
    
    def __init__(self, loader: DataLoader):
        self.loader = loader

    def _roll_ilvl(self, base_ilvl: int) -> int:
        """根据基础 ilvl 计算 ±5% 的浮动 (向下取整)"""
        variance = max(1, int(base_ilvl * 0.05))
        return max(1, random.randint(base_ilvl - variance, base_ilvl + variance))
    
    def _roll_tier(self) -> int:
        """根据权重抽取档位 T0-T4"""
        tiers = list(self.TIER_WEIGHTS.keys())
        weights = list(self.TIER_WEIGHTS.values())
        return random.choices(tiers, weights=weights, k=1)[0]
        
    def _filter_affixes(self, affix_type: str, current_ilvl: int, equip_type: str, exclude_ids: set) -> List[AffixConfig]:
        """筛选符合条件的词条"""
        valid_affixes = []
        for affix in self.loader.affixes.values():
            if affix.type != affix_type:
                continue
            if affix.min_ilvl > current_ilvl:
                continue
            if equip_type not in affix.slot_tags:
                continue
            if affix.id in exclude_ids:
                continue
            valid_affixes.append(affix)
        return valid_affixes

    def _roll_stat_affix(self, current_ilvl: int, equip_type: str, exclude_ids: set) -> Optional[AffixConfig]:
        """按权重抽取一条属性"""
        valid_affixes = self._filter_affixes("stat", current_ilvl, equip_type, exclude_ids)
        if not valid_affixes:
            return None
        weights = [a.weight for a in valid_affixes]
        return random.choices(valid_affixes, weights=weights, k=1)[0]

    def _roll_skill_affix(self, current_ilvl: int, equip_type: str) -> Optional[AffixConfig]:
        """按权重抽取一个技能"""
        valid_affixes = self._filter_affixes("skill", current_ilvl, equip_type, set())
        if not valid_affixes:
            return None
        weights = [a.weight for a in valid_affixes]
        return random.choices(valid_affixes, weights=weights, k=1)[0]

    def generate_equipment(self, equipment_id: str, base_ilvl: int) -> Dict[str, Any]:
        """
        生成一件指定模板的装备及其随机属性
        返回的数据结构能够直接被转成 EquipmentRandomStats 并存入 DB
        """
        equip_config = self.loader.get_equipment_config(equipment_id)
        current_ilvl = self._roll_ilvl(base_ilvl)
        
        affixes_picked = []
        picked_affix_ids = set()
        
        # Roll 3 个属性槽
        for _ in range(3):
            tier = self._roll_tier()
            if tier > 0:
                picked_affix = self._roll_stat_affix(current_ilvl, equip_config.type, set()) # 不限制词条去重组合
                if picked_affix:
                    affixes_picked.append({"id": picked_affix.id, "t": tier})
                    
        # Roll 技能槽
        skill_id = None
        if random.random() < self.SKILL_CHANCE:
            picked_skill = self._roll_skill_affix(current_ilvl, equip_config.type)
            if picked_skill:
                skill_id = picked_skill.skill_id
                
        # 计算颜色/稀有度 (Doc 8 纯展示用，前端可以实时计算，这里为了方便也可以算出)
        # color_score = len(affixes_picked) + (2 if skill_id else 0)
        
        return {
            "ilvl": current_ilvl,
            "affixes": affixes_picked,
            "skill": skill_id
        }
