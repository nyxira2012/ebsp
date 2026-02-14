import json
from pathlib import Path
from typing import List, Dict, Any
from ..models import Effect

class EffectFactory:
    """数据驱动的效果工厂"""
    
    _skill_data: Dict[str, List[Dict[str, Any]]] = {}
    _data_loaded: bool = False

    @classmethod
    def _load_data(cls):
        """加载技能数据文件 (data/skills.json)。

        如果数据已加载则跳过。如果文件不存在或加载失败，会输出警告或错误信息。
        """
        if cls._data_loaded:
            return

        # 尝试多个可能的路径
        possible_paths = [
            Path("data/skills.json"),
            Path("../data/skills.json"),
            Path("skills.json"),
        ]

        skill_file = None
        for path in possible_paths:
            if path.exists():
                skill_file = path
                break

        if not skill_file:
            print(f"⚠️  警告: 找不到技能数据文件，尝试了以下路径:")
            for path in possible_paths:
                print(f"  - {path.absolute()}")
            return
            
        try:
            with open(skill_file, 'r', encoding='utf-8') as f:
                cls._skill_data = json.load(f)
            cls._data_loaded = True
            print(f"✓ 已加载 {len(cls._skill_data)} 个技能定义 (从 {skill_file})")
        except Exception as e:
            print(f"❌ 加载技能数据失败: {e}")

    @classmethod
    def create_effect(cls, effect_id: str, duration: int = 1) -> List[Effect]:
        """根据效果 ID 从 JSON 配置中创建标准效果对象列表。

        如果 ID 存在于配置中，会遍历其包含的所有子效果定义并实例化为 Effect 对象。
        支持从 JSON 中覆盖 duration、charges、priority 等默认数值。

        Args:
            effect_id: 技能或精神指令的唯一标识符
            duration: 默认持续回合数，若 JSON 中未指定则使用此值

        Returns:
            List[Effect]: 生成的效果对象列表，若 ID 不存在则返回空列表
        """
        cls._load_data()
        
        effects: List[Effect] = []
        
        if effect_id in cls._skill_data:
            for item in cls._skill_data[effect_id]:
                # 复制并应用 duration (如果 JSON 里没写永久的话)
                # 注意: 如果 JSON 里 duration 是 -1，表示永久特性，不需要覆盖
                item_duration = item.get("duration", duration)
                
                eff = Effect(
                    id=item["id"],
                    name=item["name"],
                    hook=item["hook"],
                    operation=item["operation"],
                    value=item["value"],
                    priority=item.get("priority", 50),
                    sub_priority=item.get("sub_priority", 500),
                    duration=item_duration,
                    charges=item.get("charges", -1),
                    conditions=item.get("conditions", []),
                    side_effects=item.get("side_effects", [])
                )
                effects.append(eff)
        else:
            # 未定义的效果ID返回空列表
            return []

        return effects

    @classmethod
    def create_trait_effects(cls, trait_id: str) -> List[Effect]:
        """根据特性 ID 创建永久性的效果对象列表。

        Args:
            trait_id: 机体或驾驶员特性的唯一标识符

        Returns:
            List[Effect]: 生成的永久效果列表
        """
        # 特性的 duration 通常在 JSON 中定义为 -1
        return cls.create_effect(trait_id, duration=-1)

