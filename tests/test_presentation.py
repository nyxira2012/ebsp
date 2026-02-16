"""
演出系统测试套件
验证演出系统的基本功能、集成场景和全面测试
"""

import sys
import os
from pathlib import Path

# 获取项目根目录
project_root = Path(__file__).parent.parent

from src.presentation import EventMapper, TextRenderer, RawAttackEvent, TemplateRegistry
from src.presentation.models import PresentationAttackEvent
from src.presentation.constants import TemplateTier
from src.models import WeaponType


def create_event(round_num, att_name, def_name, weapon, w_type, result, dmg, skills=None, is_first=False):
    """创建测试事件的辅助函数"""
    return RawAttackEvent(
        round_number=round_num,
        attacker_id="att_01",
        defender_id="def_01",
        attacker_name=att_name,
        defender_name=def_name,
        weapon_id=f"wp_{weapon}",
        weapon_name=weapon,
        weapon_type=w_type,
        weapon_tags=[],
        attack_result=result,
        damage=dmg,
        distance=5,
        attacker_will_delta=0,
        defender_will_delta=0,
        triggered_skills=skills or [],
        is_first_attack=is_first,
        initiative_holder="attacker"
    )


def test_mapper():
    """测试事件转换器"""
    print("=" * 80)
    print("测试事件转换器 (EventMapper)")
    print("=" * 80)
    print()

    # 加载配置
    config_path = os.path.join(project_root, "config", "presentation_templates.yaml")
    registry = TemplateRegistry(config_path)
    mapper = EventMapper(registry)

    # 创建测试用的原始攻击事件
    raw_event = RawAttackEvent(
        round_number=1,
        attacker_id="mecha_001",
        defender_id="mecha_002",
        attacker_name="RX-78-2 高达",
        defender_name="MS-06S 扎古指挥官型",
        weapon_id="weapon_beam_saber",
        weapon_name="光束军刀",
        weapon_type=WeaponType.MELEE,
        weapon_tags=[],
        attack_result="HIT",
        damage=1200,
        distance=800,
        attacker_will_delta=2,
        defender_will_delta=0,
        triggered_skills=[],
        is_first_attack=True,
        initiative_holder="mecha_001"
    )

    # 转换为演出事件
    pres_events = mapper.map_attack(raw_event)

    # 打印结果
    print("原始事件:")
    print(f"  攻击方: {raw_event.attacker_name}")
    print(f"  防御方: {raw_event.defender_name}")
    print(f"  武器: {raw_event.weapon_name}")
    print(f"  结果: {raw_event.attack_result}")
    print(f"  伤害: {raw_event.damage}")
    print()

    print("演出事件:")
    for i, pres_event in enumerate(pres_events):
        print(f"  事件 {i+1}:")
        print(f"    类型: {pres_event.event_type}")
        print(f"    文本: {pres_event.text}")
        print(f"    Tier: {pres_event.tier.value}")
        print(f"    动画ID: {pres_event.anim_id}")
        print(f"    特效ID: {pres_event.vfx_ids}")
        print(f"    命中部位: {pres_event.hit_location}")
    print()


def test_text_renderer():
    """测试文本渲染器"""
    print("=" * 80)
    print("测试文本渲染器 (TextRenderer)")
    print("=" * 80)
    print()

    # 创建渲染器
    renderer = TextRenderer()

    # 创建测试事件
    test_event = PresentationAttackEvent(
        event_type="ACTION",
        round_number=1,
        text="高达的光束军刀从腰部挂架中抽出的刹那，机体已化作白色闪光！刀刃精准刺向扎古的左侧肩甲。（命中！伤害 1200）",
        display_tags=["命中"],
        anim_id="anim_saber_slash_01",
        damage_display=1200,
        hit_location="左侧肩甲",
        attacker_name="高达",
        defender_name="扎古",
        weapon_name="光束军刀",
        attack_result="HIT",
        tier=TemplateTier.T3_FALLBACK
    )

    # 渲染文本
    rendered_text = renderer.render_attack([test_event])
    print("渲染结果:")
    print(rendered_text)
    print()


