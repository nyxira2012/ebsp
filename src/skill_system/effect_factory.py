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
        """加载技能 JSON 数据"""
        if cls._data_loaded:
            return
            
        skill_file = Path("data/skills.json")
        if not skill_file.exists():
            print(f"⚠️  警告: 找不到技能数据文件 {skill_file}")
            return
            
        try:
            with open(skill_file, 'r', encoding='utf-8') as f:
                cls._skill_data = json.load(f)
            cls._data_loaded = True
            # print(f"✓ 已加载 {len(cls._skill_data)} 个技能定义")
        except Exception as e:
            print(f"❌ 加载技能数据失败: {e}")

    @classmethod
    def create_effect(cls, effect_id: str, duration: int = 1) -> List[Effect]:
        """根据 ID 从 JSON 数据中创建 Effect 对象"""
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
        """创建特性的永久效果 (复用 create_effect 逻辑)"""
        # 特性的 duration 通常在 JSON 中定义为 -1
        return cls.create_effect(trait_id, duration=-1)

