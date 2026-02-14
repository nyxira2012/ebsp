"""
演出系统测试脚本
验证演出系统的基本功能
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.presentation import EventMapper, TextRenderer, RawAttackEvent


def test_mapper():
    """测试事件转换器"""
    print("=" * 80)
    print("测试事件转换器 (EventMapper)")
    print("=" * 80)
    print()

    # 创建事件转换器
    mapper = EventMapper()

    # 创建测试用的原始攻击事件
    raw_event = RawAttackEvent(
        round_number=1,
        attacker_id="mecha_001",
        defender_id="mecha_002",
        attacker_name="RX-78-2 高达",
        defender_name="MS-06S 扎古指挥官型",
        weapon_id="weapon_beam_saber",
        weapon_name="光束军刀",
        weapon_type="MELEE",
        attack_result="HIT",
        damage=1200,
        distance=800,
        attacker_will_delta=2,
        defender_will_delta=0,
        initiative_holder="mecha_001",
        initiative_reason="PERFORMANCE",
        triggered_skills=[],
        is_first_attack=True
    )

    # 转换为演出事件
    pres_event = mapper.map_attack(raw_event)

    # 打印结果
    print("原始事件:")
    print(f"  攻击方: {raw_event.attacker_name}")
    print(f"  防御方: {raw_event.defender_name}")
    print(f"  武器: {raw_event.weapon_name}")
    print(f"  结果: {raw_event.attack_result}")
    print(f"  伤害: {raw_event.damage}")
    print()

    print("演出事件:")
    print(f"  文本: {pres_event.text}")
    print(f"  动画ID: {pres_event.anim_id}")
    print(f"  特效ID: {pres_event.vfx_ids}")
    print(f"  命中部位: {pres_event.hit_location}")
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
    from src.presentation.models import PresentationAttackEvent

    test_event = PresentationAttackEvent(
        round_number=1,
        is_first_attack=True,
        text="高达的光束军刀从腰部挂架中抽出的刹那，机体已化作白色闪光！刀刃精准刺向扎古的左侧肩甲。（命中！伤害 1200）",
        display_tags=["命中"],
        section_type="ACTION_FIRST",
        anim_id="anim_saber_slash_01",
        damage_display=1200,
        hit_location="左侧肩甲",
        attacker_name="高达",
        defender_name="扎古",
        weapon_name="光束军刀",
        attack_result="HIT"
    )

    # 渲染文本
    rendered_text = renderer.render_attack(test_event)
    print("渲染结果:")
    print(rendered_text)
    print()


def test_different_attack_results():
    """测试不同攻击结果的演出文本"""
    print("=" * 80)
    print("测试不同攻击结果的演出")
    print("=" * 80)
    print()

    mapper = EventMapper()
    renderer = TextRenderer()

    # 测试场景列表
    test_scenarios = [
        ("MELEE", "HIT", True),
        ("MELEE", "CRIT", True),
        ("MELEE", "DODGE", True),
        ("MELEE", "PARRY", True),
        ("RIFLE", "HIT", True),
        ("RIFLE", "CRIT", True),
    ]

    for weapon_type, result, is_first in test_scenarios:
        raw_event = RawAttackEvent(
            round_number=1,
            attacker_id="mecha_a",
            defender_id="mecha_b",
            attacker_name="高达",
            defender_name="扎古",
            weapon_id="weapon_test",
            weapon_name="测试武器",
            weapon_type=weapon_type,
            attack_result=result,
            damage=800,
            distance=1000,
            attacker_will_delta=0,
            defender_will_delta=0,
            initiative_holder="mecha_a",
            initiative_reason="PERFORMANCE",
            triggered_skills=[],
            is_first_attack=is_first
        )

        pres_event = mapper.map_attack(raw_event)
        rendered = renderer.render_attack(pres_event)

        print(f"[{weapon_type}] [{result}]")
        print(f"  {rendered}")
        print()


if __name__ == "__main__":
    try:
        test_mapper()
        test_text_renderer()
        test_different_attack_results()

        print("=" * 80)
        print("所有测试完成！")
        print("=" * 80)

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