def test_integration_scenarios():
    """测试集成场景"""
    print("=" * 80)
    print("集成场景测试")
    print("=" * 80)
    print()

    # 加载配置
    config_path = os.path.join(project_root, "config", "presentation_templates.yaml")
    registry = TemplateRegistry(config_path)
    mapper = EventMapper(registry)
    renderer = TextRenderer()

    print(f"✓ 已加载 {len(registry._templates)} 个演出模板")
    print()

    # 测试场景1：T1 精彩闪避
    print("场景1: T1 精彩闪避")
    print("-" * 80)
    event1 = RawAttackEvent(
        round_number=1,
        attacker_id="zaku_01",
        defender_id="gundam_01",
        attacker_name="扎古指挥官型",
        defender_name="高达",
        weapon_id="wp_heat_hawk",
        weapon_name="热能斧",
        weapon_type=WeaponType.MELEE,
        weapon_tags=["heat"],
        attack_result="DODGE",
        damage=0,
        distance=3,
        attacker_will_delta=0,
        defender_will_delta=2,
        triggered_skills=["spirit_lucky_dodge"],
        is_first_attack=True,
        initiative_holder="attacker"
    )

    pres_events1 = mapper.map_attack(event1)
    rendered1 = renderer.render_attack(pres_events1)
    print(rendered1)
    print()

    # 测试场景2：T2 命中
    print("场景2: T2 轻武器命中")
    print("-" * 80)
    event2 = RawAttackEvent(
        round_number=2,
        attacker_id="gundam_01",
        defender_id="zaku_01",
        attacker_name="高达",
        defender_name="扎古指挥官型",
        weapon_id="wp_vulcan",
        weapon_name="火神炮",
        weapon_type=WeaponType.SHOOTING,
        weapon_tags=["bullet"],
        attack_result="HIT",
        damage=150,
        distance=5,
        attacker_will_delta=1,
        defender_will_delta=0,
        triggered_skills=[],
        is_first_attack=False,
        initiative_holder="attacker"
    )

    pres_events2 = mapper.map_attack(event2)
    rendered2 = renderer.render_attack(pres_events2)
    print(rendered2)
    print()

    # 测试场景3：T2 暴击
    print("场景3: T2 重击暴击")
    print("-" * 80)
    event3 = RawAttackEvent(
        round_number=3,
        attacker_id="gundam_01",
        defender_id="zaku_01",
        attacker_name="高达",
        defender_name="扎古指挥官型",
        weapon_id="wp_beam_saber",
        weapon_name="光束军刀",
        weapon_type=WeaponType.MELEE,
        weapon_tags=["beam"],
        attack_result="CRIT",
        damage=2500,
        distance=2,
        attacker_will_delta=3,
        defender_will_delta=-2,
        triggered_skills=["melee_crit_mastery"],
        is_first_attack=False,
        initiative_holder="attacker"
    )

    pres_events3 = mapper.map_attack(event3)
    rendered3 = renderer.render_attack(pres_events3)
    print(rendered3)
    print()

    # 测试场景4：格挡
    print("场景4: 格挡")
    print("-" * 80)
    event4 = RawAttackEvent(
        round_number=4,
        attacker_id="zaku_01",
        defender_id="gundam_01",
        attacker_name="扎古指挥官型",
        defender_name="高达",
        weapon_id="wp_crasher",
        weapon_name="破碎球",
        weapon_type=WeaponType.MELEE,
        weapon_tags=["impact"],
        attack_result="PARRY",
        damage=0,
        distance=2,
        attacker_will_delta=0,
        defender_will_delta=1,
        triggered_skills=["shield_parry"],
        is_first_attack=False,
        initiative_holder="defender"
    )

    pres_events4 = mapper.map_attack(event4)
    rendered4 = renderer.render_attack(pres_events4)
    print(rendered4)
    print()


