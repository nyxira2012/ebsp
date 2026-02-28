import os
import sys
import argparse
import json
import io
import collections
import math
import random
from typing import List, Dict, Any, Optional, Callable

# 确保项目根目录在路径中
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Windows UTF-8 支持
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 核心系统引用
from src.loader import DataLoader
from src.factory import MechaFactory
from src.combat.engine import BattleSimulator, WeaponSelector
from src.presentation.models import RawAttackEvent, PresentationAttackEvent
from src.presentation.constants import TemplateTier
from src.models import Mecha, Weapon, WeaponType, AttackResult, InitiativeReason, BattleContext, WeaponSnapshot
from src.skills import SkillRegistry
from src.combat.resolver import AttackTableResolver
from src.combat.calculator import CombatCalculator
from src.presentation.event_builder import AttackEventBuilder
from src.presentation import EventMapper, TextRenderer
from src.presentation.models import PresentationRoundEvent, PresentationAttackSequence
from src.skill_system.event_manager import EventManager

# ============================================================================
# 自定义战斗模拟器 - 支持自定义输出格式
# ============================================================================

class CustomBattleSimulator(BattleSimulator):
    """自定义战斗模拟器，支持自定义输出格式"""

    def __init__(self, mecha_a: Mecha, mecha_b: Mecha, verbose: bool = True):
        # 调用父类初始化，但不启用verbose输出
        super().__init__(mecha_a, mecha_b, enable_presentation=True, verbose=False)
        self.custom_verbose = verbose
        self.presenter = CombatTextPresenter()

    def run_battle(self) -> None:
        """运行完整的战斗流程"""
        if self.custom_verbose:
            print("=" * 80)
            print(f"战斗开始: {self.mecha_a.name} vs {self.mecha_b.name}")
            print("=" * 80)
            print()

        # 计算回合上限
        from src.config import Config
        max_rounds = SkillRegistry.process_hook("HOOK_MAX_ROUNDS", Config.MAX_ROUNDS,
                                              BattleContext(round_number=0, distance=0, mecha_a=self.mecha_a, mecha_b=self.mecha_b, event_manager=self._event_manager))

        while True:
            # 状态检查
            if not self.mecha_a.is_alive() or not self.mecha_b.is_alive():
                break

            # 回合上限检查
            if self.round_number >= max_rounds:
                ctx = BattleContext(round_number=self.round_number, distance=0, mecha_a=self.mecha_a, mecha_b=self.mecha_b, event_manager=self._event_manager)
                should_maintain = SkillRegistry.process_hook("HOOK_CHECK_MAINTAIN_BATTLE", False, ctx)
                if not should_maintain:
                    break

            self.round_number += 1
            self._execute_round_custom()

        # 战斗结束
        final_ctx = BattleContext(round_number=self.round_number, distance=0, mecha_a=self.mecha_a, mecha_b=self.mecha_b, event_manager=self._event_manager)
        SkillRegistry.process_hook("HOOK_ON_BATTLE_END", None, final_ctx)

        # 结算
        self._conclude_battle_custom()

    def _execute_round_custom(self) -> None:
        """执行单个回合（自定义输出格式）"""
        if self.custom_verbose:
            print(f"{'=' * 80}")
            print(f"ROUND {self.round_number}")
            print(f"{'=' * 80}")

        # 生成距离
        distance = self.distance_provider(self.round_number) if self.distance_provider else self._generate_distance()

        if self.custom_verbose:
            print(f"交战距离: {distance}m")

        # 先手判定
        first_mover, second_mover, reason = self.initiative_calc.calculate_initiative(
            self.mecha_a, self.mecha_b, self.round_number, self._event_manager
        )

        if self.custom_verbose:
            print(f"先手方: {first_mover.name} ({reason.value})")
            print()

        # 清空当前回合的输出缓冲
        self.presenter.clear()

        # 先攻方攻击
        pres_events_first = self._execute_attack_custom(first_mover, second_mover, distance, is_first=True)
        if pres_events_first:
            for evt in pres_events_first:
                self.presenter.present_presentation(evt)

        # 检查后攻方存活
        if not second_mover.is_alive():
            self.presenter.present_death(second_mover, first_mover, self._last_result)
            print(self.presenter.flush())
            return

        # 后攻方反击
        pres_events_second = self._execute_attack_custom(second_mover, first_mover, distance, is_first=False)
        if pres_events_second:
            for evt in pres_events_second:
                self.presenter.present_presentation(evt)

        # 检查先攻方存活
        if not first_mover.is_alive():
            self.presenter.present_death(first_mover, second_mover, self._last_result)
            print(self.presenter.flush())
            return

        # 回合结束处理
        self.mecha_a.modify_will(1)
        self.mecha_b.modify_will(1)
        self._apply_en_regeneration(self.mecha_a)
        self._apply_en_regeneration(self.mecha_b)

        ctx = BattleContext(round_number=self.round_number, distance=distance, mecha_a=self.mecha_a, mecha_b=self.mecha_b, event_manager=self._event_manager)
        SkillRegistry.process_hook("HOOK_ON_TURN_END", None, ctx)
        from src.skills import EffectManager
        EffectManager.tick_effects(self.mecha_a)
        EffectManager.tick_effects(self.mecha_b)

        if self.enable_presentation and self.mapper:
            self.mapper.advance_turn()

        # 显示机体状态
        self.presenter.present_status(self.mecha_a, self.mecha_b)
        print(self.presenter.flush())

    def _execute_attack_custom(
        self,
        attacker: Mecha,
        defender: Mecha,
        distance: int,
        is_first: bool
    ) -> Optional[List[PresentationAttackEvent]]:
        """执行单次攻击（自定义输出格式）"""
        self._event_manager.begin_attack()

        # 选择武器
        weapon = WeaponSelector.select_best_weapon(attacker, distance)

        # 显示攻击动作（系统信息）
        if self.custom_verbose:
            self.presenter.present_attack(attacker.name, weapon.name, is_counter=not is_first,
                                         power=weapon.power, en_cost=weapon.en_cost)

        # 创建上下文
        ctx = BattleContext(
            round_number=self.round_number,
            distance=distance,
            mecha_a=attacker,
            mecha_b=defender,
            weapon=weapon,
            event_manager=self._event_manager
        )

        # 计算EN消耗
        weapon_cost = float(weapon.en_cost)
        weapon_cost = SkillRegistry.process_hook("HOOK_PRE_EN_COST_MULT", weapon_cost, ctx)

        if attacker.current_en < int(weapon_cost):
            self.presenter.present_status(attacker, defender)
            print(self.presenter.flush())
            self._event_manager.end_attack()
            return None

        attacker.consume_en(int(weapon_cost))

        # 圆桌判定
        result, damage = AttackTableResolver.resolve_attack(ctx)

        # 应用伤害和气力
        if damage > 0:
            defender.take_damage(damage)

        self._last_result = result  # 保存结果用于死亡信息

        if ctx.current_attacker_will_delta != 0:
            attacker.modify_will(ctx.current_attacker_will_delta)
        if ctx.current_defender_will_delta != 0:
            defender.modify_will(ctx.current_defender_will_delta)

        # 显示判定结果（系统信息）
        if self.custom_verbose:
            self.presenter.present_result(
                result, ctx.roll, damage,
                ctx.current_attacker_will_delta, ctx.current_defender_will_delta,
                attacker.name, defender.name,
                defender.current_hp, defender.final_max_hp
            )

        # 结算钩子
        if damage > 0:
            SkillRegistry.process_hook("HOOK_ON_DAMAGE_DEALT", damage, ctx)

        if not defender.is_alive():
            SkillRegistry.process_hook("HOOK_ON_KILL", None, ctx)

        SkillRegistry.process_hook("HOOK_ON_ATTACK_END", None, ctx)

        # 构建攻击事件
        attack_events = self._event_manager.end_attack()
        triggered_skill_ids = [e.skill_id for e in attack_events]

        SPIRIT_COMMAND_IDS = {"hot_blood", "soul", "flash", "trust", "hope", "focus", "effort"}
        spirit_commands = [sid for sid in triggered_skill_ids if sid in SPIRIT_COMMAND_IDS]

        raw_event = AttackEventBuilder.build(
            attacker=attacker,
            defender=defender,
            weapon=weapon,
            ctx=ctx,
            result=result,
            damage=damage,
            triggered_skill_ids=triggered_skill_ids,
            spirit_commands=spirit_commands,
            is_first=is_first,
            round_number=self.round_number,
            en_cost=int(weapon_cost),
        )

        # 通知统计监听器
        for listener in self._attack_event_listeners:
            listener(raw_event)

        # 生成演出事件
        if self.enable_presentation and self.mapper:
            pres_events_list = self.mapper.map_attack(raw_event)

            # 构建回合事件
            if not self.presentation_timeline or self.presentation_timeline[-1].round_number != self.round_number:
                round_evt = PresentationRoundEvent(round_number=self.round_number)
                self.presentation_timeline.append(round_evt)

            current_round_evt = self.presentation_timeline[-1]

            seq = PresentationAttackSequence(
                attacker_id=attacker.id,
                defender_id=defender.id,
                events=pres_events_list
            )
            current_round_evt.attack_sequences.append(seq)

            for listener in self._presentation_event_listeners:
                listener(pres_events_list)

            return pres_events_list

        return None

    def _conclude_battle_custom(self) -> None:
        """战斗结算"""
        if self.custom_verbose:
            print()
            print("=" * 80)
            print("战斗结束")
            print("=" * 80)

        if not self.mecha_a.is_alive():
            if self.custom_verbose:
                print(f"胜者: {self.mecha_b.name} (击破)")
        elif not self.mecha_b.is_alive():
            if self.custom_verbose:
                print(f"胜者: {self.mecha_a.name} (击破)")
        else:
            # 判定胜
            from src.config import Config
            a_pct = self.mecha_a.get_hp_percentage()
            b_pct = self.mecha_b.get_hp_percentage()

            if a_pct > b_pct:
                if self.custom_verbose:
                    print(f"胜者: {self.mecha_a.name} (判定胜)")
            elif b_pct > a_pct:
                if self.custom_verbose:
                    print(f"胜者: {self.mecha_b.name} (判定胜)")
            else:
                if self.custom_verbose:
                    print("平局")


