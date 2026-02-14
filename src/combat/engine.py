"""
战斗引擎
包含先手判定、武器选择和战斗主循环
"""

import random
from ..config import Config
from ..models import Mecha, Weapon, WeaponType, BattleContext, InitiativeReason, AttackResult
from ..skills import SkillRegistry, EffectManager
from .resolver import AttackTableResolver
from typing import Callable, Any, List
from ..models import TriggerEvent


class InitiativeCalculator:
    """先手判定系统"""
    
    def __init__(self) -> None:
        """初始化先手判定系统。

        创建连续先攻计数器,用于强制换手机制。
        """
        self.consecutive_wins: dict[str, int] = {
            'A': 0,  # A方连先次数
            'B': 0   # B方连先次数
        }
        self.last_winner: str | None = None
    
    def calculate_initiative(
        self,
        mecha_a: Mecha,
        mecha_b: Mecha,
        round_number: int
    ) -> tuple[Mecha, Mecha, InitiativeReason]:
        """计算回合的先手方和后手方。

        判定优先级:
        1. 强制换手机制 (连续先攻达到阈值)
        2. 技能强制先攻钩子
        3. 综合优势判定 (机动性、反应值、气力)
        4. 平局时上回合后手方获得先手

        算法思路:
        - 第一层检查绝对优先权 (换机制、技能钩子)
        - 第二层计算综合得分 = 机动性*权重 + 反应*权重 + 气力加成 + 随机波动
        - 根据得分差异判断先手原因

        Args:
            mecha_a: A 方机体
            mecha_b: B 方机体
            round_number: 当前回合数 (未使用,保留用于扩展)

        Returns:
            tuple[Mecha, Mecha, InitiativeReason]: (先手方, 后手方, 先手原因)
        """
        
        # === 第一层: 绝对优先权 ===
        
        # 检查强制换手机制
        if self.consecutive_wins['A'] >= Config.CONSECUTIVE_WINS_THRESHOLD:
            self._update_winner('B')
            return (mecha_b, mecha_a, InitiativeReason.FORCED_SWITCH)
        
        if self.consecutive_wins['B'] >= Config.CONSECUTIVE_WINS_THRESHOLD:
            self._update_winner('A')
            return (mecha_a, mecha_b, InitiativeReason.FORCED_SWITCH)
        
        # 检查技能: 强制先攻 (HOOK_INITIATIVE_CHECK)
        # 这里的钩子如果返回 True，表示强制该机体先手
        # 构建简单上下文
        ctx_a = BattleContext(round_number=round_number, distance=0, mecha_a=mecha_a, mecha_b=None)
        ctx_b = BattleContext(round_number=round_number, distance=0, mecha_a=mecha_b, mecha_b=None)
        
        force_a = SkillRegistry.process_hook("HOOK_INITIATIVE_CHECK", False, ctx_a)
        if force_a:
            self._update_winner('A')
            return (mecha_a, mecha_b, InitiativeReason.PERFORMANCE)
            
        force_b = SkillRegistry.process_hook("HOOK_INITIATIVE_CHECK", False, ctx_b)
        if force_b:
            self._update_winner('B')
            return (mecha_b, mecha_a, InitiativeReason.PERFORMANCE)
        
        # === 第二层: 综合优势判定 ===
        
        score_a: float = self._calculate_initiative_score(mecha_a)
        score_b: float = self._calculate_initiative_score(mecha_b)
        
        # 判断理由
        if score_a > score_b:
            winner: Mecha = mecha_a
            reason: InitiativeReason = self._determine_reason(mecha_a, mecha_b)
            self._update_winner('A')
            return (winner, mecha_b, reason)
        elif score_b > score_a:
            winner: Mecha = mecha_b
            reason: InitiativeReason = self._determine_reason(mecha_b, mecha_a)
            self._update_winner('B')
            return (winner, mecha_a, reason)
        else:
            # 平局: 上回合后手方获得先手
            if self.last_winner == 'A':
                self._update_winner('B')
                return (mecha_b, mecha_a, InitiativeReason.COUNTER)
            else:
                self._update_winner('A')
                return (mecha_a, mecha_b, InitiativeReason.COUNTER)
    
    def _calculate_initiative_score(self, mecha: Mecha) -> float:
        """计算机体的先手判定得分。

        计算公式:
        得分 = (机动性 * 机动权重) + (反应值 * 反应权重) + (气力 * 气力系数) + 随机波动

        Args:
            mecha: 要计算得分的机体

        Returns:
            float: 先手判定得分 (越高越容易获得先手)
        """
        # 基底
        base_score: float = (
            mecha.final_mobility * Config.INITIATIVE_MOBILITY_WEIGHT +
            mecha.pilot_stats_backup.get('stat_reaction', 0) * Config.INITIATIVE_REACTION_WEIGHT
        )

        # 气力修正
        will_bonus: float = mecha.current_will * Config.INITIATIVE_WILL_BONUS

        # 随机事件 (小幅度)
        random_event: float = random.uniform(
            -Config.INITIATIVE_RANDOM_RANGE,
            Config.INITIATIVE_RANDOM_RANGE
        )

        final_score = base_score + will_bonus + random_event

        # HOOK: 先攻得分修正 (HOOK_INITIATIVE_SCORE)
        # 在 Initiative 阶段，创建临时 context 来处理钩子
        ctx = BattleContext(round_number=0, distance=0, mecha_a=mecha, mecha_b=None)
        final_score = SkillRegistry.process_hook("HOOK_INITIATIVE_SCORE", final_score, ctx)

        return final_score
    
    def _determine_reason(self, winner: Mecha, loser: Mecha) -> InitiativeReason:
        """根据双方属性差异判断先手原因。

        判定逻辑:
        - 机动性差异 > 20: 机体性能优势
        - 反应值差异 > 15: 驾驶员感知优势
        - 气力差异 > 20: 气力优势延续
        - 其他情况: 机体性能优势 (默认)

        Args:
            winner: 获得先手的机体
            loser: 失去先手的机体

        Returns:
            InitiativeReason: 先手原因枚举值
        """
        # 简化逻辑
        mobility_diff: int = abs(winner.final_mobility - loser.final_mobility)
        reaction_diff: int = abs(winner.pilot_stats_backup.get('stat_reaction', 0) - loser.pilot_stats_backup.get('stat_reaction', 0))
        will_diff: int = abs(winner.current_will - loser.current_will)

        if mobility_diff > 20:
            return InitiativeReason.PERFORMANCE
        elif reaction_diff > 15:
            return InitiativeReason.PILOT
        elif will_diff > 20:
            return InitiativeReason.ADVANTAGE
        else:
            return InitiativeReason.PERFORMANCE
    
    def _update_winner(self, winner_id: str) -> None:
        """更新连续先攻记录。

        如果与上一回合获胜方相同,增加连胜计数;
        否则重置所有计数并设置新的获胜方。

        Args:
            winner_id: 获胜方标识 ('A' 或 'B')
        """
        if self.last_winner == winner_id:
            self.consecutive_wins[winner_id] += 1
        else:
            # 换手了,重置所有计数
            self.consecutive_wins = {'A': 0, 'B': 0}
            self.consecutive_wins[winner_id] = 1

        self.last_winner = winner_id


