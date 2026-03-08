"""物品生成核心功能测试

测试装备与词条生成系统 (Doc 8):
1. ilvl 生成与 ±5% 浮动 (Doc 8 §5)
2. 词条档位 T0-T4 权重分布 (Doc 8 §3.1)
3. 技能槽 0.5% 概率 (Doc 8 §3.2)
4. 词条不重复 (Doc 8 §5)
5. 颜色分计算 (Doc 8 §4)
"""

import pytest
from unittest.mock import patch, MagicMock, Mock
from src.core.item_generator import EquipmentGenerator
from src.loader import DataLoader
from src.models import EquipmentConfig, AffixConfig
from src.user.schemas import EquipmentRandomStats, AffixEntry


class TestLegacyBehavior:
    """保持与旧测试的兼容性"""

    def test_equipment_generator(self):
        """原测试用例 - 保持兼容"""
        loader = DataLoader()
        loader.equipments = {"test_eq": EquipmentConfig(id="test_eq", name="Test", type="WEAPON", series=[], modifiers={})}
        loader.affixes = {
            "stat_hit": AffixConfig(id="stat_hit", type="stat", target="final_hit", base_value=1.0, ilvl_scale=0.1, min_ilvl=1, weight=1000, slot_tags=["WEAPON"]),
            "skill_snipe": AffixConfig(id="skill_snipe", type="skill", skill_id="sniper", min_ilvl=1, weight=100, slot_tags=["WEAPON"])
        }

        gen = EquipmentGenerator(loader)

        with patch("random.randint", return_value=10):
            with patch("random.choices", side_effect=[
                [3], [loader.affixes["stat_hit"]],  # slot 1: T3, stat_hit
                [0],                               # slot 2: T0
                [1], [loader.affixes["stat_hit"]],  # slot 3: T1, stat_hit
                [loader.affixes["skill_snipe"]]    # skill
            ]):
                with patch("random.random", return_value=0.001):  # < SKILL_CHANCE
                    res = gen.generate_equipment("test_eq", 10)

                    assert res["ilvl"] == 10
                    assert len(res["affixes"]) == 2
                    assert res["skill"] == "sniper"


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_loader():
    """模拟 DataLoader"""
    loader = Mock()

    # 模拟装备配置
    loader.get_equipment_config = Mock(return_value=EquipmentConfig(
        id="beam_rifle",
        name="Beam Rifle",
        type="WEAPON",
        series=["RX"],
        modifiers={}
    ))

    # 模拟词条配置
    loader.affixes = {
        # 属性词条
        "stat_hit": AffixConfig(
            id="stat_hit",
            type="stat",
            target="final_hit",
            base_value=2.0,
            ilvl_scale=0.2,
            min_ilvl=1,
            weight=1000,
            slot_tags=["WEAPON", "EQUIP"]
        ),
        "stat_crit": AffixConfig(
            id="stat_crit",
            type="stat",
            target="final_crit",
            base_value=1.0,
            ilvl_scale=0.1,
            min_ilvl=10,
            weight=500,
            slot_tags=["WEAPON", "EQUIP"]
        ),
        "stat_dodge": AffixConfig(
            id="stat_dodge",
            type="stat",
            target="final_dodge",
            base_value=1.0,
            ilvl_scale=0.1,
            min_ilvl=1,
            weight=800,
            slot_tags=["EQUIP"]  # 不适用于武器
        ),
        # 技能词条
        "skill_auto_repair": AffixConfig(
            id="skill_auto_repair",
            type="skill",
            skill_id="auto_repair",
            min_ilvl=20,
            weight=100,
            slot_tags=["EQUIP"]
        ),
        "skill_shield_boost": AffixConfig(
            id="skill_shield_boost",
            type="skill",
            skill_id="shield_boost",
            min_ilvl=1,
            weight=50,
            slot_tags=["WEAPON", "EQUIP"]
        ),
    }

    return loader


# ============================================================================
# ilvl 生成测试 (Doc 8 §5)
# ============================================================================

