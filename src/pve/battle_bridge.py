import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from src.pve.models import PveSessionData, PveEntityState, PveEnemyState
from src.pve.enums import CombatOutcome
from src.factory import MechaFactory
from src.combat.engine import BattleSimulator
from src.pve.services import MothershipIntegrationService

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
        
    @classmethod
    def engage(cls, session: PveSessionData, event_index: int,
               loader: Any, 
               mothership_config: Any, 
               mecha_factory: MechaFactory,
               player_index: int = 0) -> BattleResult:
        """执行一场与当前事件中敌人的遭遇战。

        Args:
            session (PveSessionData): 当前活跃的 PVE 会话实例。
            event_index (int): 触发战斗的事件索引（对应 event_sequence.current_index）。
            loader (Any): 静态资源加载器。
            mothership_config (Any): 玩家携带的母舰配置对象。
            mecha_factory (MechaFactory): 用于构建战斗快照的工厂。
            player_index (int, optional): 指定己方阵营中第几个成员出战。默认为 0。

        Returns:
            BattleResult: 包含胜负、损耗及掉落的详细结算结果。

        Raises:
            ValueError: 当指定的 event_index 在序列中不存在时抛出。
        """
        current_time = time.time()
        
        # 1. 还原己方机体
        player_state = session.squad_state.members[player_index]
        # 回血
        cls._apply_time_regen(player_state, mothership_config, current_time)
        
        # 从 locked_config 还原实际编队数据
        mechas_config = session.squad_state.locked_config.get("mechas", [])
        if player_index < len(mechas_config):
            m_config_data = mechas_config[player_index]
            snapshot_dict = m_config_data.get("snapshot_dict")
            
            if snapshot_dict:
                from src.models import MechaSnapshot
                player_snapshot = MechaSnapshot.model_validate(snapshot_dict)
            else:
                mecha_id = m_config_data.get("mecha_id", "rx78")
                try:
                    mecha_config = loader.get_mecha_config(mecha_id)
                except KeyError:
                    mecha_config = loader.get_mecha_config("rx78")
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

        # event_index 作为 key 存储 enemy_states
        try:
            enemy_config = loader.get_mecha_config(enemy_template_id)
        except KeyError:
            enemy_config = loader.get_mecha_config("zaku2")
            
        enemy_snapshot = mecha_factory.create_mecha_snapshot(enemy_config, weapon_configs=loader.equipments)
        
        if event_index in session.enemy_states:
            enemy_pve_state = session.enemy_states[event_index].entity_state
            # 回血 (通常敌方不回血或取决于设计，目前设定敌方不获取母舰回血)
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
        simulator = BattleSimulator(player_snapshot, enemy_snapshot, enable_presentation=False, quiet=True)
        simulator.run_battle()
        sim_result = simulator.get_result()
        
        # 4. 战后抽提
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
        
        outcome_str = sim_result["outcome"]
        if outcome_str == "a_wins":
            outcome = CombatOutcome.WIN
        elif outcome_str == "b_wins":
            outcome = CombatOutcome.LOSE
        else:
            outcome = CombatOutcome.DRAW
            
        # 5. 更新事件状态
        if outcome == CombatOutcome.WIN:
            # 将事件标记为已清除
            if event_index < len(session.event_sequence.events):
                session.event_sequence.events[event_index].cleared = True
            if event_index in session.enemy_states:
                del session.enemy_states[event_index]
                
        # 6. 生成奖励 Loot
        loot_drops = []
        credits_earned = 0
        if outcome == CombatOutcome.WIN:
            credits_earned = 100
            
            # 引入装备随机词条生成流水线
            from src.core.item_generator import EquipmentGenerator
            generator = EquipmentGenerator(loader)
            
            try:
                region_config = loader.get_region_config(session.region_id)
                base_ilvl = getattr(region_config, 'base_ilvl', 10) # Fallback to 10 if missing
            except KeyError:
                base_ilvl = 10
                
            # 随机挑选一个装备掉落（模拟掉落表）
            import random
            if loader.equipments:
                equip_id = random.choice(list(loader.equipments.keys()))
                random_stats = generator.generate_equipment(equip_id, base_ilvl)
                
                loot_drops.append({
                    "type": "equipment",
                    "equipment_id": equip_id,
                    "enhancement_level": 0,
                    "random_stats": random_stats
                })
                
            # 随机加一点消耗品或者素材强化物
            loot_drops.append({
                "type": "item",
                "item_id": "mat_armor_plate", # 一种假设的通用基础材料
                "quantity": random.randint(1, 3)
            })
        
        return BattleResult(
            outcome=outcome,
            player_states=session.squad_state.members,
            enemy_state=enemy_pve_state if outcome == CombatOutcome.DRAW else None,
            rounds_fought=sim_result["rounds"],
            credits_earned=credits_earned,
            loot_drops=loot_drops
        )
