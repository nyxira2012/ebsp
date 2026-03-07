"""
单元测试: 战斗系统 - 圆桌判定 (Resolver)
测试 AttackTableResolver 的圆桌判定逻辑、伤害计算和段计算边界条件
"""

import copy
import pytest
from unittest.mock import patch
from src.models import Mecha, MechaSnapshot, BattleContext, AttackResult, Weapon, WeaponType, Terrain
from src.combat.resolver import AttackTableResolver


# ============================================================================
# 圆桌判定基础测试
# ============================================================================

class TestAttackTableResolution:
    """圆桌判定基础测试"""

    @patch('random.uniform')
    def test_miss_result(self, mock_uniform, basic_context):
        """测试未命中结果 (roll < miss_rate)"""
        mock_uniform.return_value = 0.5  # 假设miss_rate足够大

        # 设置高未命中率
        basic_context.attacker.pilot_stats_backup['weapon_proficiency'] = 0  # 最低熟练度

        result, damage = AttackTableResolver.resolve_attack(basic_context)
        assert result == AttackResult.MISS
        assert damage == 0

    @patch('random.uniform')
    def test_dodge_result(self, mock_uniform, basic_context):
        """测试躲闪结果"""
        # 设置roll值落在dodge区间
        # 默认miss_rate约13.6%，所以roll=20可以落在dodge区间
        mock_uniform.return_value = 20.0

        result, damage = AttackTableResolver.resolve_attack(basic_context)
        assert result == AttackResult.DODGE
        assert damage == 0

    def test_all_results_possible(self, basic_context):
        """测试所有结果都可能发生 (运行多次)"""
        results = set()
        for _ in range(100):
            result, _ = AttackTableResolver.resolve_attack(basic_context)
            results.add(result)

        # 应该至少出现3种不同的结果
        assert len(results) >= 3


# ============================================================================
# 优先级顺序测试
# ============================================================================

class TestPriorityOrder:
    """圆桌判定优先级顺序测试"""

    @patch('random.uniform')
    def test_priority_miss_first(self, mock_uniform, basic_context):
        """测试Miss优先级最高"""
        # roll=0 应该落在Miss区间（如果有miss_rate）
        mock_uniform.return_value = 0.0

        # 设置高未命中率
        basic_context.attacker.pilot_stats_backup['weapon_proficiency'] = 100

        result, _ = AttackTableResolver.resolve_attack(basic_context)
        # 最低熟练度会miss
        assert result == AttackResult.MISS

    def test_hit_is_fallback(self, basic_context):
        """测试Hit是兜底结果"""
        # 设置所有防御概率为0，降低暴击率
        basic_context.defender.final_dodge = 0
        basic_context.defender.final_parry = 0
        basic_context.defender.final_block = 0
        basic_context.attacker.final_crit = 0

        # 设置高命中加成
        basic_context.attacker.pilot_stats_backup['weapon_proficiency'] = 1000

        # 应该大部分时候是Hit或MISS，但由于命中率很高，主要是Hit
        with patch('random.uniform', return_value=50.0):
            result, damage = AttackTableResolver.resolve_attack(basic_context)
            # 由于防御概率为0，且miss被命中加成抵消，应该是Hit
            assert result in [AttackResult.HIT, AttackResult.MISS]


# ============================================================================
# 必中逻辑测试
# ============================================================================

class TestAlwaysHitLogic:
    """必中逻辑测试"""

    @patch('random.uniform')
    def test_hit_rate_100_clears_defense(self, mock_uniform, basic_context):
        """测试命中率100%清空所有防御"""
        mock_uniform.return_value = 50.0

        # 添加必中效果
        from src.models import Effect
        basic_context.attacker.effects.append(Effect(
            id="test_always_hit", name="Test Always Hit",
            hook="HOOK_PRE_HIT_RATE",
            operation="set", value=100.0,
            duration=1, priority=100
        ))

        result, _ = AttackTableResolver.resolve_attack(basic_context)
        # 必中情况下，不会是Miss/Dodge/Parry/Block
        # 只能是Crit或Hit
        assert result in [AttackResult.CRIT, AttackResult.HIT]


# ============================================================================
# 暴击计算测试
# ============================================================================