# ============================================================================
# 演出处理器
# ============================================================================

class CombatTextPresenter:
    """负责将演出事件格式化为可读文本，并组织输出布局"""
    def __init__(self):
        self.action_lines = []
        self.reaction_lines = []

    def present_attack(self, attacker: str, weapon: str, is_counter: bool = False, power: int = 0, en_cost: int = 0):
        """格式化攻击动作（系统信息，在线上）"""
        role = "反击" if is_counter else "先攻"
        self.action_lines.append(f"[{role}] {attacker} 使用 【{weapon}】 (威力:{power}, EN消耗:{en_cost})")

    def present_result(self, result: AttackResult, roll: float, damage: int,
                      attacker_will_delta: int, defender_will_delta: int,
                      attacker_name: str, defender_name: str,
                      defender_hp: int = None, defender_max_hp: int = None):
        """格式化判定结果（系统信息，在线上）"""
        result_symbols = {
            AttackResult.CRIT: "★",
            AttackResult.HIT: "✓",
            AttackResult.BLOCK: "▌",
            AttackResult.PARRY: "◇",
            AttackResult.DODGE: "✗",
            AttackResult.MISS: "✗"
        }
        symbol = result_symbols.get(result, "?")
        result_name = {
            AttackResult.CRIT: "暴击",
            AttackResult.HIT: "命中",
            AttackResult.BLOCK: "格挡",
            AttackResult.PARRY: "招架",
            AttackResult.DODGE: "躲闪",
            AttackResult.MISS: "未命中"
        }.get(result, "未知")

        hp_info = ""
        if defender_hp is not None and defender_max_hp is not None and result not in (AttackResult.MISS, AttackResult.DODGE):
            hp_info = f" | 剩余: {defender_hp}/{defender_max_hp}"

        self.action_lines.append(
            f"   {symbol} {result_name}! Roll点: {roll:.2f} | 伤害: {damage}{hp_info}"
        )

        if attacker_will_delta != 0 or defender_will_delta != 0:
            self.action_lines.append(
                f"   气力变化: {attacker_name}({attacker_will_delta:+d}) {defender_name}({defender_will_delta:+d})"
            )

    def present_status(self, mecha_a: Mecha, mecha_b: Mecha):
        """格式化机体状态（系统信息，在线上）"""
        self.action_lines.append(
            f"{mecha_a.name}: HP={mecha_a.current_hp}/{mecha_a.final_max_hp} | "
            f"EN={mecha_a.current_en}/{mecha_a.final_max_en} | 气力={mecha_a.current_will}"
        )
        self.action_lines.append(
            f"{mecha_b.name}: HP={mecha_b.current_hp}/{mecha_b.final_max_hp} | "
            f"EN={mecha_b.current_en}/{mecha_b.final_max_en} | 气力={mecha_b.current_will}"
        )

    def present_death(self, victim: Mecha, killer: Mecha, result: AttackResult):
        """格式化死亡信息（系统信息，在线上）"""
        result_desc = {
            AttackResult.CRIT: "暴击",
            AttackResult.HIT: "命中",
            AttackResult.BLOCK: "格挡但伤害致命",
            AttackResult.PARRY: "招架但伤害致命",
            AttackResult.DODGE: "躲闪但受到溅射伤害",
            AttackResult.MISS: "未命中但受到其他伤害"
        }.get(result, "攻击")
        self.action_lines.append(f"💀 {victim.name} 被击破！({killer.name}的{result_desc}造成致命一击)")

    def present_presentation(self, evt: PresentationAttackEvent):
        """格式化演出文字（线下，明确标注）"""
        # 确定颜色（ACTION黄色，REACTION蓝色）
        color = "\033[93m" if evt.event_type == "ACTION" else "\033[94m"
        self.reaction_lines.append(f"{color}{evt.text}\033[0m")

    def flush(self) -> str:
        """输出格式化的战斗信息，系统信息在线上，演出信息在线下"""
        lines = []
        # 系统信息在线上
        for line in self.action_lines:
            lines.append(line)
        # 演出信息在线下，单独分区
        if self.reaction_lines:
            lines.append("  ════════════════════════════════════════════════════════════════")
            lines.append("  【战斗演出】")
            for line in self.reaction_lines:
                lines.append(f"  {line}")
        return "\n".join(lines)

    def clear(self):
        """清空缓冲区"""
        self.action_lines = []
        self.reaction_lines = []

    @property
    def _last_result(self):
        return getattr(self, '_saved_result', None)

    @_last_result.setter
    def _last_result(self, value):
        self._saved_result = value


