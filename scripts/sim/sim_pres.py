"""
MDDC 文字演出综合模拟测试 v7.0
=================================
按武器类型组织，每种武器测试全部6种判定：
- MISS, DODGE, PARRY, BLOCK, HIT, CRIT
"""

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.presentation import RawAttackEvent
from src.presentation.constants import MotionStyle, DamageMaterial
from src.presentation.loader import TemplateLoader


# =====================================================
# 武器类型定义（按动作风格+材质组合）
# =====================================================
WEAPON_TYPES = [
    {
        "id": "beam_rifle",
        "name": "光束步枪",
        "motion_style": MotionStyle.SHOOT_INSTANT,
        "damage_material": DamageMaterial.ENERGY,
        "attacker": "高达",
        "defender": "扎古II",
    },
    {
        "id": "kinetic_rifle",
        "name": "90mm机枪",
        "motion_style": MotionStyle.SHOOT_INSTANT,
        "damage_material": DamageMaterial.KINETIC,
        "attacker": "陆战型吉姆",
        "defender": "大魔",
    },
    {
        "id": "beam_saber",
        "name": "光束军刀",
        "motion_style": MotionStyle.SLASH_LIGHT,
        "damage_material": DamageMaterial.ENERGY,
        "attacker": "高达",
        "defender": "老虎",
    },
    {
        "id": "heat_axe",
        "name": "热能斧",
        "motion_style": MotionStyle.SLASH_HEAVY,
        "damage_material": DamageMaterial.PHYSICAL,
        "attacker": "夏亚扎古",
        "defender": "钢坦克",
    },
    {
        "id": "bazooka",
        "name": "火箭炮",
        "motion_style": MotionStyle.PROJ_SINGLE,
        "damage_material": DamageMaterial.KINETIC,
        "attacker": "全装甲高达",
        "defender": "勇士",
    },
    {
        "id": "beam_cannon",
        "name": "扩散粒子炮",
        "motion_style": MotionStyle.SHOOT_MASSIVE,
        "damage_material": DamageMaterial.ENERGY,
        "attacker": "精神力高达",
        "defender": "百式",
    },
    {
        "id": "missile_launcher",
        "name": "导弹发射器",
        "motion_style": MotionStyle.PROJ_RAIN,
        "damage_material": DamageMaterial.KINETIC,
        "attacker": "全装甲高达",
        "defender": "大魔",
    },
    {
        "id": "impact_ram",
        "name": "冲撞攻击",
        "motion_style": MotionStyle.IMPACT_RAM,
        "damage_material": DamageMaterial.GENERIC,
        "attacker": "大魔",
        "defender": "钢加农",
    },
    {
        "id": "blunt_strike",
        "name": "铁锤重击",
        "motion_style": MotionStyle.STRIKE_BLUNT,
        "damage_material": DamageMaterial.GENERIC,
        "attacker": "勇士",
        "defender": "高达",
    },
    {
        "id": "funnel",
        "name": "浮游炮",
        "motion_style": MotionStyle.PSYCHO_WAVE,
        "damage_material": DamageMaterial.ENERGY,
        "attacker": "精神力高达",
        "defender": "Z高达",
    },
]


# =====================================================
# 六种判定定义
# =====================================================
ATTACK_RESULTS = [
    ("MISS", 0, False, "未命中"),
    ("DODGE", 0, False, "闪避"),
    ("PARRY", 0, False, "招架"),
    ("BLOCK", 500, False, "格挡"),
    ("HIT", 2000, False, "命中"),
    ("CRIT", 3500, False, "暴击"),
]


def create_event(weapon: dict, attack_result: str, damage: int, is_lethal: bool) -> RawAttackEvent:
    """创建攻击事件（模拟程序只负责场景数据，HP由演出系统处理）"""
    return RawAttackEvent(
        round_number=1,
        attacker_id="att_01",
        defender_id="def_01",
        attacker_name=weapon["attacker"],
        defender_name=weapon["defender"],
        weapon_id=weapon["id"],
        weapon_name=weapon["name"],
        weapon_type="TEST",
        weapon_tags=[],
        attack_result=attack_result,
        damage=damage,
        distance=1000,
        attacker_will_delta=0,
        defender_will_delta=0,
        triggered_skills=[],
        is_first_attack=True,
        initiative_holder="attacker",
        motion_style=weapon["motion_style"].value,
        damage_material=weapon["damage_material"].value,
        is_lethal=is_lethal,
    )


def run_simulation():
    """运行完整武器类型 × 判定结果矩阵测试"""
    print("=" * 100)
    print("MDDC 文字演出综合模拟测试 v7.0 [Weapon × Result Matrix]")
    print("=" * 100)

    # 初始化演出系统 (v5.0 唯一入口: EventMapper)
    from src.presentation import EventMapper, TemplateRegistry
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "config", "presentation_templates.yaml"
    )
    registry = TemplateRegistry()
    registry.load_from_config(config_path)
    mapper = EventMapper(registry)

    total_cases = 0

    
    # 遍历所有武器类型
    for weapon in WEAPON_TYPES:
        print(f"\n{'=' * 100}")
        print(f"【{weapon['name']}】 | 动作: {weapon['motion_style'].value} | 材质: {weapon['damage_material'].value}")
        print('=' * 100)

        # 遍历所有判定结果
        for result_code, damage, is_lethal, result_name in ATTACK_RESULTS:
            total_cases += 1

            # 创建事件
            event = create_event(weapon, result_code, damage, is_lethal)
            
            # 使用 EventMapper 作为黑盒 (L1-L4 完整流水线)
            presentation_events = mapper.map_attack(event)
            
            # 提取结果 (Action 在前，Reaction 在后)
            action_event = presentation_events[0]
            reaction_event = presentation_events[1]

            # 输出测试结果
            print(f"\n  [{result_code}] - {result_name}")
            print(f"    进攻: {action_event.text}")
            print(f"    受击: {reaction_event.text}")
            print(f"    Tier: {action_event.tier.name} / {reaction_event.tier.name}")

    print(f"\n完成 {total_cases} 个测试用例")


if __name__ == "__main__":
    run_simulation()