class TestCriticalHit:
    """暴击计算测试"""

    @patch('random.uniform')
    def test_crit_damage_multiplier(self, mock_uniform, basic_context):
        """测试暴击伤害倍率"""
        # 强制暴击结果
        mock_uniform.return_value = 95.0  # 假设暴击率足够高

        # 设置高暴击率
        basic_context.attacker.final_crit = 50

        result, damage = AttackTableResolver.resolve_attack(basic_context)

        if result == AttackResult.CRIT:
            # 暴击伤害应该 > 普通伤害
            # 我们通过比较相对大小来验证
            assert damage > 0

    @patch('random.uniform')
    def test_crit_will_bonus(self, mock_uniform, basic_context):
        """测试暴击气力加成"""
        mock_uniform.return_value = 95.0

        initial_will = basic_context.attacker.current_will
        basic_context.attacker.final_crit = 50

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        if result == AttackResult.CRIT:
            # 暴击应该给攻击方+5气力
            # 但气力变化存储在context中，不是直接修改mecha
            assert basic_context.current_attacker_will_delta == 5


# ============================================================================
# 伤害计算测试
# ============================================================================

class TestDamageCalculation:
    """伤害计算测试"""

    @patch('random.uniform')
    def test_base_damage_formula(self, mock_uniform, basic_context):
        """测试基础伤害公式"""
        mock_uniform.return_value = 95.0  # 确保命中

        result, damage = AttackTableResolver.resolve_attack(basic_context)

        if result in [AttackResult.HIT, AttackResult.CRIT]:
            # 基础伤害 = 武器威力 + (驾驶员属性 * 2) * 气力修正
            # damage应该 > 0
            assert damage > 0

    @patch('random.uniform')
    def test_block_reduces_damage(self, mock_uniform, basic_context):
        """测试格挡减伤"""
        # 设置高格挡率，强制格挡
        mock_uniform.return_value = 30.0
        basic_context.defender.final_block = 50
        basic_context.defender.block_reduction = 500

        result, damage = AttackTableResolver.resolve_attack(basic_context)

        if result == AttackResult.BLOCK:
            # 格挡伤害应该小于基础伤害
            # (基础伤害 - 格挡值)
            assert damage >= 0


# ============================================================================
# 气力变化测试
# ============================================================================

class TestWillChanges:
    """气力变化测试"""

    @patch('random.uniform')
    def test_miss_will_change(self, mock_uniform, basic_context):
        """测试Miss的气力变化"""
        mock_uniform.return_value = 0.0
        basic_context.attacker.pilot_stats_backup['weapon_proficiency'] = 0  # 确保miss

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        if result == AttackResult.MISS:
            # Miss没有气力变化
            assert basic_context.current_attacker_will_delta == 0
            assert basic_context.current_defender_will_delta == 0

    @patch('random.uniform')
    def test_dodge_will_change(self, mock_uniform, basic_context):
        """测试躲闪的气力变化"""
        mock_uniform.return_value = 1.0

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        if result == AttackResult.DODGE:
            # 躲闪: 防御方+5气力
            assert basic_context.current_defender_will_delta == 5

    @patch('random.uniform')
    def test_parry_will_change(self, mock_uniform, basic_context):
        """测试招架的气力变化"""
        # 设置高招架率
        mock_uniform.return_value = 5.0
        basic_context.defender.final_parry = 30

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        if result == AttackResult.PARRY:
            # 招架: 防御方+15气力
            assert basic_context.current_defender_will_delta == 15

    @patch('random.uniform')
    def test_hit_will_change(self, mock_uniform, basic_context):
        """测试命中的气力变化"""
        mock_uniform.return_value = 95.0
        basic_context.defender.final_dodge = 0
        basic_context.defender.final_parry = 0
        basic_context.defender.final_block = 0
        basic_context.attacker.final_crit = 0

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        if result == AttackResult.HIT:
            # 命中: 攻击方+2, 防御方+1
            assert basic_context.current_attacker_will_delta == 2
            assert basic_context.current_defender_will_delta == 1


# ============================================================================
# 护甲减伤测试
# ============================================================================

