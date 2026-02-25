"""
战斗统计收集器
====================
功能：从 RawAttackEvent 事件流中收集战斗统计数据
设计原则：
  - 事件驱动：只订阅事件，不干预战斗流程
  - 解耦设计：不依赖 BattleSimulator 的具体实现
  - 数据完整性：支持攻击判定、伤害分布、技能触发等多维度统计
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from collections import Counter, defaultdict
from ..models import AttackResult
from ..presentation.models import RawAttackEvent


@dataclass
class AttackRecord:
    """单次攻击记录（用于详细分析）"""
    round_number: int
    attacker_id: str
    defender_id: str
    attacker_name: str
    defender_name: str
    weapon_name: str
    weapon_type: str
    attack_result: AttackResult
    damage: int
    roll_value: float
    distance: int
    attacker_will_delta: int
    defender_will_delta: int
    triggered_skills: List[str]
    is_first_attack: bool
    # 攻击后的状态快照
    attacker_hp_after: int = 0
    attacker_en_after: int = 0
    attacker_will_after: int = 0
    defender_hp_after: int = 0
    defender_en_after: int = 0
    defender_will_after: int = 0


@dataclass
class RoundSnapshot:
    """回合结束时的状态快照"""
    round_number: int
    distance: int
    first_mover: str
    initiative_reason: str
    mecha_a_hp: int
    mecha_a_en: int
    mecha_a_will: int
    mecha_b_hp: int
    mecha_b_en: int
    mecha_b_will: int


@dataclass
class BattleStatistics:
    """单场战斗统计数据"""
    battle_id: int = 0
    rounds: int = 0
    winner: str = ""
    end_reason: str = ""

    # 伤害统计
    total_damage_dealt: int = 0
    total_damage_taken: int = 0
    max_single_damage: int = 0
    min_single_damage: float = float('inf')
    damage_distribution: List[int] = field(default_factory=list)

    # 攻击判定统计
    attack_results: Counter = field(default_factory=Counter)
    challenger_attack_results: Counter = field(default_factory=Counter)
    boss_attack_results: Counter = field(default_factory=Counter)

    # 资源统计
    total_en_consumed: int = 0
    total_en_regened: int = 0

    # 气力变化记录
    will_changes: List[tuple] = field(default_factory=list)

    # 技能统计
    skills_applied: List[str] = field(default_factory=list)
    skill_trigger_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # 详细记录（用于深度分析）
    attack_records: List[AttackRecord] = field(default_factory=list)
    round_snapshots: List[RoundSnapshot] = field(default_factory=list)

    def finalize(self):
        """ finalize statistics for reporting"""
        if self.min_single_damage == float('inf'):
            self.min_single_damage = 0


class StatisticsCollector:
    """战斗统计收集器 - 事件驱动架构

    设计理念：
    1. 单一职责：只负责收集统计，不干预战斗逻辑
    2. 事件订阅：通过 on_attack_event() 接收事件，与战斗引擎解耦
    3. 数据完整：从 RawAttackEvent 提取所有需要的统计信息
    4. 灵活配置：支持按需启用/禁用详细记录
    """

    def __init__(
        self,
        battle_id: int = 0,
        mecha_a_id: str = "",
        mecha_b_id: str = "",
        enable_detailed_records: bool = False
    ):
        """初始化统计收集器

        Args:
            battle_id: 战斗ID（用于多场战斗批量测试）
            mecha_a_id: A方机体ID（用于区分攻击方向）
            mecha_b_id: B方机体ID
            enable_detailed_records: 是否记录详细的攻击记录（内存消耗较大）
        """
        self.battle_id = battle_id
        self.mecha_a_id = mecha_a_id
        self.mecha_b_id = mecha_b_id
        self.enable_detailed_records = enable_detailed_records

        self.stats = BattleStatistics(battle_id=battle_id)
        self._roll_value = 0.0  # 临时存储当前 attack 的 roll 值

    def set_round_context(
        self,
        round_number: int,
        distance: int,
        first_mover: str,
        initiative_reason: str
    ):
        """设置回合上下文（用于记录回合级别的统计）

        这个方法应该在回合开始时调用，以便收集器知道当前的回合信息。
        """
        self._current_round = round_number
        self._current_distance = distance
        self._current_first_mover = first_mover
        self._current_initiative_reason = initiative_reason

    def set_roll_value(self, roll_value: float):
        """设置当前攻击的 Roll 值

        由于 RawAttackEvent 可能不包含 roll_value，需要通过这个方法从外部传入。
        """
        self._roll_value = roll_value

    def on_attack_event(self, event: RawAttackEvent):
        """处理原始攻击事件（核心接口）

        这是 StatisticsCollector 的主入口，每次攻击发生时应该调用这个方法。

        Args:
            event: RawAttackEvent - 包含攻击的完整数据
        """
        # 1. 基础统计更新
        # AttackResult 继承自 str，所以可以用值来构造枚举
        result = AttackResult(event.attack_result)

        # 更新攻击判定计数
        self.stats.attack_results[result.name] += 1

        # 区分攻击方向
        is_challenger = (event.attacker_id == self.mecha_a_id)
        is_boss = (event.attacker_id == self.mecha_b_id)

        if is_challenger:
            self.stats.challenger_attack_results[result.name] += 1
            self.stats.damage_distribution.append(event.damage)
            self.stats.total_damage_dealt += event.damage
        elif is_boss:
            self.stats.boss_attack_results[result.name] += 1
            self.stats.total_damage_taken += event.damage

        # 更新伤害极值
        if event.damage > 0:
            self.stats.max_single_damage = max(self.stats.max_single_damage, event.damage)
            self.stats.min_single_damage = min(self.stats.min_single_damage, event.damage)

        # 2. 技能触发统计
        if event.triggered_skills:
            for skill_id in event.triggered_skills:
                if skill_id not in self.stats.skill_trigger_stats:
                    self.stats.skill_trigger_stats[skill_id] = {
                        "attempts": 0,
                        "success": 0
                    }
                self.stats.skill_trigger_stats[skill_id]["success"] += 1

        # 3. 详细记录（可选）
        if self.enable_detailed_records:
            record = AttackRecord(
                round_number=event.round_number,
                attacker_id=event.attacker_id,
                defender_id=event.defender_id,
                attacker_name=event.attacker_name,
                defender_name=event.defender_name,
                weapon_name=event.weapon_name,
                weapon_type=event.weapon_type,
                attack_result=result,
                damage=event.damage,
                roll_value=self._roll_value,
                distance=event.distance,
                attacker_will_delta=event.attacker_will_delta,
                defender_will_delta=event.defender_will_delta,
                triggered_skills=event.triggered_skills.copy(),
                is_first_attack=event.is_first_attack
            )
            self.stats.attack_records.append(record)

    def on_en_consumed(self, amount: int):
        """记录 EN 消耗"""
        self.stats.total_en_consumed += amount

    def on_en_regened(self, amount: int):
        """记录 EN 回复"""
        self.stats.total_en_regened += amount

    def on_will_changed(self, round_number: int, will_value: int):
        """记录气力变化（mecha_a 的气力变化）"""
        self.stats.will_changes.append((round_number, will_value))

    def on_round_end(
        self,
        mecha_a_hp: int, mecha_a_en: int, mecha_a_will: int,
        mecha_b_hp: int, mecha_b_en: int, mecha_b_will: int
    ):
        """记录回合结束时的状态快照"""
        snapshot = RoundSnapshot(
            round_number=self._current_round,
            distance=self._current_distance,
            first_mover=self._current_first_mover,
            initiative_reason=self._current_initiative_reason,
            mecha_a_hp=mecha_a_hp,
            mecha_a_en=mecha_a_en,
            mecha_a_will=mecha_a_will,
            mecha_b_hp=mecha_b_hp,
            mecha_b_en=mecha_b_en,
            mecha_b_will=mecha_b_will
        )
        self.stats.round_snapshots.append(snapshot)

    def finalize_battle(
        self,
        rounds: int,
        winner: str,
        end_reason: str
    ) -> BattleStatistics:
        """结算战斗统计

        Args:
            rounds: 战斗回合数
            winner: 获胜方名称
            end_reason: 结束原因

        Returns:
            BattleStatistics: 完整的战斗统计数据
        """
        self.stats.rounds = rounds
        self.stats.winner = winner
        self.stats.end_reason = end_reason
        self.stats.finalize()
        return self.stats

    def get_statistics(self) -> BattleStatistics:
        """获取当前统计数据（不结算）"""
        return self.stats

    def reset(self):
        """重置统计收集器（用于复用实例）"""
        self.stats = BattleStatistics(battle_id=self.battle_id)
        self._roll_value = 0.0
