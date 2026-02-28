"""
攻击事件构建器 - 将战斗引擎的计算结果打包为 RawAttackEvent

职责说明：
  AttackEventBuilder 是战斗引擎（engine.py）和演出系统之间的"适配层"。
  引擎只需要传入机体快照、武器、上下文和判定结果等纯战斗数据，
  Builder 负责将其组装成 RawAttackEvent，引擎本身无需感知表现层的数据结构。

  这样做的好处：
  - 引擎和表现层之间的耦合大幅降低，为将来调整任意一侧提供空间。
  - RawAttackEvent 的构造逻辑集中在一处，消除了 engine.py 中的代码重复。
"""

from __future__ import annotations
from typing import TYPE_CHECKING, List

from .models import RawAttackEvent

if TYPE_CHECKING:
    # 避免循环导入：TYPE_CHECKING 块只在类型检查时导入
    from ..models import MechaSnapshot, WeaponSnapshot, BattleContext, AttackResult


class AttackEventBuilder:
    """
    static factory: 将战斗引擎的输出构建为 RawAttackEvent。

    使用示例（在 engine._execute_attack 中）：
        raw_event = AttackEventBuilder.build(
            attacker=attacker,
            defender=defender,
            weapon=weapon,
            ctx=ctx,
            result=result,
            damage=damage,
            triggered_skill_ids=triggered_skill_ids,
            is_first=is_first,
            round_number=self.round_number,
            en_cost=int(weapon_cost),
        )
    """

    @staticmethod
    def build(
        attacker: "MechaSnapshot",
        defender: "MechaSnapshot",
        weapon: "WeaponSnapshot",
        ctx: "BattleContext",
        result: "AttackResult",
        damage: int,
        triggered_skill_ids: List[str],
        is_first: bool,
        round_number: int,
        en_cost: int,
    ) -> RawAttackEvent:
        """
        构建 RawAttackEvent。

        Args:
            attacker:             攻击方机体快照（包含攻击后的最新状态）
            defender:             防御方机体快照（包含受击后的最新状态）
            weapon:               本次使用的武器快照
            ctx:                  战场上下文（包含 roll 值、气力变化等）
            result:               判定结果（AttackResult 枚举）
            damage:               最终伤害数值
            triggered_skill_ids:  本次攻击期间触发的技能 ID 列表
            is_first:             是否为本回合第一次攻击（先手方）
            round_number:         当前回合数
            en_cost:              本次武器消耗的 EN 量

        Returns:
            RawAttackEvent: 可供 EventMapper 直接消费的原始攻击事件
        """
        return RawAttackEvent(
            # ── 基本信息 ──────────────────────────────────────────────
            round_number=round_number,
            attacker_id=attacker.id,
            defender_id=defender.id,
            attacker_name=attacker.name,
            defender_name=defender.name,

            # ── 武器信息 ──────────────────────────────────────────────
            weapon_id=weapon.id,
            weapon_name=weapon.name,
            weapon_type=weapon.type.value,
            weapon_tags=getattr(weapon, 'tags', []),

            # ── 判定结果 ──────────────────────────────────────────────
            attack_result=result.value,
            damage=damage,

            # ── 战场状态 ──────────────────────────────────────────────
            distance=ctx.distance,
            attacker_will_delta=ctx.current_attacker_will_delta,
            defender_will_delta=ctx.current_defender_will_delta,

            # ── 技能触发 ──────────────────────────────────────────────
            triggered_skills=triggered_skill_ids,

            # ── 标记 ──────────────────────────────────────────────────
            is_first_attack=is_first,
            initiative_holder="",  # 由外层控制器填写（如需要）

            # ── 统计扩展字段 ─────────────────────────────────────────
            roll_value=ctx.roll,
            en_cost=en_cost,

            # ── 攻击后状态快照（用于 HP 分级 / 统计分析） ────────────
            attacker_hp_after=attacker.current_hp,
            attacker_en_after=attacker.current_en,
            attacker_will_after=attacker.current_will,
            defender_hp_after=defender.current_hp,
            defender_en_after=defender.current_en,
            defender_will_after=defender.current_will,
            defender_max_hp=defender.final_max_hp,
        )
