import time
import random
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from src.models import MechaSnapshot
from src.pve.models import PveSessionData, PveEntityState, PveEnemyState
from src.pve.enums import CombatOutcome
from src.factory import MechaFactory
from src.combat.engine import BattleSimulator
from src.pve.services import MothershipIntegrationService
from src.core.item_generator import EquipmentGenerator

@dataclass
class BattleResult:
    """遭遇战的完整结算结果。

    Attributes:
        outcome (CombatOutcome): 胜负平结果枚举。
        player_states (List[PveEntityState]): 己方全队成员在战斗结束后的最新状态。
        enemy_state (Optional[PveEntityState]): 敌方实体的残血/存活状态。
        rounds_fought (int): 战斗实际进行的回合数。
        credits_earned (int): 本场战斗掉落的信用点金额。
        loot_drops (List[Dict[str, Any]]): 产生的战利品列表（包含装备字典或物品详情）。
    """
    outcome: CombatOutcome
    player_states: List[PveEntityState]
    enemy_state: Optional[PveEntityState]
    rounds_fought: int
    credits_earned: int
    loot_drops: List[Dict[str, Any]]

class BattleBridge:
    """PVE 与战斗引擎之间的桥接层。

    负责准备战斗现场、处理战前恢复，并根据战斗结果更新 PVE 的持久化状态以及生成奖励。
    """
    
    @staticmethod
    def _apply_time_regen(state: PveEntityState, mothership: Any, current_time: float):
        """应用基于现实时间的恢复补偿逻辑。

        Args:
            state (PveEntityState): 待恢复的目标实体状态。
            mothership (Any): 母舰配置数据，用于获取恢复率。
            current_time (float): 当前时间戳。
        """
        hp_regen, en_regen = MothershipIntegrationService.calculate_regeneration(
            state.last_combat_time, current_time, mothership
        )
        state.current_hp = min(state.max_hp, state.current_hp + hp_regen)
        state.current_en = min(state.max_en, state.current_en + en_regen)

    @staticmethod
    def _apply_scaling(enemy_snapshot: MechaSnapshot, scaling: Any) -> None:
        """应用缩放系数到敌方快照。

        Args:
            enemy_snapshot: 敌方机体快照。
            scaling: 缩放配置对象，包含 hp_mult, damage_mult, armor_mult, mobility_mult。
        """
        if not scaling:
            return

        # 缩放机体属性
        enemy_snapshot.final_max_hp = int(enemy_snapshot.final_max_hp * scaling.hp_mult)
        enemy_snapshot.current_hp = enemy_snapshot.final_max_hp
        enemy_snapshot.final_armor = int(enemy_snapshot.final_armor * scaling.armor_mult)
        enemy_snapshot.final_mobility = int(enemy_snapshot.final_mobility * scaling.mobility_mult)

        # 缩放武器伤害
        for weapon in enemy_snapshot.weapons:
            weapon.final_power = int(weapon.final_power * scaling.damage_mult)

    @staticmethod
    def _translate_outcome(sim_result: Dict[str, Any]) -> CombatOutcome:
        """翻译战斗引擎结果为枚举。

        Args:
            sim_result: 战斗模拟器返回的结果字典。

        Returns:
            CombatOutcome: 战斗结果枚举。
        """
        outcome_str = sim_result["outcome"]
        if outcome_str == "a_wins":
            return CombatOutcome.WIN
        elif outcome_str == "b_wins":
            return CombatOutcome.LOSE
        else:
            return CombatOutcome.DRAW

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
            if zone_config and hasattr(zone_config, 'drop_rate_mult'):
                drop_chance *= zone_config.drop_rate_mult

            if random.random() <= drop_chance:
                if drop.type == "equipment" and drop.equipment_id:
                    if hasattr(loader, 'equipments') and drop.equipment_id in loader.equipments:
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
               mecha_factory: MechaFactory,
               player_index: int = 0,
               verbose: bool = False) -> BattleResult:
        """执行一场与当前事件中敌人的遭遇战。

        Args:
            session (PveSessionData): 当前活跃的 PVE 会话实例。
            event_index (int): 触发战斗的事件索引（对应 event_sequence.current_index）。
            loader (Any): 静态资源加载器。
            mothership_config (Any): 玩家携带的母舰配置对象。
            mecha_factory (MechaFactory): 用于构建战斗快照的工厂。
            player_index (int, optional): 指定己方阵营中第几个成员出战。默认为 0。
            verbose (bool, optional): 是否显示详细战斗过程。默认为 False。

        Returns:
            BattleResult: 包含胜负、损耗及掉落的详细结算结果。

        Raises:
            ValueError: 当指定的 event_index 在序列中不存在时抛出。
        """
        current_time = time.time()

        # 预加载副本配置（避免重复调用）
        instance_config = None
        base_ilvl = 10
        try:
            instance_config = loader.get_instance_config(session.region_id)
            base_ilvl = getattr(instance_config, 'base_ilvl', 10)
        except KeyError:
            pass

        # 1. 还原己方机体
        player_state = session.squad_state.members[player_index]
        cls._apply_time_regen(player_state, mothership_config, current_time)

        # 从 locked_config 还原实际编队数据
        mechas_config = session.squad_state.locked_config.get("mechas", [])
        if player_index < len(mechas_config):
            m_config_data = mechas_config[player_index]
            snapshot_dict = m_config_data.get("snapshot_dict")

            if snapshot_dict:
                player_snapshot = MechaSnapshot.model_validate(snapshot_dict)
            else:
                mecha_id = m_config_data.get("mecha_id", "rx78")
                mecha_config = loader.get_mecha_config(mecha_id) if mecha_id in getattr(loader, 'mechas', {}) else loader.get_mecha_config("rx78")
                player_snapshot = mecha_factory.create_mecha_snapshot(mecha_config, weapon_configs=loader.equipments)
        else:
            mecha_config = loader.get_mecha_config("rx78")
            player_snapshot = mecha_factory.create_mecha_snapshot(mecha_config, weapon_configs=loader.equipments)

        # 注入残血数据
        player_snapshot.current_hp = player_state.current_hp
        player_snapshot.current_en = player_state.current_en
        player_snapshot.final_max_hp = player_state.max_hp
        player_snapshot.final_max_en = player_state.max_en

        # 2. 还原或创建敌方机体
        events = session.event_sequence.events
        if event_index < 0 or event_index >= len(events):
            raise ValueError(f"Event index {event_index} out of range in event sequence")

        current_event = events[event_index]
        enemy_template_id = current_event.event_id or "zaku2"

        # 解析敌方模板（Doc 13：由机体+驾驶员+缩放系数组成）
        enemy_mecha_id = enemy_template_id
        scaling = None

        # 从 InstanceConfig 获取敌方模板
        if instance_config and enemy_template_id in instance_config.enemy_templates:
            template = instance_config.enemy_templates[enemy_template_id]
            enemy_mecha_id = template.mecha_id
            scaling = template.scaling

        # 构建敌方机体
        enemy_config = loader.get_mecha_config(enemy_mecha_id) if enemy_mecha_id in getattr(loader, 'mechas', {}) else loader.get_mecha_config("mech_grunt")
        enemy_snapshot = mecha_factory.create_mecha_snapshot(enemy_config, weapon_configs=loader.equipments)

        # 应用缩放系数
        cls._apply_scaling(enemy_snapshot, scaling)
        
        if event_index in session.enemy_states:
            enemy_pve_state = session.enemy_states[event_index].entity_state
            enemy_snapshot.current_hp = enemy_pve_state.current_hp
            enemy_snapshot.current_en = enemy_pve_state.current_en
            enemy_snapshot.final_max_hp = enemy_pve_state.max_hp
            enemy_snapshot.final_max_en = enemy_pve_state.max_en
        else:
            enemy_pve_state = PveEntityState(
                entity_id=f"enemy_{event_index}",
                current_hp=enemy_snapshot.max_hp,
                current_en=enemy_snapshot.max_en,
                max_hp=enemy_snapshot.max_hp,
                max_en=enemy_snapshot.max_en,
                last_combat_time=current_time
            )
            session.enemy_states[event_index] = PveEnemyState(
                event_index=event_index,
                entity_state=enemy_pve_state,
                enemy_template_id=enemy_template_id
            )

        # 3. 发动战斗
        simulator = BattleSimulator(player_snapshot, enemy_snapshot, enable_presentation=True, quiet=not verbose)
        simulator.run_battle()
        sim_result = simulator.get_result()

        # 4. 更新战斗后状态
        result_player = sim_result["mecha_a"]
        result_enemy = sim_result["mecha_b"]

        player_state.current_hp = result_player["hp"]
        player_state.current_en = result_player["en"]
        player_state.is_alive = result_player["alive"]
        player_state.last_combat_time = current_time

        enemy_pve_state.current_hp = result_enemy["hp"]
        enemy_pve_state.current_en = result_enemy["en"]
        enemy_pve_state.is_alive = result_enemy["alive"]
        enemy_pve_state.last_combat_time = current_time

        outcome = cls._translate_outcome(sim_result)

        # 5. 更新事件状态
        if outcome == CombatOutcome.WIN:
            if event_index < len(session.event_sequence.events):
                session.event_sequence.events[event_index].cleared = True
            if event_index in session.enemy_states:
                del session.enemy_states[event_index]

        # 6. 生成奖励
        loot_drops = []
        credits_earned = 0
        if outcome == CombatOutcome.WIN:
            credits_earned = 100
            event_type_name = events[event_index].event_type.name
            loot_drops = cls._generate_loot(event_type_name, instance_config, loader, session.zone_id, base_ilvl)
        
        return BattleResult(
            outcome=outcome,
            player_states=session.squad_state.members,
            enemy_state=enemy_pve_state if outcome == CombatOutcome.DRAW else None,
            rounds_fought=sim_result["rounds"],
            credits_earned=credits_earned,
            loot_drops=loot_drops
        )
