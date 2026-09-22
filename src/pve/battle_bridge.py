import time
import random
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from src.pve.models import PveSessionData, PveEntityState
from src.pve.enums import CombatOutcome
from src.combat.entry import BattleEntryService
from src.combat.engagement import Engagement
from src.core.item_generator import EquipmentGenerator

@dataclass
class BattleResult:
    """遭遇战的裁定摘要（命令返回值）。

    Attributes:
        outcome (CombatOutcome): 胜负平结果枚举。
        player_states (List[PveEntityState]): 己方全队成员在战斗结束后的最新状态。
        enemy_state (Optional[PveEntityState]): 敌方实体的残血/存活状态。
        rounds_fought (int): 战斗实际进行的回合数。
        credits_earned (int): 本场战斗掉落的信用点金额。
        loot_drops (List[Dict[str, Any]]): 产生的战利品列表（包含装备字典或物品详情）。

    完整战报不在本类（命令与资源分离）：战报的唯一去向是会话暂存
    session.battle_reports（Doc 15 §6），前端经重放端点按引用取用。
    """
    outcome: CombatOutcome
    player_states: List[PveEntityState]
    enemy_state: Optional[PveEntityState]
    rounds_fought: int
    credits_earned: int
    loot_drops: List[Dict[str, Any]]