class TestIlvlGeneration:
    """测试 ilvl 生成逻辑"""

    def test_roll_ilvl_with_variance(self, mock_loader):
        """测试 ilvl 生成有 ±5% 浮动"""
        gen = EquipmentGenerator(mock_loader)

        # base_ilvl = 100, variance = 5
        # 结果应在 [95, 105] 范围内
        for _ in range(100):
            ilvl = gen._roll_ilvl(100)
            assert 95 <= ilvl <= 105

    def test_roll_ilvl_minimum_1(self, mock_loader):
        """测试 ilvl 最小值为 1"""
        gen = EquipmentGenerator(mock_loader)

        # base_ilvl = 5, variance 至少为 1
        ilvl = gen._roll_ilvl(5)
        assert ilvl >= 1

    def test_generate_equipment_contains_ilvl(self, mock_loader):
        """测试生成的装备包含 ilvl"""
        gen = EquipmentGenerator(mock_loader)

        result = gen.generate_equipment("beam_rifle", base_ilvl=50)

        assert "ilvl" in result
        assert isinstance(result["ilvl"], int)
        # 50 的 5% 是 2.5，向下取整为 2
        # 范围应该是 [48, 52]
        assert 48 <= result["ilvl"] <= 52


# ============================================================================
# 词条档位权重测试 (Doc 8 §3.1)
# ============================================================================

class TestAffixTierWeights:
    """测试词条档位 T0-T4 权重分布"""

    def test_tier_weights_sum_to_100(self, mock_loader):
        """测试档位权重总和为 100"""
        gen = EquipmentGenerator(mock_loader)

        total_weight = sum(gen.TIER_WEIGHTS.values())
        assert total_weight == pytest.approx(100.0, rel=0.1)  # 39+35+18+7+1 = 100

    def test_roll_tier_distribution(self, mock_loader):
        """测试档位抽取符合权重分布"""
        gen = EquipmentGenerator(mock_loader)

        # 抽取大量样本，验证分布
        tiers = [gen._roll_tier() for _ in range(10000)]

        # T0 (39%) 应该最常见
        t0_count = tiers.count(0)
        t0_percent = t0_count / 10000 * 100
        assert 35 < t0_percent < 43  # 约39%

        # T4 (1%) 应该最稀有
        t4_count = tiers.count(4)
        t4_percent = t4_count / 10000 * 100
        assert 0.5 < t4_percent < 1.5  # 约1%

    def test_roll_tier_all_values_possible(self, mock_loader):
        """测试所有档位 T0-T4 都可能出现"""
        gen = EquipmentGenerator(mock_loader)

        # 足够多的尝试，确保所有档位都出现过
        tiers = set()
        for _ in range(10000):
            tiers.add(gen._roll_tier())
            if len(tiers) == 5:  # 0,1,2,3,4
                break

        assert tiers == {0, 1, 2, 3, 4}


# ============================================================================
# 技能槽概率测试 (Doc 8 §3.2)
# ============================================================================

class TestSkillSlotChance:
    """测试技能槽 0.5% 概率"""

    def test_skill_chance_is_0_5_percent(self, mock_loader):
        """测试 SKILL_CHANCE = 0.005 (0.5%)"""
        gen = EquipmentGenerator(mock_loader)
        assert gen.SKILL_CHANCE == 0.005

    def test_skill_slot_rare(self, mock_loader):
        """测试技能槽很罕见"""
        gen = EquipmentGenerator(mock_loader)

        # 生成 1000 件装备
        skill_count = 0
        for _ in range(1000):
            result = gen.generate_equipment("beam_rifle", base_ilvl=50)
            if result.get("skill"):
                skill_count += 1

        # 0.5% 概率，1000 次期望约 5 次
        # 允许一定的随机波动
        assert 0 <= skill_count < 20  # 绝大多数情况下应该少于 20 次

    def test_skill_slot_possible(self, mock_loader):
        """测试技能槽可能出现（需要足够尝试）"""
        gen = EquipmentGenerator(mock_loader)

        # 多次尝试直到出现技能
        found_skill = False
        for _ in range(10000):
            result = gen.generate_equipment("beam_rifle", base_ilvl=50)
            if result.get("skill"):
                found_skill = True
                break

        # 10000 次尝试，0.5% 概率几乎肯定会出现
        assert found_skill