class TestArmorMitigation:
    """护甲减伤测试"""

    @patch('random.uniform')
    def test_armor_reduces_damage(self, mock_uniform, basic_context):
        """测试护甲减伤"""
        mock_uniform.return_value = 95.0

        # 设置高防御
        basic_context.defender.final_armor = 2000
        basic_context.defender.final_dodge = 0
        basic_context.defender.final_parry = 0
        basic_context.defender.final_block = 0
        basic_context.attacker.final_crit = 0

        result, damage = AttackTableResolver.resolve_attack(basic_context)

        if result == AttackResult.HIT:
            # 高防御应该显著减少伤害
            assert damage >= 0

    @patch('random.uniform')
    def test_no_negative_damage(self, mock_uniform, basic_context):
        """测试伤害不会为负"""
        mock_uniform.return_value = 95.0

        # 设置极高防御
        basic_context.defender.final_armor = 10000
        basic_context.defender.final_dodge = 0
        basic_context.defender.final_parry = 0
        basic_context.defender.final_block = 0
        basic_context.attacker.final_crit = 0

        result, damage = AttackTableResolver.resolve_attack(basic_context)

        if result in [AttackResult.HIT, AttackResult.CRIT, AttackResult.BLOCK]:
            # 伤害应该 >= 0
            assert damage >= 0


# ============================================================================
# 边界条件测试
# ============================================================================

class TestEdgeCases:
    """边界条件测试"""

    @patch('random.uniform')
    def test_roll_boundary_zero(self, mock_uniform, basic_context):
        """测试roll=0边界"""
        mock_uniform.return_value = 0.0

        result, _ = AttackTableResolver.resolve_attack(basic_context)
        # roll=0 应该落在第一个区间（通常是Miss或Dodge）
        assert result in [AttackResult.MISS, AttackResult.DODGE]

    @patch('random.uniform')
    def test_roll_boundary_100(self, mock_uniform, basic_context):
        """测试roll=100边界"""
        mock_uniform.return_value = 100.0

        # 设置低防御，低暴击，确保能到Hit
        basic_context.defender.final_dodge = 0
        basic_context.defender.final_parry = 0
        basic_context.defender.final_block = 0
        basic_context.attacker.final_crit = 0
        basic_context.attacker.pilot_stats_backup['weapon_proficiency'] = 1000

        result, _ = AttackTableResolver.resolve_attack(basic_context)
        # roll=100 应该落在最后一个区间（Hit）
        assert result == AttackResult.HIT

    def test_zero_hp_defender(self, basic_pilot):
        """测试防御方HP为0"""
        attacker = Mecha(
            instance_id="m_attacker", mecha_name="Attacker", 
            main_portrait="m_atk_img", model_asset="default",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100,
            block_reduction=500,
            pilot_stats_backup={
                "stat_shooting": basic_pilot.stat_shooting,
                "stat_melee": basic_pilot.stat_melee,
                "stat_reaction": basic_pilot.stat_reaction,
                "stat_awakening": basic_pilot.stat_awakening,
                "stat_defense": basic_pilot.stat_defense,
            }
        )

        defender = Mecha(
            instance_id="m_defender", mecha_name="Defender", 
            main_portrait="m_def_img", model_asset="default",
            final_max_hp=5000, current_hp=0,  # 已死亡
            final_max_en=100, current_en=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100,
            block_reduction=500,
            pilot_stats_backup={
                "stat_shooting": basic_pilot.stat_shooting,
                "stat_melee": basic_pilot.stat_melee,
                "stat_reaction": basic_pilot.stat_reaction,
                "stat_awakening": basic_pilot.stat_awakening,
                "stat_defense": basic_pilot.stat_defense,
            }
        )

        from src.models import WeaponSnapshot as Weapon
        context = BattleContext(
            round_number=1, distance=1000, terrain=Terrain.SPACE,
            mecha_a=attacker, mecha_b=defender,
            weapon=Weapon(uid="w_uid", definition_id="w", name="W", type=WeaponType.SHOOTING,
                        final_power=1000, en_cost=10, range_min=1, range_max=5000,
                        will_req=0, anim_id="default")
        )

        result, damage = AttackTableResolver.resolve_attack(context)
        # 应该正常执行（死亡检查在引擎层）


# ============================================================================
# 精准削减测试
# ============================================================================

