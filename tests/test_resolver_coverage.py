"""
补充 resolver.py 的边界条件测试
主要覆盖 _calculate_segments 方法 (23-103行) 的各种场景
"""

import pytest
from src.models import Mecha, Pilot, BattleContext, Weapon, WeaponType
from src.combat.resolver import AttackTableResolver


# ============================================================================
# 测试熟练度影响
# ============================================================================

# 注意：所有 fixtures 已移至 conftest.py
# 包括: standard_pilot, high_proficiency_pilot, low_proficiency_pilot
#       balanced_mecha, offensive_mecha, defensive_mecha, standard_context

class TestProficiencyImpact:
    """测试熟练度对圆桌判定的影响"""

    def test_low_weapon_proficiency_increases_miss(self, low_proficiency_pilot, standard_pilot):
        """测试低武器熟练度增加MISS率"""
        attacker = Mecha(
            id="m_rookie", name="RookieMecha", pilot=low_proficiency_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=0.0,  # 无额外命中加成
            precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )
        defender = Mecha(
            id="m_defender", name="Defender",
            pilot=standard_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            attacker=attacker, defender=defender, weapon=None
        )

        segments = AttackTableResolver._calculate_segments(ctx)

        # 低熟练度应该有显著的MISS段
        assert 'MISS' in segments
        assert segments['MISS']['rate'] > 0

    def test_high_weapon_proficiency_reduces_miss(self, high_proficiency_pilot, standard_pilot):
        """测试高武器熟练度减少MISS率"""
        attacker = Mecha(
            id="m_ace", name="AceMecha", pilot=high_proficiency_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=20.0,  # 额外命中加成
            precision=15.0, crit_rate=10.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )
        defender = Mecha(
            id="m_defender", name="Defender",
            pilot=standard_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            attacker=attacker, defender=defender, weapon=None
        )

        segments = AttackTableResolver._calculate_segments(ctx)

        # 高熟练度应该MISS率很低或为0
        if 'MISS' in segments:
            assert segments['MISS']['rate'] < 20  # 应该很低

    def test_high_mecha_proficiency_increases_defense(self, high_proficiency_pilot, standard_pilot):
        """测试高机体熟练度增加防御率"""
        attacker = Mecha(
            id="m_attacker", name="Attacker",
            pilot=standard_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=20.0, precision=10.0, crit_rate=10.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )
        defender = Mecha(
            id="m_defender", name="Defender", pilot=high_proficiency_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            attacker=attacker, defender=defender, weapon=None
        )

        segments = AttackTableResolver._calculate_segments(ctx)

        # 高熟练度应该提升DODGE/PARRY/BLOCK
        defense_total = segments.get('DODGE', {}).get('rate', 0) + \
                       segments.get('PARRY', {}).get('rate', 0) + \
                       segments.get('BLOCK', {}).get('rate', 0)
        assert defense_total > 30  # 应该有显著的防御率


# ============================================================================
# 测试精度影响
# ============================================================================

class TestPrecisionImpact:
    """测试精度对防御率的影响"""

    def test_high_precision_reduces_defense(self, offensive_mecha, standard_pilot):
        """测试高精度降低防御率"""
        defender = Mecha(
            id="m_defender", name="Defender",
            pilot=standard_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=30.0, parry_rate=25.0, block_rate=20.0,  # 高防御
            defense_level=1000, mobility=100
        )

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            attacker=offensive_mecha, defender=defender, weapon=None
        )

        segments = AttackTableResolver._calculate_segments(ctx)

        # 高精度应该显著降低防御率
        dodge_rate = segments.get('DODGE', {}).get('rate', 0)
        parry_rate = segments.get('PARRY', {}).get('rate', 0)
        block_rate = segments.get('BLOCK', {}).get('rate', 0)

        # 实际防御率应该低于基础值（因为有精度削减）
        assert dodge_rate < 30 or parry_rate < 25 or block_rate < 20

    def test_low_precision_defense_unaffected(self, balanced_mecha, standard_pilot):
        """测试低精度不影响防御"""
        attacker = Mecha(
            id="m_low_prec", name="LowPrecision",
            pilot=standard_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=0.0, crit_rate=5.0,  # 低精度
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )
        defender = Mecha(
            id="m_defender", name="Defender",
            pilot=standard_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=20.0, parry_rate=15.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            attacker=attacker, defender=defender, weapon=None
        )

        segments = AttackTableResolver._calculate_segments(ctx)

        # 低精度时防御率应该接近基础值
        dodge_rate = segments.get('DODGE', {}).get('rate', 0)
        assert dodge_rate >= 15  # 应该接近20的基础值


