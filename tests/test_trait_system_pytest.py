"""
特性系统测试 (pytest 版本)
验证特性如何从定义变成永久 Effect，并参与 Hook 计算
"""

import pytest
from src.models import Mecha, Pilot, Effect
from src.skills import SkillRegistry, TraitManager


class TestTraitSystem:
    """特性系统测试组（pytest 会自动发现这个类）"""

    def test_newtype_trait_hit_rate(self, basic_mecha, basic_context):
        """验证 Newtype 特性的命中加成"""
        # 应用特性
        basic_mecha.skills = ["trait_nt"]
        TraitManager.apply_traits(basic_mecha)

        # 验证效果数量
        assert len(basic_mecha.effects) == 2, "NT特性应该产生2个效果"

        # 验证命中加成
        final_hit = SkillRegistry.process_hook(
            "HOOK_PRE_HIT_RATE", 50.0, basic_context
        )
        assert final_hit == 65.0, f"基础50 + NT加成15 应该等于65，实际: {final_hit}"

    def test_newtype_trait_dodge_rate(self, basic_mecha, basic_context):
        """验证 Newtype 特性的回避加成"""
        basic_mecha.skills = ["trait_nt"]
        TraitManager.apply_traits(basic_mecha)

        final_eva = SkillRegistry.process_hook(
            "HOOK_PRE_DODGE_RATE", 40.0, basic_context
        )
        assert final_eva == 55.0, f"基础40 + NT加成15 应该等于55，实际: {final_eva}"

    def test_expert_trait_damage_bonus(self, basic_mecha, basic_context):
        """验证精英驾驶员特性的伤害加成"""
        basic_mecha.skills = ["trait_expert"]
        TraitManager.apply_traits(basic_mecha)

        val = SkillRegistry.process_hook(
            "HOOK_PRE_DAMAGE_MULT", 1.0, basic_context
        )
        assert val == 1.1, f"精英应该增加10%伤害，实际倍率: {val}"

    def test_expert_trait_en_saving(self, basic_mecha, basic_context):
        """验证精英驾驶员特性的EN节省"""
        basic_mecha.skills = ["trait_expert"]
        TraitManager.apply_traits(basic_mecha)

        en_cost = SkillRegistry.process_hook(
            "HOOK_PRE_EN_COST_MULT", 100.0, basic_context
        )
        assert en_cost == 90.0, f"精英应该节省10% EN，实际消耗: {en_cost}"


# 运行这个测试文件的命令：
# pytest tests/test_trait_system_pytest.py -v
#
# 输出示例：
# tests/test_trait_system_pytest.py::TestTraitSystem::test_newtype_trait_hit_rate PASSED
# tests/test_trait_system_pytest.py::TestTraitSystem::test_newtype_trait_dodge_rate PASSED
# tests/test_trait_system_pytest.py::TestTraitSystem::test_expert_trait_damage_bonus PASSED
# tests/test_trait_system_pytest.py::TestTraitSystem::test_expert_trait_en_saving PASSED