class WeaponSelector:
    """武器选择策略 (AI)"""
    
    @staticmethod
    def select_best_weapon(mecha: Mecha, distance: int) -> Weapon:
        """选择当前距离下期望伤害最高的武器。

        选择逻辑:
        1. 过滤 EN 不足的武器
        2. 过滤距离不适用的武器
        3. 计算剩余武器的期望伤害 = 威力 * (1 + 距离修正/100)
        4. 选择期望伤害最高的武器
        5. 若无可用武器,返回保底武器 (撞击)

        Args:
            mecha: 要选择武器的机体
            distance: 当前交战距离 (米)

        Returns:
            Weapon: 选中的最佳武器
        """
        available_weapons: list[tuple[Weapon, float]] = []
        
        for weapon in mecha.weapons:
            # 检查EN是否足够
            if not mecha.can_attack(weapon):
                continue
            
            # 检查距离是否适用
            if not weapon.can_use_at_distance(distance):
                continue
            
            # 计算期望伤害 (威力 * 距离修正)
            hit_mod: float = weapon.get_hit_modifier_at_distance(distance)
            if hit_mod <= -999.0:
                continue
            
            expected_damage: float = weapon.power * (1.0 + hit_mod / 100.0)
            available_weapons.append((weapon, expected_damage))
        
        # 如果有可用武器,选择期望伤害最高的
        if available_weapons:
            available_weapons.sort(key=lambda x: x[1], reverse=True)
            return available_weapons[0][0]
        
        # 否则返回保底武器
        return WeaponSelector._create_fallback_weapon()
    
    @staticmethod
    def _create_fallback_weapon() -> Weapon:
        """创建保底撞击武器。

        当机体没有可用武器时使用。
        特点: 低威力 (50), 零 EN 消耗, 全距离可用。

        Returns:
            Weapon: 保底撞击武器对象
        """
        return Weapon(
            uid="wpn_fallback_uid",
            definition_id="wpn_fallback",
            name="撞击",
            type=WeaponType.FALLBACK,
            final_power=50,  # 低威力
            en_cost=0,  # 0消耗
            range_min=0,
            range_max=10000,
            will_req=0,
            anim_id="default"
        )