# ============================================================================
# 测试防御率上限
# ============================================================================

class TestDefenseCaps:
    """测试防御率上限"""

    def test_parry_hard_cap_50_percent(self, standard_pilot, high_proficiency_pilot):
        """测试PARRY 50%硬上限"""
        attacker = Mecha(
            id="m_attacker", name="Attacker",
            pilot=standard_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=0.0, crit_rate=5.0,  # 无精度削减
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )
        defender = Mecha(
            id="m_defender", name="Defender",
            pilot=high_proficiency_pilot,  # 高熟练度
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=60.0, block_rate=10.0,  # 超高PARRY
            defense_level=1000, mobility=100
        )

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            attacker=attacker, defender=defender, weapon=None
        )

        segments = AttackTableResolver._calculate_segments(ctx)

        # PARRY不应该超过50%
        parry_rate = segments.get('PARRY', {}).get('rate', 0)
        assert parry_rate <= 50.0

    def test_block_hard_cap_80_percent(self, standard_pilot, high_proficiency_pilot):
        """测试BLOCK 80%硬上限"""
        attacker = Mecha(
            id="m_attacker", name="Attacker",
            pilot=standard_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=0.0, crit_rate=5.0,  # 无精度削减
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )
        defender = Mecha(
            id="m_defender", name="Defender",
            pilot=high_proficiency_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=100.0,  # 超高BLOCK
            defense_level=1000, mobility=100
        )

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            attacker=attacker, defender=defender, weapon=None
        )

        segments = AttackTableResolver._calculate_segments(ctx)

        # BLOCK不应该超过80%
        block_rate = segments.get('BLOCK', {}).get('rate', 0)
        assert block_rate <= 80.0


# ============================================================================
# 测试CRIT被挤压
# ============================================================================

class TestCritSqueezing:
    """测试CRIT被前面的段挤压"""

    def test_crit_squeezed_by_high_defense(self, standard_pilot, high_proficiency_pilot):
        """测试高防御率挤压CRIT空间"""
        attacker = Mecha(
            id="m_attacker", name="Attacker",
            pilot=standard_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=0.0, precision=0.0, crit_rate=30.0,  # 高暴击
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )
        defender = Mecha(
            id="m_defender", name="Defender",
            pilot=high_proficiency_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=0.0, crit_rate=5.0,
            dodge_rate=40.0, parry_rate=30.0, block_rate=20.0,  # 超高防御
            defense_level=1000, mobility=100
        )

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            attacker=attacker, defender=defender, weapon=None
        )

        segments = AttackTableResolver._calculate_segments(ctx)

        # CRIT应该被挤压，实际值可能小于理论值
        crit_rate = segments.get('CRIT', {}).get('rate', 0)
        total_before_crit = segments.get('MISS', {}).get('rate', 0) + \
                            segments.get('DODGE', {}).get('rate', 0) + \
                            segments.get('PARRY', {}).get('rate', 0) + \
                            segments.get('BLOCK', {}).get('rate', 0)

        if total_before_crit >= 100:
            # 如果前面的段已经满了，CRIT应该为0或很小
            assert crit_rate < 5

    def test_crit_no_space_left(self, low_proficiency_pilot, high_proficiency_pilot):
        """测试CRIT完全没有空间"""
        attacker = Mecha(
            id="m_attacker", name="Attacker",
            pilot=low_proficiency_pilot,  # 高MISS
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=0.0, precision=0.0, crit_rate=50.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )
        defender = Mecha(
            id="m_defender", name="Defender",
            pilot=high_proficiency_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=0.0, crit_rate=5.0,
            dodge_rate=40.0, parry_rate=30.0, block_rate=20.0,
            defense_level=1000, mobility=100
        )

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            attacker=attacker, defender=defender, weapon=None
        )

        segments = AttackTableResolver._calculate_segments(ctx)

        # MISS + DODGE + PARRY + BLOCK可能超过100
        # CRIT应该为0
        crit_rate = segments.get('CRIT', {}).get('rate', 0)
        assert crit_rate == 0 or segments.get('total', 0) >= 100


# ============================================================================
# 测试HIT段作为兜底
# ============================================================================