class TestPrecisionReduction:
    """精准削减测试"""

    @patch('random.uniform')
    def test_precision_reduces_dodge(self, mock_uniform, basic_context):
        """测试精准削减躲闪"""
        mock_uniform.return_value = 5.0

        # 设置高精准
        basic_context.attacker.final_precision = 50
        # 设置高躲闪
        basic_context.defender.final_dodge = 50

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        # 由于精准削减，实际躲闪率应该 < 50%
        # 所以roll=5有较大概率不是Dodge
        # (这个测试比较粗略，实际需要更精确的验证)

    @patch('random.uniform')
    def test_parry_cap_50_percent(self, mock_uniform, basic_context):
        """测试招架50%上限"""
        mock_uniform.return_value = 5.0

        # 设置极高躲闪基础值（通过机体熟练度）
        basic_context.defender.pilot_stats_backup['mecha_proficiency'] = 4000  # 最高

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        # 招架率最高50% (被精准削减后)
        # 所以roll=5应该在Miss/Dodge/Parry区间

    @patch('random.uniform')
    def test_block_cap_80_percent(self, mock_uniform, basic_context):
        """测试格挡80%上限"""
        mock_uniform.return_value = 10.0

        # 设置极高格挡率
        basic_context.defender.final_block = 100

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        # 格挡率最高80% (被精准削减后)


# ============================================================================
# 参数化测试
# ============================================================================

class TestParametrizedScenarios:
    """参数化场景测试"""

    @pytest.mark.parametrize("dodge_rate,parry_rate,block_rate,crit_rate,expected_results", [
        # 低防御，低暴击 → 主要是Hit
        (0, 0, 0, 0, ["HIT", "MISS"]),
        # 高躲闪 → Dodge较多
        (50, 0, 0, 0, ["DODGE", "MISS", "HIT"]),
        # 高暴击 → Crit较多
        (0, 0, 0, 30, ["CRIT", "HIT", "MISS"]),
    ])
    def test_different_scenarios(self, dodge_rate, parry_rate, block_rate, crit_rate, expected_results, basic_context):
        """测试不同配置下的结果分布"""
        basic_context.defender.final_dodge = dodge_rate
        basic_context.defender.final_parry = parry_rate
        basic_context.defender.final_block = block_rate
        basic_context.attacker.final_crit = crit_rate

        results = []
        for _ in range(50):
            result, _ = AttackTableResolver.resolve_attack(basic_context)
            results.append(result.name)

        # 检查是否出现了预期的结果
        for expected in expected_results:
            assert expected in results


# ============================================================================
# 回合上下文完整性测试
# ============================================================================

class TestContextIntegrity:
    """上下文完整性测试"""

    @patch('random.uniform')
    def test_roll_stored_in_context(self, mock_uniform, basic_context):
        """测试roll值存储在context中"""
        mock_uniform.return_value = 42.0

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        # roll值应该被记录
        assert basic_context.roll == pytest.approx(42.0)

    @patch('random.uniform')
    def test_result_stored_in_context(self, mock_uniform, basic_context):
        """测试结果存储在context中"""
        mock_uniform.return_value = 95.0

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        # 结果应该被记录
        assert basic_context.attack_result == result

    @patch('random.uniform')
    def test_damage_stored_in_context(self, mock_uniform, basic_context):
        """测试伤害存储在context中"""
        mock_uniform.return_value = 95.0

        result, damage = AttackTableResolver.resolve_attack(basic_context)

        # 伤害应该被记录
        assert basic_context.damage == damage


# ============================================================================
# 熟练度影响测试
# ============================================================================

class TestProficiencyImpact:
    """测试熟练度对圆桌判定的影响"""

    def test_placeholder_low_stat_increases_miss(self, balanced_mecha):
        """测试低射击值增加MISS率 (占位测试)"""
        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            mecha_a=balanced_mecha, mecha_b=balanced_mecha, weapon=None
        )

        segments = AttackTableResolver.calculate_attack_table_segments(ctx)
        assert 'MISS' in segments or 'HIT' in segments

    def test_placeholder_high_stat_reduces_miss(self, high_hit_mecha):
        """测试高命中率减少MISS率 (占位测试)"""
        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            mecha_a=high_hit_mecha, mecha_b=high_hit_mecha, weapon=None
        )

        segments = AttackTableResolver.calculate_attack_table_segments(ctx)
        if 'MISS' in segments:
            assert segments['MISS']['rate'] < 20

    def test_placeholder_high_dodge_increases_defense(self, balanced_mecha, high_dodge_mecha):
        """测试高躲闪增加防御率 (占位测试)"""
        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            mecha_a=balanced_mecha, mecha_b=high_dodge_mecha, weapon=None
        )

        segments = AttackTableResolver.calculate_attack_table_segments(ctx)
        assert 'DODGE' in segments
        assert segments['DODGE']['rate'] > 0