# ============================================================================
# 统计采集模块
# ============================================================================

class PresentationStatisticsCollector:
    """负责收集战斗演出数据并生成量化报告。"""
    def __init__(self):
        self.raw_events: List[RawAttackEvent] = []
        self.tier_counts = collections.Counter()
        self.result_tier_matrix = collections.defaultdict(collections.Counter)
        self.template_usage = collections.Counter()
        self.weapon_template_usage = collections.defaultdict(collections.Counter)

    def on_presentation_events(self, pres_events: List[PresentationAttackEvent]):
        if not pres_events: return
        evt = pres_events[0]
        raw = evt.raw_event
        if not raw: return

        self.raw_events.append(raw)
        self.tier_counts[evt.tier.name] += 1
        self.result_tier_matrix[raw.attack_result][evt.tier.name] += 1
        self.template_usage[evt.template_id] += 1
        self.weapon_template_usage[raw.weapon_type][evt.template_id] += 1

    def calculate_entropy(self) -> float:
        total = sum(self.template_usage.values())
        if total == 0: return 0.0
        entropy = 0.0
        for count in self.template_usage.values():
            p = count / total
            entropy -= p * math.log2(p)
        return entropy

    def generate_report(self) -> Dict[str, Any]:
        total = len(self.raw_events)
        if total == 0: return {"status": "No data"}
        t3_rate = (self.tier_counts.get("T3_FALLBACK", 0) / total) * 100
        return {
            "summary": {
                "total_attacks": total,
                "diversity_entropy": round(self.calculate_entropy(), 3),
                "t3_fallback_rate": f"{t3_rate:.2f}%",
                "tier_distribution": dict(self.tier_counts)
            },
            "result_tier_matrix": {res: dict(tiers) for res, tiers in self.result_tier_matrix.items()},
            "top_templates": dict(self.template_usage.most_common(10)),
            "weapon_variety": {wt: len(templates) for wt, templates in self.weapon_template_usage.items()}
        }


