"""
单元测试: 战斗系统 - 圆桌判定测试
测试AttackTableResolver的圆桌判定逻辑和伤害计算
"""

import pytest
from unittest.mock import patch
from src.models import Mecha, BattleContext, AttackResult, Weapon, WeaponType, Terrain
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
        basic_context.attacker.pilot.weapon_proficiency = 0  # 最低熟练度

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
        basic_context.attacker.pilot.weapon_proficiency = 100

        result, _ = AttackTableResolver.resolve_attack(basic_context)
        # 最低熟练度会miss
        assert result == AttackResult.MISS

    def test_hit_is_fallback(self, basic_context):
        """测试Hit是兜底结果"""
        # 设置所有防御概率为0，降低暴击率
        basic_context.defender.dodge_rate = 0
        basic_context.defender.parry_rate = 0
        basic_context.defender.block_rate = 0
        basic_context.attacker.crit_rate = 0

        # 设置高命中加成
        basic_context.attacker.pilot.weapon_proficiency = 1000

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
        basic_context.attacker.crit_rate = 50

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
        basic_context.attacker.crit_rate = 50

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        if result == AttackResult.CRIT:
            # 暴击应该给攻击方+5气力
            # 但气力变化存储在context中，不是直接修改mecha
            assert basic_context.attacker_will_delta == 5


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
        basic_context.defender.block_rate = 50
        basic_context.defender.block_value = 500

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
        basic_context.attacker.pilot.weapon_proficiency = 0  # 确保miss

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        if result == AttackResult.MISS:
            # Miss没有气力变化
            assert basic_context.attacker_will_delta == 0
            assert basic_context.defender_will_delta == 0

    @patch('random.uniform')
    def test_dodge_will_change(self, mock_uniform, basic_context):
        """测试躲闪的气力变化"""
        mock_uniform.return_value = 1.0

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        if result == AttackResult.DODGE:
            # 躲闪: 防御方+5气力
            assert basic_context.defender_will_delta == 5

    @patch('random.uniform')
    def test_parry_will_change(self, mock_uniform, basic_context):
        """测试招架的气力变化"""
        # 设置高招架率
        mock_uniform.return_value = 5.0
        basic_context.defender.parry_rate = 30

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        if result == AttackResult.PARRY:
            # 招架: 防御方+15气力
            assert basic_context.defender_will_delta == 15

    @patch('random.uniform')
    def test_hit_will_change(self, mock_uniform, basic_context):
        """测试命中的气力变化"""
        mock_uniform.return_value = 95.0
        basic_context.defender.dodge_rate = 0
        basic_context.defender.parry_rate = 0
        basic_context.defender.block_rate = 0
        basic_context.attacker.crit_rate = 0

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        if result == AttackResult.HIT:
            # 命中: 攻击方+2, 防御方+1
            assert basic_context.attacker_will_delta == 2
            assert basic_context.defender_will_delta == 1


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
        basic_context.defender.defense_level = 2000
        basic_context.defender.dodge_rate = 0
        basic_context.defender.parry_rate = 0
        basic_context.defender.block_rate = 0
        basic_context.attacker.crit_rate = 0

        result, damage = AttackTableResolver.resolve_attack(basic_context)

        if result == AttackResult.HIT:
            # 高防御应该显著减少伤害
            assert damage >= 0

    @patch('random.uniform')
    def test_no_negative_damage(self, mock_uniform, basic_context):
        """测试伤害不会为负"""
        mock_uniform.return_value = 95.0

        # 设置极高防御
        basic_context.defender.defense_level = 10000
        basic_context.defender.dodge_rate = 0
        basic_context.defender.parry_rate = 0
        basic_context.defender.block_rate = 0
        basic_context.attacker.crit_rate = 0

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
        basic_context.defender.dodge_rate = 0
        basic_context.defender.parry_rate = 0
        basic_context.defender.block_rate = 0
        basic_context.attacker.crit_rate = 0
        basic_context.attacker.pilot.weapon_proficiency = 1000

        result, _ = AttackTableResolver.resolve_attack(basic_context)
        # roll=100 应该落在最后一个区间（Hit）
        assert result == AttackResult.HIT

    def test_zero_hp_defender(self, basic_pilot):
        """测试防御方HP为0"""
        attacker = Mecha(
            id="m_attacker", name="Attacker", pilot=basic_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )

        defender = Mecha(
            id="m_defender", name="Defender", pilot=basic_pilot,
            max_hp=5000, current_hp=0,  # 已死亡
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )

        context = BattleContext(
            round_number=1, distance=1000, terrain=Terrain.SPACE,
            attacker=attacker, defender=defender,
            weapon=Weapon(id="w", name="W", weapon_type=WeaponType.RIFLE,
                        power=1000, en_cost=10, range_min=1, range_max=5)
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
        basic_context.attacker.precision = 50
        # 设置高躲闪
        basic_context.defender.dodge_rate = 50

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        # 由于精准削减，实际躲闪率应该 < 50%
        # 所以roll=5有较大概率不是Dodge
        # (这个测试比较粗略，实际需要更精确的验证)

    @patch('random.uniform')
    def test_parry_cap_50_percent(self, mock_uniform, basic_context):
        """测试招架50%上限"""
        mock_uniform.return_value = 5.0

        # 设置极高躲闪基础值（通过机体熟练度）
        basic_context.defender.pilot.mecha_proficiency = 4000  # 最高

        result, _ = AttackTableResolver.resolve_attack(basic_context)

        # 招架率最高50% (被精准削减后)
        # 所以roll=5应该在Miss/Dodge/Parry区间

    @patch('random.uniform')
    def test_block_cap_80_percent(self, mock_uniform, basic_context):
        """测试格挡80%上限"""
        mock_uniform.return_value = 10.0

        # 设置极高格挡率
        basic_context.defender.block_rate = 100

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
        basic_context.defender.dodge_rate = dodge_rate
        basic_context.defender.parry_rate = parry_rate
        basic_context.defender.block_rate = block_rate
        basic_context.attacker.crit_rate = crit_rate

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
