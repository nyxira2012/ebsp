import math
from ..config import Config


class CombatCalculator:
    """战斗计算核心"""
    
    @staticmethod
    def calculate_proficiency_miss_penalty(proficiency: int) -> float:
        """
        计算武器熟练度导致的未命中惩罚
        公式: 当前未命中率 = 12% + (18% * (1 - (Min(次数, 1000)/1000)^1.5))
        
        Args:
            proficiency: 武器熟练度 (0-1000+)
            
        Returns:
            实际未命中率 (%)
        """
        clamped: int = min(proficiency, Config.WEAPON_PROFICIENCY_THRESHOLD)
        ratio: float = (clamped / Config.WEAPON_PROFICIENCY_THRESHOLD) ** Config.WEAPON_PROFICIENCY_EXPONENT
        penalty: float = Config.WEAPON_PROFICIENCY_PENALTY_MAX * (1 - ratio)
        return Config.BASE_MISS_RATE + penalty
    
    @staticmethod
    def calculate_proficiency_defense_ratio(proficiency: int, base_rate: float) -> float:
        """
        计算机体熟练度对躲闪/招架的影响
        公式: 当前比率 = 基础比率 * (log(Min(次数, 4000) + 1) / log(4000 + 1))
        
        Args:
            proficiency: 机体熟练度 (0-4000+)
            base_rate: 基础比率 (%)
            
        Returns:
            实际比率 (%)
        """
        clamped: int = min(proficiency, Config.MECHA_PROFICIENCY_THRESHOLD)
        ratio: float = math.log(clamped + 1) / math.log(Config.MECHA_PROFICIENCY_THRESHOLD + 1)
        return base_rate * ratio
    
    @staticmethod
    def calculate_will_damage_modifier(will: int) -> float:
        """
        气力对伤害的修正
        公式: 伤害修正系数 = 气力 / 100
        
        Args:
            will: 当前气力值
            
        Returns:
            伤害修正系数
        """
        return will / Config.WILL_MODIFIER_BASE
    
    @staticmethod
    def calculate_will_defense_modifier(will: int) -> float:
        """
        气力对防御的修正
        公式: 有效装甲值 = 基础装甲 * (气力 / 100)
        
        Args:
            will: 当前气力值
            
        Returns:
            防御修正系数
        """
        return will / Config.WILL_MODIFIER_BASE
    
    @staticmethod
    def calculate_will_stability_bonus(will: int) -> float:
        """
        气力对命中/躲闪的微调
        公式: 命中/躲闪附加率 = (气力 - 100) * 0.002
        
        Args:
            will: 当前气力值
            
        Returns:
            稳定性加成 (小数比例)
        """
        return (will - Config.WILL_MODIFIER_BASE) * Config.WILL_STABILITY_COEFFICIENT
    
    @staticmethod
    def calculate_armor_mitigation(armor: int, will_modifier: float) -> float:
        """
        护甲减伤计算 (非线性)
        公式: 减伤% = (护甲 * 气力修正) / (护甲 * 气力修正 + K)
        
        Args:
            armor: 基础护甲值
            will_modifier: 气力修正系数
            
        Returns:
            减伤比例 (0.0-1.0)
        """
        effective_armor: float = armor * will_modifier
        return effective_armor / (effective_armor + Config.ARMOR_K)
    
    @staticmethod
    def calculate_precision_reduction(precision: float) -> float:
        """
        精准削减防御概率的比例
        公式: 削减比 = precision / 100
        最大削减上限: 80%
        
        Args:
            precision: 精准值
            
        Returns:
            削减比例 (0.0-0.8)
        """
        return min(precision / 100.0, Config.PRECISION_REDUCTION_CAP)