# ============================================================================
# 工具函数
# ============================================================================

def assign_random_weapons(mecha_snapshot, weapons_config: dict, exclude_dummy: bool = True,
                          min_weapons: int = 2, max_weapons: int = 4):
    """为机体随机分配武器（约束：最多两种武器类型）

    Args:
        mecha_snapshot: 机体快照对象
        weapons_config: 武器配置字典 {id: config}
        exclude_dummy: 是否排除木桩武器
        min_weapons: 最少武器数
        max_weapons: 最多武器数
    """
    # 筛选真正的武器（type="WEAPON"）
    weapon_configs = {
        wid: wc for wid, wc in weapons_config.items()
        if wc.type == "WEAPON" and wc.weapon_power is not None
    }
    if exclude_dummy:
        weapon_configs = {wid: wc for wid, wc in weapon_configs.items() if wid != "wpn_dummy"}

    if not weapon_configs:
        return []

    # 按武器类型分组
    from collections import defaultdict
    weapons_by_type = defaultdict(list)
    for wid, wc in weapon_configs.items():
        weapon_type = wc.weapon_type if wc.weapon_type else WeaponType.SHOOTING
        weapons_by_type[weapon_type].append((wid, wc))

    available_types = list(weapons_by_type.keys())

    # 随机选择1-2种武器类型，确保至少有min_weapons个武器可用
    selected_types = []
    available_weapons = []

    # 先随机选择1种类型
    first_type = random.choice(available_types)
    selected_types.append(first_type)

    # 收集第一种类型的武器
    for wid, wc in weapons_by_type[first_type]:
        available_weapons.append((wid, wc))

    # 如果武器数不足min_weapons，再选择一种类型
    if len(available_weapons) < min_weapons and len(available_types) > 1:
        remaining_types = [t for t in available_types if t != first_type]
        second_type = random.choice(remaining_types)
        selected_types.append(second_type)
        for wid, wc in weapons_by_type[second_type]:
            available_weapons.append((wid, wc))
    # 随机决定是否添加第二种类型（如果已有足够武器）
    elif len(available_types) > 1 and random.random() < 0.5:
        remaining_types = [t for t in available_types if t != first_type]
        second_type = random.choice(remaining_types)
        selected_types.append(second_type)
        for wid, wc in weapons_by_type[second_type]:
            available_weapons.append((wid, wc))

    # 清空现有武器列表
    mecha_snapshot.weapons = []

    # 随机选择武器数量（确保不超过可用武器数）
    actual_max = min(max_weapons, len(available_weapons))
    actual_min = min(min_weapons, actual_max)
    num_weapons = random.randint(actual_min, actual_max)
    selected_weapons = random.sample(available_weapons, num_weapons)

    # 为每个武器创建WeaponSnapshot
    for weapon_id, weapon_config in selected_weapons:
        weapon = WeaponSnapshot(
            uid=f"{weapon_config.id}_{mecha_snapshot.instance_id}",
            definition_id=weapon_config.id,
            name=weapon_config.name,
            type=weapon_config.weapon_type if weapon_config.weapon_type else WeaponType.SHOOTING,
            final_power=weapon_config.weapon_power,
            en_cost=weapon_config.weapon_en_cost,
            range_min=weapon_config.weapon_range_min,
            range_max=weapon_config.weapon_range_max,
            will_req=weapon_config.weapon_will_req,
            anim_id=weapon_config.weapon_anim_id,
            tags=weapon_config.weapon_tags,
        )
        mecha_snapshot.weapons.append(weapon)

    return [w.name for w in mecha_snapshot.weapons]