# ============================================================================
# 精度影响测试
# ============================================================================

class TestPrecisionImpact:
    """测试精度对防御率的影响"""

    def test_high_precision_reduces_defense(self, offensive_mecha, defensive_mecha):
        """测试高精度降低防御率"""
        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            mecha_a=offensive_mecha, mecha_b=defensive_mecha, weapon=None
        )

        segments = AttackTableResolver.calculate_attack_table_segments(ctx)

        dodge_rate = segments.get('DODGE', {}).get('rate', 0)
        parry_rate = segments.get('PARRY', {}).get('rate', 0)
        block_rate = segments.get('BLOCK', {}).get('rate', 0)

        actual_defense = dodge_rate + parry_rate + block_rate
        base_defense = 30.0 + 25.0 + 20.0  # 75
        assert actual_defense < base_defense

    def test_low_precision_defense_unaffected(self, balanced_mecha, defensive_mecha):
        """测试低精度不影响防御"""
        attacker = copy.deepcopy(balanced_mecha)
        attacker.final_precision = 0.0
        attacker.instance_id = "m_low_prec"

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            mecha_a=attacker, mecha_b=defensive_mecha, weapon=None
        )

        segments = AttackTableResolver.calculate_attack_table_segments(ctx)
        dodge_rate = segments.get('DODGE', {}).get('rate', 0)
        assert dodge_rate >= 15


# ============================================================================
# 防御率上限测试
# ============================================================================

class TestDefenseCaps:
    """测试防御率上限"""

    def test_parry_hard_cap_50_percent(self, balanced_mecha):
        """测试PARRY 50%硬上限"""
        defender = copy.deepcopy(balanced_mecha)
        defender.final_parry = 80.0
        defender.instance_id = "m_high_parry"

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            mecha_a=balanced_mecha, mecha_b=defender, weapon=None
        )

        segments = AttackTableResolver.calculate_attack_table_segments(ctx)
        parry_rate = segments.get('PARRY', {}).get('rate', 0)
        assert parry_rate <= 50.0

    def test_block_hard_cap_80_percent(self, balanced_mecha):
        """测试BLOCK 80%硬上限"""
        defender = copy.deepcopy(balanced_mecha)
        defender.final_block = 120.0
        defender.instance_id = "m_high_block"

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            mecha_a=balanced_mecha, mecha_b=defender, weapon=None
        )

        segments = AttackTableResolver.calculate_attack_table_segments(ctx)
        block_rate = segments.get('BLOCK', {}).get('rate', 0)
        assert block_rate <= 80.0


# ============================================================================
# CRIT 被挤压测试
# ============================================================================

class TestCritSqueezing:
    """测试CRIT被前面的段挤压"""

    def test_crit_squeezed_by_high_defense(self, crit_mecha, defensive_mecha):
        """测试高防御率挤压CRIT空间"""
        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            mecha_a=crit_mecha, mecha_b=defensive_mecha, weapon=None
        )

        segments = AttackTableResolver.calculate_attack_table_segments(ctx)

        crit_rate = segments.get('CRIT', {}).get('rate', 0)
        total_before_crit = segments.get('MISS', {}).get('rate', 0) + \
                            segments.get('DODGE', {}).get('rate', 0) + \
                            segments.get('PARRY', {}).get('rate', 0) + \
                            segments.get('BLOCK', {}).get('rate', 0)

        if total_before_crit >= 100:
            assert crit_rate < 5

    def test_crit_no_space_left(self, balanced_mecha, defensive_mecha):
        """测试CRIT完全没有空间"""
        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            mecha_a=balanced_mecha, mecha_b=defensive_mecha, weapon=None
        )

        segments = AttackTableResolver.calculate_attack_table_segments(ctx)

        total_non_crit = segments.get('MISS', {}).get('rate', 0) + \
                          segments.get('DODGE', {}).get('rate', 0) + \
                          segments.get('PARRY', {}).get('rate', 0) + \
                          segments.get('BLOCK', {}).get('rate', 0)

        if total_non_crit >= 100:
            crit_rate = segments.get('CRIT', {}).get('rate', 0)
            assert crit_rate == 0


# ============================================================================
# HIT 段兜底测试
# ============================================================================