# ============================================================================
# 词条生成与筛选测试
# ============================================================================

class TestAffixGeneration:
    """测试词条生成逻辑"""

    def test_filter_affixes_by_type(self, mock_loader):
        """测试按类型筛选词条"""
        gen = EquipmentGenerator(mock_loader)

        # 只获取 stat 类型
        stat_affixes = gen._filter_affixes("stat", current_ilvl=50, equip_type="WEAPON", exclude_ids=set())
        affix_ids = [a.id for a in stat_affixes]

        # 应该包含 stat_hit 和 stat_crit，不包含 skill_xxx
        assert "stat_hit" in affix_ids
        assert "stat_crit" in affix_ids
        assert "skill_auto_repair" not in affix_ids
        assert "skill_shield_boost" not in affix_ids

    def test_filter_affixes_by_min_ilvl(self, mock_loader):
        """测试按 min_ilvl 筛选词条"""
        gen = EquipmentGenerator(mock_loader)

        # ilvl 15 时，stat_crit (min_ilvl=10) 应该可用
        affixes = gen._filter_affixes("stat", current_ilvl=15, equip_type="WEAPON", exclude_ids=set())
        affix_ids = [a.id for a in affixes]

        assert "stat_hit" in affix_ids
        assert "stat_crit" in affix_ids

        # ilvl 5 时，stat_crit (min_ilvl=10) 不应该可用
        affixes = gen._filter_affixes("stat", current_ilvl=5, equip_type="WEAPON", exclude_ids=set())
        affix_ids = [a.id for a in affixes]

        assert "stat_hit" in affix_ids
        assert "stat_crit" not in affix_ids

    def test_filter_affixes_by_slot_tags(self, mock_loader):
        """测试按槽位标签筛选词条"""
        gen = EquipmentGenerator(mock_loader)

        # WEAPON 类型应该能获取 stat_hit
        # 但 stat_dodge 只适用于 EQUIP
        affixes = gen._filter_affixes("stat", current_ilvl=50, equip_type="WEAPON", exclude_ids=set())
        affix_ids = [a.id for a in affixes]

        assert "stat_hit" in affix_ids
        assert "stat_dodge" not in affix_ids

    def test_filter_affixes_excludes_ids(self, mock_loader):
        """测试排除指定词条 ID"""
        gen = EquipmentGenerator(mock_loader)

        # 排除 stat_hit
        affixes = gen._filter_affixes(
            "stat",
            current_ilvl=50,
            equip_type="WEAPON",
            exclude_ids={"stat_hit"}
        )
        affix_ids = [a.id for a in affixes]

        assert "stat_hit" not in affix_ids
        assert "stat_crit" in affix_ids


# ============================================================================
# 完整装备生成测试
# ============================================================================

class TestEquipmentGeneration:
    """测试完整装备生成流程"""

    def test_generate_equipment_structure(self, mock_loader):
        """测试生成装备的数据结构"""
        gen = EquipmentGenerator(mock_loader)

        result = gen.generate_equipment("beam_rifle", base_ilvl=50)

        # 验证返回结构
        assert "ilvl" in result
        assert "affixes" in result
        assert "skill" in result

        # 验证数据类型
        assert isinstance(result["ilvl"], int)
        assert isinstance(result["affixes"], list)
        assert isinstance(result["skill"], (str, type(None)))

    def test_generate_equipment_three_affix_slots(self, mock_loader):
        """测试生成 3 个词条槽"""
        gen = EquipmentGenerator(mock_loader)

        result = gen.generate_equipment("beam_rifle", base_ilvl=50)

        # affixes 最多 3 条
        assert len(result["affixes"]) <= 3

        # 每条词条有 id 和 t 字段
        for affix in result["affixes"]:
            assert "id" in affix
            assert "t" in affix
            assert affix["t"] in {1, 2, 3, 4}  # T0 不存入 affixes

    def test_generate_equipment_tier_0_not_stored(self, mock_loader):
        """测试 T0 (空槽) 不存入 affixes"""
        gen = EquipmentGenerator(mock_loader)

        # 多次生成，统计 affix 数量
        # T0 概率 39%，所以应该有很多少于 3 条词条的情况
        empty_count = 0
        for _ in range(100):
            result = gen.generate_equipment("beam_rifle", base_ilvl=50)
            if len(result["affixes"]) < 3:
                empty_count += 1

        assert empty_count > 50  # 应该超过一半