# ============================================================================
# 场景定义模块
# ============================================================================

class BattleScenario:
    def __init__(self, name: str, desc: str):
        self.name, self.desc = name, desc
        self.mecha_a = self.mecha_b = None
        self.dist_provider = None
        self.random_weapons = False  # 是否使用随机武器

    def setup(self, loader: DataLoader): pass

    def _create(self, loader: DataLoader, mid: str, pid: str = None):
        return MechaFactory.create_mecha_snapshot(
            loader.get_mecha_config(mid),
            pilot_conf=loader.get_pilot_config(pid) if pid else None,
            weapon_configs=loader.equipments
        )

class NormalScenario(BattleScenario):
    def setup(self, loader: DataLoader):
        mids = list(loader.mechas.keys())
        pids = list(loader.pilots.keys())
        self.mecha_a = self._create(loader, mids[0], pids[0] if pids else None)
        self.mecha_b = self._create(loader, mids[1] if len(mids)>1 else mids[0])

        # 如果启用随机武器
        if self.random_weapons:
            weapons_a = assign_random_weapons(self.mecha_a, loader.equipments)
            weapons_b = assign_random_weapons(self.mecha_b, loader.equipments)
            self._weapon_info = f"{self.mecha_a.name}: {', '.join(weapons_a)} | {self.mecha_b.name}: {', '.join(weapons_b)}"
        else:
            self._weapon_info = f"{self.mecha_a.name}: {', '.join([w.name for w in self.mecha_a.weapons])} | {self.mecha_b.name}: {', '.join([w.name for w in self.mecha_b.weapons])}"