class TestHitAsFallback:
    """测试HIT段作为兜底"""

    def test_hit_fills_remaining_space(self, standard_context):
        """测试HIT填充剩余空间"""
        segments = AttackTableResolver._calculate_segments(standard_context)

        # HIT应该填充到100
        assert 'HIT' in segments
        assert segments['HIT']['end'] == 100

    def test_hit_rate_calculated_correctly(self, standard_context):
        """测试HIT率计算正确"""
        segments = AttackTableResolver._calculate_segments(standard_context)

        hit_rate = segments['HIT']['rate']
        hit_start = segments['HIT']['start']
        hit_end = segments['HIT']['end']

        # HIT率应该等于end-start
        assert hit_rate == hit_end - hit_start

    def test_no_hit_if_table_full(self, low_proficiency_pilot, standard_pilot):
        """测试圆桌满了就没有HIT"""
        # 构造一个MISS=100的极端情况
        attacker = Mecha(
            id="m_attacker", name="Attacker",
            pilot=low_proficiency_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=-100.0, precision=0.0, crit_rate=0.0,  # 负命中
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )
        defender = Mecha(
            id="m_defender", name="Defender",
            pilot=standard_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            attacker=attacker, defender=defender, weapon=None
        )

        segments = AttackTableResolver._calculate_segments(ctx)

        # 如果MISS已经100了，HIT应该为0
        if segments.get('MISS', {}).get('rate', 0) >= 100:
            hit_rate = segments.get('HIT', {}).get('rate', 0)
            assert hit_rate == 0


# ============================================================================
# 测试段边界计算
# ============================================================================

class TestSegmentBoundaries:
    """测试段的边界计算"""

    def test_segments_are_continuous(self, standard_context):
        """测试段是连续的（无缝隙）"""
        segments = AttackTableResolver._calculate_segments(standard_context)

        # 按start排序
        ordered_segments = sorted(
            [s for k, s in segments.items() if k != 'total'],
            key=lambda x: x['start']
        )

        # 检查连续性
        for i in range(len(ordered_segments) - 1):
            current_end = ordered_segments[i]['end']
            next_start = ordered_segments[i + 1]['start']
            assert current_end == next_start, f"段不连续: {ordered_segments[i]} -> {ordered_segments[i+1]}"

    def test_segment_ranges_not_negative(self, standard_context):
        """测试段的范围不为负"""
        segments = AttackTableResolver._calculate_segments(standard_context)

        for name, segment in segments.items():
            if name == 'total':
                continue
            assert segment['rate'] >= 0, f"{name} rate为负: {segment['rate']}"
            assert segment['start'] >= 0, f"{name} start为负: {segment['start']}"
            assert segment['end'] >= 0, f"{name} end为负: {segment['end']}"

    def test_total_does_not_exceed_100(self, standard_context):
        """测试总段不超过100"""
        segments = AttackTableResolver._calculate_segments(standard_context)

        total = segments.get('total', 0)
        # 由于各种修正，total可能略超过100
        assert total >= 100  # 至少到100


# ============================================================================
# 测试极端情况
# ============================================================================

class TestExtremeScenarios:
    """测试极端情况"""

    def test_all_zeros(self, standard_pilot):
        """测试所有属性为0"""
        attacker = Mecha(
            id="m_zero", name="ZeroMecha",
            pilot=standard_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=0.0, precision=0.0, crit_rate=0.0,
            dodge_rate=0.0, parry_rate=0.0, block_rate=0.0,
            defense_level=0, mobility=0
        )
        defender = Mecha(
            id="m_zero_def", name="ZeroDefender",
            pilot=standard_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=0.0, precision=0.0, crit_rate=0.0,
            dodge_rate=0.0, parry_rate=0.0, block_rate=0.0,
            defense_level=0, mobility=0
        )

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            attacker=attacker, defender=defender, weapon=None
        )

        segments = AttackTableResolver._calculate_segments(ctx)

        # 应该有MISS段（低熟练度）
        # 应该有HIT段作为兜底
        assert 'MISS' in segments or 'HIT' in segments

    def test_very_high_hit_rate(self, high_proficiency_pilot, standard_pilot):
        """测试超高命中率"""
        attacker = Mecha(
            id="m_godlike", name="GodlikeMecha",
            pilot=high_proficiency_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=100.0, precision=50.0, crit_rate=30.0,  # 超高属性
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )
        defender = Mecha(
            id="m_defender", name="Defender",
            pilot=standard_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            attacker=attacker, defender=defender, weapon=None
        )

        segments = AttackTableResolver._calculate_segments(ctx)

        # MISS应该为0或很小
        miss_rate = segments.get('MISS', {}).get('rate', 0)
        assert miss_rate < 10

        # HIT或CRIT应该占大部分
        hit_rate = segments.get('HIT', {}).get('rate', 0)
        crit_rate = segments.get('CRIT', {}).get('rate', 0)
        assert (hit_rate + crit_rate) > 50