class BattleBridge:
    """PVE 与战斗编排层之间的桥接（Doc 15 §5 消费方表）。

    只面向委托与战报（战斗知识零泄漏，红线 2）：装配走收发室
    BattleEntryService，裁定走裁判 Engagement；裁定成功后一次性写回
    会话（失败原子，Doc 15 §3）——resolve 抛异常时异常传播、session 零变更。
    """

    @classmethod
    def _generate_loot(
        cls,
        event_type: str,
        instance_config: Any,
        loader: Any,
        zone_id: str,
        base_ilvl: int
    ) -> List[Dict[str, Any]]:
        """生成战斗掉落。

        Args:
            event_type: 事件类型名称。
            instance_config: 副本配置。
            loader: 资源加载器。
            zone_id: 区域 ID。
            base_ilvl: 基础装等。

        Returns:
            掉落物品列表。
        """
        loot_drops = []
        if not instance_config or zone_id not in instance_config.loot_tables:
            return loot_drops

        loot_table = instance_config.loot_tables[zone_id]
        available_drops = []

        # Boss专有掉落
        if event_type == "BOSS_COMBAT":
            available_drops.extend(loot_table.boss_drops)

        # 通用掉落
        available_drops.extend(loot_table.common_drops)

        generator = EquipmentGenerator(loader)
        for drop in available_drops:
            # 应用掉落率倍率（如果配置了）
            drop_chance = drop.chance
            zone_config = instance_config.zones.get(zone_id)
            if zone_config is not None:
                drop_chance *= zone_config.drop_rate_mult

            if random.random() <= drop_chance:
                if drop.type == "equipment" and drop.equipment_id:
                    # 停用模板不产出（Doc 17 场景 4.14）：旧档持有按 id 读配置
                    # 照常展示，只有新掉落在这一闸被拦
                    if drop.equipment_id in loader.equipments and not loader.equipments[drop.equipment_id].deprecated:
                        random_stats = generator.generate_equipment(drop.equipment_id, base_ilvl)
                        loot_drops.append({
                            "type": "equipment",
                            "equipment_id": drop.equipment_id,
                            "enhancement_level": 0,
                            "random_stats": random_stats
                        })
                elif drop.type == "item" and drop.item_id:
                    loot_drops.append({
                        "type": "item",
                        "item_id": drop.item_id,
                        "quantity": drop.quantity
                    })

        return loot_drops

    @classmethod
    def engage(cls, session: PveSessionData, event_index: int,
               loader: Any,
               mothership_config: Any,
               mecha_factory: Any,
               player_index: int = 0) -> BattleResult:
        """执行一场与当前事件中敌人的遭遇战。

        流程：收发室装配（session 零变更）→ 裁判裁定 → 裁定成功后
        一次性写回残血/事件/奖励。装配与裁定逻辑分别归
        BattleEntryService 与 Engagement（Doc 15 §2）。

        Args:
            session (PveSessionData): 当前活跃的 PVE 会话实例。
            event_index (int): 触发战斗的事件索引（对应 event_sequence.current_index）。
            loader (Any): 静态资源加载器。
            mothership_config (Any): 玩家携带的母舰配置对象。
            mecha_factory (Any): 用于构建战斗快照的工厂。
            player_index (int, optional): 指定己方阵营中第几个成员出战。默认为 0。

        Returns:
            BattleResult: 包含胜负、损耗及掉落的详细结算结果。

        Raises:
            ValueError: 当指定的 event_index 在序列中不存在时抛出。
        """
        current_time = time.time()

        # 副本配置加载单点（掉落表、装等、装配侧敌方模板共用）
        instance_config = None
        base_ilvl = 10
        try:
            instance_config = loader.get_instance_config(session.region_id)
            base_ilvl = instance_config.base_ilvl
        except KeyError:
            pass

        # 1. 装配（收发室）→ 2. 裁定（裁判）。裁定成功前 session 零变更（失败原子）。
        spec, assembly = BattleEntryService.build_pve(
            session, event_index, loader, mothership_config, mecha_factory,
            now=current_time, player_index=player_index,
            instance_config=instance_config,
        )
        report = Engagement(spec).resolve()
        # dump 一次、唯一去向是会话暂存（Doc 14 四块结构，Doc 15 §3/§6）
        battle_report = report.timeline.model_dump(mode="json")

        # 3. 裁定成功，一次性写回（Doc 15 §3：残血出自同一次裁定，
        # 唯一来源是裁定 summary）
        result_player = report.ruling.summary.a
        result_enemy = report.ruling.summary.b

        player_state = assembly.player_state
        player_state.current_hp = result_player.hp
        player_state.current_en = result_player.en
        player_state.is_alive = bool(result_player.alive)
        player_state.last_combat_time = current_time

        if assembly.enemy_is_new:
            session.enemy_states[assembly.event_index] = assembly.enemy_state
        enemy_pve_state = assembly.enemy_state.entity_state
        enemy_pve_state.current_hp = result_enemy.hp
        enemy_pve_state.current_en = result_enemy.en
        enemy_pve_state.is_alive = bool(result_enemy.alive)
        enemy_pve_state.last_combat_time = current_time

        # 胜负翻译走裁定口径（Doc 14 §7.1：finish + winner 正交表达）
        if report.ruling.winner == "a":
            outcome = CombatOutcome.WIN
        elif report.ruling.winner == "b":
            outcome = CombatOutcome.LOSE
        else:
            outcome = CombatOutcome.DRAW

        # 4. 更新事件状态
        if outcome == CombatOutcome.WIN:
            assembly.event.cleared = True
            if assembly.event_index in session.enemy_states:
                del session.enemy_states[assembly.event_index]

        # 5. 生成奖励
        loot_drops = []
        credits_earned = 0
        if outcome == CombatOutcome.WIN:
            credits_earned = 100
            loot_drops = cls._generate_loot(
                assembly.event.event_type.name, instance_config, loader, session.zone_id, base_ilvl
            )

        # 6. 暂存战报（Doc 15 §6）：战报唯一去向——发生在全部成功路径之后，
        # 裁定失败时异常早已传播，暂存零写入（失败原子不受影响）
        session.battle_reports[event_index] = battle_report

        return BattleResult(
            outcome=outcome,
            player_states=session.squad_state.members,
            enemy_state=enemy_pve_state if outcome == CombatOutcome.DRAW else None,
            rounds_fought=report.ruling.rounds_fought,
            credits_earned=credits_earned,
            loot_drops=loot_drops
        )