class BossPressureScenario(BattleScenario):
    def setup(self, loader: DataLoader):
        mids = list(loader.mechas.keys())
        self.mecha_a = self._create(loader, mids[0])
        self.mecha_b = self._create(loader, mids[1] if len(mids)>1 else mids[0])

        # 如果启用随机武器（在强化前分配）
        if self.random_weapons:
            weapons_a = assign_random_weapons(self.mecha_a, loader.equipments)
            weapons_b = assign_random_weapons(self.mecha_b, loader.equipments)

        if self.mecha_b:
            self.mecha_b.final_hit += 50
            self.mecha_b.final_max_hp *= 10
            self.mecha_b.current_hp = self.mecha_b.final_max_hp
            for w in self.mecha_b.weapons: w.final_power *= 2

        # 记录武器信息
        self._weapon_info = f"{self.mecha_a.name}: {', '.join([w.name for w in self.mecha_a.weapons])} | {self.mecha_b.name}: {', '.join([w.name for w in self.mecha_b.weapons])}"

class MeleeBrawlScenario(BattleScenario):
    def setup(self, loader: DataLoader):
        mids = list(loader.mechas.keys())
        self.mecha_a = self._create(loader, mids[0]); self.mecha_b = self._create(loader, mids[1] if len(mids)>1 else mids[0])
        self.dist_provider = lambda r: random.randint(200, 800)

        # 如果启用随机武器
        if self.random_weapons:
            weapons_a = assign_random_weapons(self.mecha_a, loader.equipments)
            weapons_b = assign_random_weapons(self.mecha_b, loader.equipments)
        self._weapon_info = f"{self.mecha_a.name}: {', '.join([w.name for w in self.mecha_a.weapons])} | {self.mecha_b.name}: {', '.join([w.name for w in self.mecha_b.weapons])}"


# ============================================================================
# 运行引擎与入口
# ============================================================================

def run_simulation(args):
    data_loader = DataLoader(data_dir="data")
    data_loader.load_all()

    scenarios = {
        "normal": NormalScenario("普通对战", "标准对峙，验证通用演出覆盖"),
        "boss": BossPressureScenario("Boss 压迫", "玩家处于劣势，验证受损演出"),
        "melee": MeleeBrawlScenario("近战缠斗", "强制近距离，验证格斗模板")
    }
    scenario = scenarios.get(args.scenario, scenarios["normal"])
    scenario.random_weapons = args.random_weapons  # 设置是否使用随机武器
    collector = PresentationStatisticsCollector()

    print(f"\n>>> 运行场景: {scenario.name} | 次数: {args.count}")
    if args.random_weapons:
        print(f">>> 武器配置: 随机分配 (2-4件武器)")

    for i in range(args.count):
        scenario.setup(data_loader)
        if i == 0 and hasattr(scenario, '_weapon_info'):
            print(f">>> {scenario._weapon_info}")
        sim = CustomBattleSimulator(scenario.mecha_a, scenario.mecha_b, verbose=(i==0))
        sim.register_presentation_event_listener(collector.on_presentation_events)
        if scenario.dist_provider: sim.distance_provider = scenario.dist_provider
        sim.run_battle()

    report = collector.generate_report()

    # 仅在显式指定路径时保存文件，否则仅输出到控制台
    if args.report:
        os.makedirs(os.path.dirname(args.report), exist_ok=True)
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=4, ensure_ascii=False)
        print(f"\n>>> 报告已存至: {args.report}")
    else:
        # 如果不保存文件，把核心统计打印出来方便一眼看到
        print("\n>>> 统计简报:")
        print(json.dumps(report["summary"], indent=4, ensure_ascii=False))
        print(">>> 提示: 使用 --report [path] 可将完整详细报告保存为 JSON 文件。")

    print(f"\n>>> 模拟结束。T3回退率: {report['summary']['t3_fallback_rate']} | 熵值: {report['summary']['diversity_entropy']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=str, default="normal")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--random-weapons", action="store_true", help="为机体随机分配武器")
    parser.add_argument("--report", type=str, default=None, help="详细统计报告保存路径 (可选)")
    run_simulation(parser.parse_args())