def test_comprehensive_scenarios():
    """全面测试所有可能的战斗场景"""
    print("=" * 80)
    print("全面场景测试")
    print("=" * 80)
    print()

    # 加载配置
    config_path = os.path.join(project_root, "config", "presentation_templates.yaml")
    registry = TemplateRegistry(config_path)
    mapper = EventMapper(registry)
    renderer = TextRenderer()

    # 测试场景矩阵
    test_cases = [
        # (武器类型, 攻击结果, 伤害, 技能, 描述)
        (WeaponType.MELEE, "HIT", 800, [], "近战命中"),
        (WeaponType.MELEE, "CRIT", 2500, [], "近战暴击"),
        (WeaponType.MELEE, "DODGE", 0, ["spirit_lucky_dodge"], "近战闪避"),
        (WeaponType.MELEE, "PARRY", 0, [], "近战格挡"),
        (WeaponType.MELEE, "MISS", 0, [], "近战未命中"),

        (WeaponType.SHOOTING, "HIT", 1200, [], "射击命中"),
        (WeaponType.SHOOTING, "CRIT", 3000, [], "射击暴击"),
        (WeaponType.SHOOTING, "DODGE", 0, [], "射击闪避"),
        (WeaponType.SHOOTING, "MISS", 0, [], "射击未命中"),

        (WeaponType.SPECIAL, "HIT", 500, [], "特殊攻击命中"),
        (WeaponType.SPECIAL, "CRIT", 1500, [], "特殊攻击暴击"),
    ]

    passed = 0
    failed = 0

    for i, (w_type, result, dmg, skills, desc) in enumerate(test_cases, 1):
        print(f"测试 {i}: {desc}")
        print("-" * 80)

        try:
            event = create_event(
                i, "攻击方", "防御方", "测试武器",
                w_type, result, dmg, skills, is_first=(i == 1)
            )

            pres_events = mapper.map_attack(event)
            rendered = renderer.render_attack(pres_events)

            print(rendered)
            print(f"✓ 通过 - Tier: {pres_events[0].tier.value if pres_events else 'N/A'}")
            passed += 1

        except Exception as e:
            print(f"✗ 失败 - {str(e)}")
            failed += 1
            import traceback
            traceback.print_exc()

        print()

    # 测试特殊技能场景
    print("=" * 80)
    print("特殊技能场景测试")
    print("=" * 80)
    print()

    special_cases = [
        {
            "name": "精神闪光闪避",
            "event": create_event(1, "扎古", "高达", "热能斧", WeaponType.MELEE,
                                 "DODGE", 0, ["spirit_lucky_dodge"], True)
        },
        {
            "name": "暴击精通",
            "event": create_event(2, "高达", "大魔", "光束军刀", WeaponType.MELEE,
                                 "CRIT", 2800, ["melee_crit_mastery"], False)
        },
        {
            "name": "远狙精准",
            "event": create_event(3, "狙击型高达", "勇士", "狙击步枪", WeaponType.SHOOTING,
                                 "HIT", 1800, ["long_range_precision"], False)
        },
    ]

    for case in special_cases:
        print(f"场景: {case['name']}")
        print("-" * 80)

        try:
            pres_events = mapper.map_attack(case['event'])
            rendered = renderer.render_attack(pres_events)
            print(rendered)
            print(f"✓ 通过 - Tier: {pres_events[0].tier.value if pres_events else 'N/A'}")
            passed += 1
        except Exception as e:
            print(f"✗ 失败 - {str(e)}")
            failed += 1

        print()

    # 测试汇总
    print("=" * 80)
    print("测试汇总")
    print("=" * 80)
    print(f"总计: {passed + failed} 个测试")
    print(f"✓ 通过: {passed}")
    print(f"✗ 失败: {failed}")
    if passed + failed > 0:
        print(f"成功率: {passed / (passed + failed) * 100:.1f}%")
    print("=" * 80)

    assert failed == 0, f"有 {failed} 个测试失败"


def run_all_tests():
    """运行所有测试"""
    print("\n")
    print("*" * 80)
    print("*" + " " * 78 + "*")
    print("*" + " " * 20 + "演出系统测试套件" + " " * 42 + "*")
    print("*" + " " * 78 + "*")
    print("*" * 80)
    print("\n")

    try:
        test_mapper()
        test_text_renderer()
        test_integration_scenarios()
        success = test_comprehensive_scenarios()

        print("\n")
        print("=" * 80)
        print("所有测试完成！")
        print("=" * 80)

        return success

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # 如果作为脚本运行，调用 pytest
    import pytest
    pytest.main([__file__, "-v", "-s"])