# ============================================================================
# 颜色分计算测试 (Doc 8 §4)
# ============================================================================

class TestColorCalculation:
    """测试颜色分计算逻辑"""

    def test_color_from_affixes_only(self):
        """测试仅由属性数决定颜色"""
        # 0 条属性 = 白色 (0)
        stats = EquipmentRandomStats(ilvl=1, affixes=[], skill=None)
        assert stats.color == 0

        # 1 条属性 = 绿色 (1)
        stats = EquipmentRandomStats(ilvl=1, affixes=[AffixEntry(id="test", t=1)], skill=None)
        assert stats.color == 1

        # 2 条属性 = 蓝色 (2)
        stats = EquipmentRandomStats(ilvl=1, affixes=[
            AffixEntry(id="test1", t=1),
            AffixEntry(id="test2", t=2)
        ], skill=None)
        assert stats.color == 2

        # 3 条属性 = 紫色 (3)
        stats = EquipmentRandomStats(ilvl=1, affixes=[
            AffixEntry(id="test1", t=1),
            AffixEntry(id="test2", t=2),
            AffixEntry(id="test3", t=3)
        ], skill=None)
        assert stats.color == 3

    def test_color_skill_bonus(self):
        """测试技能提供 +2 颜色分"""
        # 1 属性 + 技能 = 紫色 (1 + 2 = 3)
        stats = EquipmentRandomStats(
            ilvl=1,
            affixes=[AffixEntry(id="test", t=1)],
            skill="auto_repair"
        )
        assert stats.color == 3

        # 2 属性 + 技能 = 橙色 (2 + 2 = 4)
        stats = EquipmentRandomStats(
            ilvl=1,
            affixes=[
                AffixEntry(id="test1", t=1),
                AffixEntry(id="test2", t=2)
            ],
            skill="auto_repair"
        )
        assert stats.color == 4

    def test_color_max_is_4(self):
        """测试颜色分最高为 4"""
        # 3 属性 + 技能应该是 5，但 capped at 4
        stats = EquipmentRandomStats(
            ilvl=1,
            affixes=[
                AffixEntry(id="test1", t=1),
                AffixEntry(id="test2", t=2),
                AffixEntry(id="test3", t=3)
            ],
            skill="auto_repair"
        )
        # min(4, len + 2) = min(4, 5) = 4
        assert stats.color == 4


# ============================================================================
# 边界条件测试
# ============================================================================

class TestEdgeCases:
    """测试边界条件"""

    def test_generate_with_no_valid_affixes(self):
        """测试没有可用词条时的处理"""
        # 使用一个没有词条的 loader
        empty_loader = Mock()
        empty_loader.get_equipment_config = Mock(return_value=EquipmentConfig(
            id="empty_item",
            name="Empty",
            type="WEAPON",
            series=[],
            modifiers={}
        ))
        empty_loader.affixes = {}

        gen = EquipmentGenerator(empty_loader)
        result = gen.generate_equipment("empty_item", base_ilvl=50)

        # 应该正常返回，只是没有词条
        assert result["ilvl"] >= 45
        assert result["affixes"] == []
        assert result["skill"] is None