class BattleSimulator:
    """战斗模拟器主控"""
    
    def __init__(self, mecha_a: Mecha, mecha_b: Mecha) -> None:
        """初始化战斗模拟器。

        Args:
            mecha_a: A 方机体
            mecha_b: B 方机体
        """
        self.mecha_a: Mecha = mecha_a
        self.mecha_b: Mecha = mecha_b
        self.initiative_calc: InitiativeCalculator = InitiativeCalculator()
        self.round_number: int = 0
        self.battle_log: list[str] = []
    
    def run_battle(self) -> None:
        """运行完整的战斗流程。

        战斗流程:
        1. 显示战斗开始信息
        2. 循环执行回合直到:
           - 任一机体 HP 归零
           - 达到最大回合数 (Config.MAX_ROUNDS)
        3. 执行战斗结算,判定胜负

        胜负判定规则:
        - 击破胜: 对方 HP 归零
        - 判定胜: 回合数上限时 HP 百分比更高
        - 平局: HP 百分比相同
        """
        print("=" * 80)
        print(f"战斗开始: {self.mecha_a.name} vs {self.mecha_b.name}")
        print("=" * 80)
        print()

        # 2. 循环执行回合
        # HOOK: 初始回合上限判定 (HOOK_MAX_ROUNDS)
        max_rounds = SkillRegistry.process_hook("HOOK_MAX_ROUNDS", Config.MAX_ROUNDS,
                                              BattleContext(round_number=0, distance=0, mecha_a=self.mecha_a, mecha_b=self.mecha_b))

        while True:
            # 状态检查: 是否有人击破
            if not self.mecha_a.is_alive() or not self.mecha_b.is_alive():
                break

            # 回合上限检查
            if self.round_number >= max_rounds:
                # HOOK: 强制继续战斗判定 (如：死斗/剧情需要)
                ctx = BattleContext(round_number=self.round_number, distance=0, mecha_a=self.mecha_a, mecha_b=self.mecha_b)
                should_maintain = SkillRegistry.process_hook("HOOK_CHECK_MAINTAIN_BATTLE", False, ctx)
                if not should_maintain:
                    break

            self.round_number += 1

            # 执行回合
            self._execute_round()

            print()

        # HOOK: 战斗结束 (HOOK_ON_BATTLE_END)
        # 用于清理 BATTLE_BASED 状态 (如 学习电脑层数)
        # 此时 round_number 可能已经达到 MAX，或者有一方死亡
        final_ctx = BattleContext(round_number=self.round_number, distance=0, mecha_a=self.mecha_a, mecha_b=self.mecha_b)
        SkillRegistry.process_hook("HOOK_ON_BATTLE_END", None, final_ctx)

        # 战斗结算
        self._conclude_battle()
    
    def _execute_round(self) -> None:
        """执行单个战斗回合。

        回合流程:
        1. 生成当前交战距离 (随回合数递减)
        2. 判定先手方和原因
        3. 先手方发动攻击
        4. 检查后手方是否存活,若存活则反击
        5. 回合结束,双方气力 +1
        6. 显示双方当前状态

        如果任一机体在回合中被击破,立即结束回合。
        """
        print(f"{'=' * 80}")
        print(f"ROUND {self.round_number}")
        print(f"{'=' * 80}")

        # 1. 生成距离
        distance: int = self._generate_distance()
        print(f"📍 交战距离: {distance}m")

        # 2. 先手判定
        first_mover, second_mover, reason = self.initiative_calc.calculate_initiative(
            self.mecha_a,
            self.mecha_b,
            self.round_number
        )
        print(f"⚔️  先手方: {first_mover.name} ({reason.value})")
        print()

        # 3. 先攻方攻击
        self._execute_attack(first_mover, second_mover, distance, is_first=True)

        # 检查后攻方是否存活
        if not second_mover.is_alive():
            print(f"💀 {second_mover.name} 被击破!")
            return

        print()

        # 4. 后攻方反击
        self._execute_attack(second_mover, first_mover, distance, is_first=False)

        # 检查先攻方是否存活
        if not first_mover.is_alive():
            print(f"💀 {first_mover.name} 被击破!")
            return

        # 5. 回合结束 - 气力基础增长
        self.mecha_a.modify_will(1)
        self.mecha_b.modify_will(1)

        # HOOK: 回合结束 (HOOK_ON_TURN_END)
        # 用于清理 TURN_BASED 状态，或触发每回合结束的效果 (如 EN回复)
        ctx = BattleContext(round_number=self.round_number, distance=distance, mecha_a=self.mecha_a, mecha_b=self.mecha_b)
        SkillRegistry.process_hook("HOOK_ON_TURN_END", None, ctx)

        # 6. 效果结算 (Tick)
        EffectManager.tick_effects(self.mecha_a)
        EffectManager.tick_effects(self.mecha_b)

        print()
        print(f"📊 {self.mecha_a.name}: HP={self.mecha_a.current_hp}/{self.mecha_a.final_max_hp} | "
              f"EN={self.mecha_a.current_en}/{self.mecha_a.final_max_en} | "
              f"气力={self.mecha_a.current_will}")
        print(f"📊 {self.mecha_b.name}: HP={self.mecha_b.current_hp}/{self.mecha_b.final_max_hp} | "
              f"EN={self.mecha_b.current_en}/{self.mecha_b.final_max_en} | "
              f"气力={self.mecha_b.current_will}")
    
    def _generate_distance(self) -> int:
        """生成当前回合的交战距离。

        距离随回合数线性递减,模拟机体逐渐接近的过程。
        每回合减少固定距离 (Config.DISTANCE_REDUCTION_PER_ROUND)。

        Returns:
            int: 当前回合的随机距离 (米)
        """
        # 计算当前回合的距离范围
        rounds_elapsed: int = self.round_number - 1
        reduction: int = Config.DISTANCE_REDUCTION_PER_ROUND * rounds_elapsed

        range_min: int = max(Config.DISTANCE_FINAL_MIN, Config.DISTANCE_INITIAL_MIN - reduction)
        range_max: int = max(Config.DISTANCE_FINAL_MAX, Config.DISTANCE_INITIAL_MAX - reduction)

        # 在范围内随机
        return random.randint(range_min, range_max)
    
    def _execute_attack(
        self,
        attacker: Mecha,
        defender: Mecha,
        distance: int,
        is_first: bool
    ) -> None:
        """执行单次攻击。

        攻击流程:
        1. AI 选择最佳武器
        2. 检查 EN 是否足够
        3. 消耗 EN
        4. 创建战场上下文
        5. 执行圆桌判定 (Miss/Dodge/Parry/Block/Crit/Hit)
        6. 应用伤害
        7. 应用气力变化
        8. 显示攻击结果

        Args:
            attacker: 攻击方机体
            defender: 防御方机体
            distance: 当前交战距离
            is_first: True 表示先攻, False 表示反击
        """
        # 1. 选择武器
        weapon: Weapon = WeaponSelector.select_best_weapon(attacker, distance)

        print(f"{'[先攻]' if is_first else '[反击]'} {attacker.name} 使用 【{weapon.name}】"
              f" (威力:{weapon.power}, EN消耗:{weapon.en_cost})")

        # 4. 创建战场上下文
        ctx: BattleContext = BattleContext(
            round_number=self.round_number,
            distance=distance,
            mecha_a=attacker,
            mecha_b=defender,
            weapon=weapon
        )

        # 5. 消耗 EN
        weapon_cost = float(weapon.en_cost)
        # HOOK: 修正 EN 消耗 (例如 节能)
        weapon_cost = SkillRegistry.process_hook("HOOK_PRE_EN_COST_MULT", weapon_cost, ctx)
        
        # 检查 EN (修正后的消耗)
        if attacker.current_en < int(weapon_cost):
            print(f"   ❌ EN不足! 无法攻击 (当前EN: {attacker.current_en}, 需要: {int(weapon_cost)})")
            return
            
        attacker.consume_en(int(weapon_cost))

        # 5. 圆桌判定
        result, damage = AttackTableResolver.resolve_attack(ctx)

        # 6. 应用伤害
        if damage > 0:
            defender.take_damage(damage)

        # 7. 应用气力变化
        if ctx.current_attacker_will_delta != 0:
            attacker.modify_will(ctx.current_attacker_will_delta)
        if ctx.current_defender_will_delta != 0:
            defender.modify_will(ctx.current_defender_will_delta)

        # 8. 输出结果
        result_emoji: dict[AttackResult, str] = {
            AttackResult.MISS: "❌",
            AttackResult.DODGE: "💨",
            AttackResult.PARRY: "⚔️",
            AttackResult.BLOCK: "🛡️",
            AttackResult.HIT: "💥",
            AttackResult.CRIT: "💥✨"
        }

        print(f"   {result_emoji.get(result, '❓')} {result.value}! "
              f"Roll点: {ctx.roll} | 伤害: {damage} | "
              f"气力变化: ⚡{attacker.name}({ctx.current_attacker_will_delta:+d}) "
              f"⚡{defender.name}({ctx.current_defender_will_delta:+d})")

        # 9. 结算钩子 (HOOK_ON_DAMAGE_DEALT, HOOK_ON_KILL, HOOK_ON_ATTACK_END)
        
        # HOOK: 造成伤害后
        if damage > 0:
            SkillRegistry.process_hook("HOOK_ON_DAMAGE_DEALT", damage, ctx)
            
        # HOOK: 击坠判定
        if not defender.is_alive():
            SkillRegistry.process_hook("HOOK_ON_KILL", None, ctx)
            
        # HOOK: 攻击结束 (常用于清理 ATTACK_BASED 状态，或触发再动等)
        SkillRegistry.process_hook("HOOK_ON_ATTACK_END", None, ctx)
    
    def _conclude_battle(self) -> None:
        """执行战斗结算并显示胜负结果。

        胜负判定优先级:
        1. 击破胜: 对方 HP 归零
        2. 判定胜: 回合数上限时,比较 HP 百分比
        3. 平局: HP 百分比完全相同
        """
        print()
        print("=" * 80)
        print("战斗结束")
        print("=" * 80)

        # 判断胜负
        if not self.mecha_a.is_alive():
            print(f"🏆 胜者: {self.mecha_b.name} (击破)")
        elif not self.mecha_b.is_alive():
            print(f"🏆 胜者: {self.mecha_a.name} (击破)")
        else:
            # 判定胜
            hp_a: float = self.mecha_a.get_hp_percentage()
            hp_b: float = self.mecha_b.get_hp_percentage()

            print(f"回合数达到上限! 进入判定...")
            print(f"{self.mecha_a.name} HP: {hp_a:.1f}%")
            print(f"{self.mecha_b.name} HP: {hp_b:.1f}%")

            if hp_a > hp_b:
                print(f"🏆 胜者: {self.mecha_a.name} (判定胜)")
            elif hp_b > hp_a:
                print(f"🏆 胜者: {self.mecha_b.name} (判定胜)")
            else:
                print(f"🤝 平局!")

    def set_event_callback(self, callback: Callable[[TriggerEvent], None]) -> None:
        """设置前端事件回调（用于接收技能触发事件）

        Args:
            callback: 回调函数，接收 TriggerEvent 参数
        """
        from ..skill_system.event_manager import EventManager
        EventManager.register_callback(callback)

    def get_trigger_events(self) -> List[TriggerEvent]:
        """获取本回合的所有触发事件（用于前端演出）

        Returns:
            本回合的所有触发事件列表
        """
        from ..skill_system.event_manager import EventManager
        # 注意：当前 EventManager 设计没有历史事件存储
        # 这里返回空列表，实际使用时可能需要扩展 EventManager
        return []