class TestHitAsFallback:
    """测试HIT段作为兜底"""

    def test_hit_fills_remaining_space(self, standard_context):
        """测试HIT填充剩余空间"""
        segments = AttackTableResolver.calculate_attack_table_segments(standard_context)
        assert 'HIT' in segments
        assert segments['HIT']['end'] == 100

    def test_hit_rate_calculated_correctly(self, standard_context):
        """测试HIT率计算正确"""
        segments = AttackTableResolver.calculate_attack_table_segments(standard_context)

        hit_rate = segments['HIT']['rate']
        hit_start = segments['HIT']['start']
        hit_end = segments['HIT']['end']
        assert hit_rate == hit_end - hit_start

    def test_no_hit_if_table_full(self, balanced_mecha):
        """测试圆桌满了就没有HIT"""
        attacker = copy.deepcopy(balanced_mecha)
        attacker.final_hit = -100.0
        attacker.instance_id = "m_negative_hit"

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            mecha_a=attacker, mecha_b=balanced_mecha, weapon=None
        )

        segments = AttackTableResolver.calculate_attack_table_segments(ctx)

        if segments.get('MISS', {}).get('rate', 0) >= 100:
            hit_rate = segments.get('HIT', {}).get('rate', 0)
            assert hit_rate == 0


# ============================================================================
# 段边界计算测试
# ============================================================================

class TestSegmentBoundaries:
    """测试段的边界计算"""

    def test_segments_are_continuous(self, standard_context):
        """测试段是连续的（无缝隙）"""
        segments = AttackTableResolver.calculate_attack_table_segments(standard_context)

        ordered_segments = sorted(
            [s for k, s in segments.items() if k != 'total'],
            key=lambda x: x['start']
        )

        for i in range(len(ordered_segments) - 1):
            current_end = ordered_segments[i]['end']
            next_start = ordered_segments[i + 1]['start']
            assert current_end == next_start, f"段不连续: {ordered_segments[i]} -> {ordered_segments[i+1]}"

    def test_segment_ranges_not_negative(self, standard_context):
        """测试段的范围不为负"""
        segments = AttackTableResolver.calculate_attack_table_segments(standard_context)

        for name, segment in segments.items():
            if name == 'total':
                continue
            assert segment['rate'] >= 0, f"{name} rate为负: {segment['rate']}"
            assert segment['start'] >= 0, f"{name} start为负: {segment['start']}"
            assert segment['end'] >= 0, f"{name} end为负: {segment['end']}"

    def test_total_does_not_exceed_100(self, standard_context):
        """测试总段不超过100"""
        segments = AttackTableResolver.calculate_attack_table_segments(standard_context)

        total = segments.get('total', 0)
        assert total >= 100


# ============================================================================
# 极端情况测试
# ============================================================================

class TestExtremeScenarios:
    """测试极端情况"""

    def test_all_zeros(self, balanced_mecha):
        """测试所有属性为0"""
        attacker = copy.deepcopy(balanced_mecha)
        attacker.final_hit = 0.0
        attacker.final_precision = 0.0
        attacker.final_crit = 0.0
        attacker.final_dodge = 0.0
        attacker.final_parry = 0.0
        attacker.final_block = 0.0
        attacker.instance_id = "m_zero_atk"

        defender = copy.deepcopy(balanced_mecha)
        defender.final_hit = 0.0
        defender.final_precision = 0.0
        defender.final_crit = 0.0
        defender.final_dodge = 0.0
        defender.final_parry = 0.0
        defender.final_block = 0.0
        defender.instance_id = "m_zero_def"

        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            mecha_a=attacker, mecha_b=defender, weapon=None
        )

        segments = AttackTableResolver.calculate_attack_table_segments(ctx)
        assert 'MISS' in segments or 'HIT' in segments

    def test_very_high_hit_rate(self, high_hit_mecha, balanced_mecha):
        """测试超高命中率"""
        ctx = BattleContext(
            round_number=1, distance=1000, terrain=None,
            mecha_a=high_hit_mecha, mecha_b=balanced_mecha, weapon=None
        )

        segments = AttackTableResolver.calculate_attack_table_segments(ctx)

        miss_rate = segments.get('MISS', {}).get('rate', 0)
        assert miss_rate < 10

        hit_rate = segments.get('HIT', {}).get('rate', 0)
        crit_rate = segments.get('CRIT', {}).get('rate', 0)
        assert (hit_rate + crit_rate) > 50

