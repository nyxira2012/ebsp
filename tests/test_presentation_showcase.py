"""演出系统演示脚本 - 展示不同场景下的演出效果（修复版）"""

import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "."))

from src.presentation import EventMapper, TextRenderer, TemplateRegistry
from src.presentation.models import RawAttackEvent

def showcase_presentation():
    """展示演出系统的不同场景"""
    print("=" * 80)
    print("演出系统效果展示")
    print("=" * 80)
    print()

    # 创建 TemplateRegistry 并加载配置
    registry = TemplateRegistry()
    config_path = os.path.join("config", "presentation_templates.yaml")
    registry.load_from_config(config_path)

    # 创建 EventMapper，传入配置好的 registry
    mapper = EventMapper(registry=registry)
    renderer = TextRenderer()

    # 场景 1: 光束武器射击
    print("【场景 1: 远距离光束射击 - 命中】")
    raw1 = RawAttackEvent(
        round_number=1,
        attacker_id="mech_a",
        defender_id="mech_b",
        attacker_name="RX-78-2 高达",
        defender_name="扎古II",
        weapon_id="beam_rifle",
        weapon_name="光束步枪",
        weapon_type="SHOOTING",
        weapon_tags=["beam"],
        attack_result="HIT",
        damage=2800,
        distance=1500,
        attacker_will_delta=5,
        defender_will_delta=2,
        triggered_skills=[],
        is_first_attack=True,
        initiative_holder="mech_a"
    )
    events1 = mapper.map_attack(raw1)
    print(renderer.render_attack(events1))
    print()

    # 场景 2: 近战斩击 - 暴击
    print("【场景 2: 近战斩击 - 暴击】")
    raw2 = RawAttackEvent(
        round_number=1,
        attacker_id="mech_a",
        defender_id="mech_b",
        attacker_name="高达",
        defender_name="大魔",
        weapon_id="beam_saber",
        weapon_name="光束军刀",
        weapon_type="MELEE",
        weapon_tags=["beam", "slash_light"],
        attack_result="CRIT",
        damage=4500,
        distance=50,
        attacker_will_delta=8,
        defender_will_delta=0,
        triggered_skills=[],
        is_first_attack=True,
        initiative_holder="mech_a"
    )
    events2 = mapper.map_attack(raw2)
    print(renderer.render_attack(events2))
    print()

    # 场景 3: 近战重击 - 格挡
    print("【场景 3: 热能斧重击 - 格挡】")
    raw3 = RawAttackEvent(
        round_number=2,
        attacker_id="mech_b",
        defender_id="mech_a",
        attacker_name="大魔",
        defender_name="高达",
        weapon_id="heat_axe",
        weapon_name="热能斧",
        weapon_type="MELEE",
        weapon_tags=["heavy", "slash_heavy"],
        attack_result="BLOCK",
        damage=800,
        distance=80,
        attacker_will_delta=3,
        defender_will_delta=1,
        triggered_skills=[],
        is_first_attack=True,
        initiative_holder="mech_b"
    )
    events3 = mapper.map_attack(raw3)
    print(renderer.render_attack(events3))
    print()

    # 场景 4: 远程狙击 - 闪避
    print("【场景 4: 狙击 - 闪避】")
    raw4 = RawAttackEvent(
        round_number=3,
        attacker_id="mech_a",
        defender_id="mech_b",
        attacker_name="狙击型高达",
        defender_name="渣古",
        weapon_id="sniper_rifle",
        weapon_name="狙击步枪",
        weapon_type="SHOOTING",
        weapon_tags=["beam", "long_range"],
        attack_result="DODGE",
        damage=0,
        distance=5000,
        attacker_will_delta=2,
        defender_will_delta=5,
        triggered_skills=[],
        is_first_attack=True,
        initiative_holder="mech_a"
    )
    events4 = mapper.map_attack(raw4)
    print(renderer.render_attack(events4))
    print()

    # 场景 5: 火箭炮轰炸 - 招架
    print("【场景 5: 火箭炮 - 招架】")
    raw5 = RawAttackEvent(
        round_number=4,
        attacker_id="mech_b",
        defender_id="mech_a",
        attacker_name="老虎",
        defender_name="高达",
        weapon_id="rocket_launcher",
        weapon_name="重型火箭炮",
        weapon_type="HEAVY",
        weapon_tags=["explosive", "impact_massive"],
        attack_result="PARRY",
        damage=1200,
        distance=800,
        attacker_will_delta=4,
        defender_will_delta=3,
        triggered_skills=[],
        is_first_attack=True,
        initiative_holder="mech_b"
    )
    events5 = mapper.map_attack(raw5)
    print(renderer.render_attack(events5))
    print()

    # 场景 6: 近战攻击 - 未命中
    print("【场景 6: 近战攻击 - 未命中】")
    raw6 = RawAttackEvent(
        round_number=5,
        attacker_id="mech_a",
        defender_id="mech_b",
        attacker_name="高达",
        defender_name="大魔",
        weapon_id="vibro_blade",
        weapon_name="振动刀",
        weapon_type="MELEE",
        weapon_tags=["slash_light"],
        attack_result="MISS",
        damage=0,
        distance=100,
        attacker_will_delta=1,
        defender_will_delta=2,
        triggered_skills=[],
        is_first_attack=True,
        initiative_holder="mech_a"
    )
    events6 = mapper.map_attack(raw6)
    print(renderer.render_attack(events6))
    print()

    print("=" * 80)
    print("演出模板级别统计")
    print("=" * 80)

    all_events = events1 + events2 + events3 + events4 + events5 + events6
    tier_count = {}
    for evt in all_events:
        tier = evt.tier.value
        tier_count[tier] = tier_count.get(tier, 0) + 1

    print(f"T0 (脚本化): {tier_count.get('T0_SCRIPTED', 0)} 个")
    print(f"T1 (剧情): {tier_count.get('T1_HIGHLIGHT', 0)} 个")
    print(f"T2 (战术): {tier_count.get('T2_TACTICAL', 0)} 个")
    print(f"T3 (兜底): {tier_count.get('T3_FALLBACK', 0)} 个")

    print()
    print("演出系统演示完成")

if __name__ == "__main__":
    showcase_presentation()
