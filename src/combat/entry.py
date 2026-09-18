"""
战斗入口（收发室）— Doc 15 §4 红线 5：装配单点

各界面（调试 / PVE / 将来的训练与竞技场）进战斗的快照装配只走这里，
别处不许自己攒（现存两处内联装配——simulate 与 battle_bridge——已收编）。

装配产物是 EngagementSpec（构造即值冻结），PVE 路径另附
PveAssemblyContext 携带裁定成功后的写回定位信息。

失败原子（Doc 15 §3）的前提在本层成立：build_* 全程不 mutate 调用方
状态——时间回能、残血注入都算进快照拷贝，PveEntityState 原值不动；
裁定失败时会话零变更，写回由 battle_bridge 在裁定成功后一次性完成。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.factory import MechaFactory
from src.models import MechaSnapshot
from src.pve.models import PveEntityState, PveEnemyState, PveEvent, PveSessionData
from src.pve.services import MothershipIntegrationService
from src.user.repository import UserAssetRepository
from src.core.factory import SnapshotFactory

from .engagement import EngagementContext, EngagementSpec

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.api.presentation_api import BattleRequest
    from src.database.models import User


@dataclass
class PveAssemblyContext:
    """PVE 装配产物：裁定成功后的写回定位信息（Doc 15 §2.3 技术设计）。

    Attributes:
        player_state: 己方出战成员的 PveEntityState 引用（session 内）。
        enemy_state: 敌方 PveEnemyState——已接敌过的事件点是 session.enemy_states
            内的既有引用；新建时是按模板值构造、尚未落 session 的独立对象，
            裁定成功后由 battle_bridge 插入（失败原子的前提）。
        enemy_is_new: 敌方实体是否为本场新建。
        event: 本次接敌的事件引用。
        event_index: 事件在序列中的索引（enemy_states 的键）。
    """

    player_state: PveEntityState
    enemy_state: PveEnemyState
    enemy_is_new: bool
    event: PveEvent
    event_index: int


def _apply_scaling(enemy_snapshot: MechaSnapshot, scaling: Any) -> None:
    """应用缩放系数到敌方快照（Doc 13：模板实例化的数值档）。

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


class BattleEntryService:
    """收发室：各界面进战斗的唯一装配口（Doc 15 §2/§4 红线 5）。

    只管"快照从哪来"，不做裁定也不写回——裁定走 Engagement，
    写回归各玩法（PVE 在 battle_bridge）。
    """

    @staticmethod
    async def build_debug(
        loader: Any,
        req: "BattleRequest",
        user: "User | None",
        db_session: "AsyncSession",
    ) -> EngagementSpec:
        """调试来源装配（POST /battle/simulate 专用，Doc 15 §5 消费方表）。

        静态配置直构快照；登录用户可请求用出战存档覆盖（覆盖失败
        降级回静态配置）。行为自旧 simulate handler 原样搬移。

        Args:
            loader: 静态资源加载器。
            req: 调试请求（双方机体 ID 与存档覆盖开关）。
            user: 当前登录用户（匿名为 None）。
            db_session: 数据库会话（用户存档查询用）。

        Returns:
            EngagementSpec: 值冻结的战斗委托（source="debug"）。

        Raises:
            KeyError: 机体 ID 不存在（由 handler 翻译为 404，Doc 14 §2）。
        """
        # 获取基础配置（未知 ID 时 get_mecha_config 抛 KeyError → 404 契约）
        config_a = loader.get_mecha_config(req.mecha_a_id)
        config_b = loader.get_mecha_config(req.mecha_b_id)

        # 创建基础快照
        mecha_a = MechaFactory.create_mecha_snapshot(config_a, weapon_configs=loader.equipments)
        mecha_b = MechaFactory.create_mecha_snapshot(config_b, weapon_configs=loader.equipments)

        # 如果用户已登录，尝试加载出战小队阵容覆盖
        if user is not None:
            active_squad = await UserAssetRepository.get_active_squad(db_session, user.id)

            if active_squad is not None and len(active_squad.mecha_ids) > 0:
                try:
                    factory = SnapshotFactory(loader, UserAssetRepository())
                    user_mechas = active_squad.mecha_ids

                    # 取出战小队的第一台和第二台机体进行覆盖
                    # 实际业务中应配合请求参数选择出战序号，此处作为平滑过渡
                    if req.use_user_save_for_a and len(user_mechas) > 0:
                        mecha_a = await factory.create_combat_snapshot(db_session, user.id, user_mechas[0])

                    if req.use_user_save_for_b and len(user_mechas) > 1:
                        mecha_b = await factory.create_combat_snapshot(db_session, user.id, user_mechas[1])
                    elif req.use_user_save_for_b and len(user_mechas) > 0:
                        # 兜底：如果选了B但只有一个机甲，用那个
                        mecha_b = await factory.create_combat_snapshot(db_session, user.id, user_mechas[0])

                except (ValueError, KeyError) as e:
                    # 养成数据无效/引用未知机体，忽略并使用默认配置
                    # （404 只指向请求字段；存档缺陷走降级语义，Doc 14 §2）
                    print(f"⚠️ 玩家出战数据无效，使用默认配置: {e}")

        return EngagementSpec(
            mecha_a=mecha_a,
            mecha_b=mecha_b,
            context=EngagementContext(source="debug"),
        )

    @staticmethod
    def build_pve(
        session: PveSessionData,
        event_index: int,
        loader: Any,
        mothership_config: Any,
        mecha_factory: MechaFactory,
        now: float,
        player_index: int = 0,
    ) -> tuple[EngagementSpec, PveAssemblyContext]:
        """PVE 接敌装配（Doc 15 §5：会话还原 + 事件点实例化）。

        我方从 locked_config 还原（回退链 snapshot_dict → mecha_id →
        默认 rx78），时间回能与残血注入全部算进快照——不触碰
        PveEntityState（失败原子的前提）；敌方由事件点模板 + 缩放
        实例化，已接敌过的事件点注入敌方残血。全程不 mutate session。

        Args:
            session: 当前活跃的 PVE 会话。
            event_index: 接敌的事件索引。
            loader: 静态资源加载器。
            mothership_config: 玩家母舰配置（战间恢复率来源）。
            mecha_factory: 用于构建战斗快照的工厂。
            now: 当前时间戳（时间回能基准）。
            player_index: 己方出战成员下标（恒首机出战，Doc 15 §6 裁决 #6）。

        Returns:
            tuple[EngagementSpec, PveAssemblyContext]: 值冻结的委托 + 写回定位。

        Raises:
            ValueError: 当 event_index 在序列中越界时。
        """
        # 副本配置（敌方模板与缩放来源；无配置走默认模板）
        instance_config = None
        try:
            instance_config = loader.get_instance_config(session.region_id)
        except KeyError:
            pass

        # 1. 还原己方机体（回退链 snapshot_dict → mecha_id → 默认 rx78）
        player_state = session.squad_state.members[player_index]

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

        # 2. 时间回能 + 残血注入：算进快照拷贝，不触碰 PveEntityState（失败原子）
        hp_regen, en_regen = MothershipIntegrationService.calculate_regeneration(
            player_state.last_combat_time, now, mothership_config
        )
        player_snapshot.current_hp = min(player_state.max_hp, player_state.current_hp + hp_regen)
        player_snapshot.current_en = min(player_state.max_en, player_state.current_en + en_regen)
        player_snapshot.final_max_hp = player_state.max_hp
        player_snapshot.final_max_en = player_state.max_en

        # 3. 敌方：事件点模板实例化（模板缺失回退 mech_grunt）
        events = session.event_sequence.events
        if event_index < 0 or event_index >= len(events):
            raise ValueError(f"Event index {event_index} out of range in event sequence")

        current_event = events[event_index]
        enemy_template_id = current_event.event_id or "zaku2"

        # 解析敌方模板（Doc 13：由机体+驾驶员+缩放系数组成）
        enemy_mecha_id = enemy_template_id
        scaling = None

        if instance_config and enemy_template_id in instance_config.enemy_templates:
            template = instance_config.enemy_templates[enemy_template_id]
            enemy_mecha_id = template.mecha_id
            scaling = template.scaling

        enemy_config = loader.get_mecha_config(enemy_mecha_id) if enemy_mecha_id in getattr(loader, 'mechas', {}) else loader.get_mecha_config("mech_grunt")
        enemy_snapshot = mecha_factory.create_mecha_snapshot(enemy_config, weapon_configs=loader.equipments)

        _apply_scaling(enemy_snapshot, scaling)

        # 4. 敌方残血：已接敌过的事件点沿用残血；否则按模板值新建（先不落 session）
        if event_index in session.enemy_states:
            enemy_state = session.enemy_states[event_index]
            enemy_is_new = False
            enemy_pve_state = enemy_state.entity_state
            enemy_snapshot.current_hp = enemy_pve_state.current_hp
            enemy_snapshot.current_en = enemy_pve_state.current_en
            enemy_snapshot.final_max_hp = enemy_pve_state.max_hp
            enemy_snapshot.final_max_en = enemy_pve_state.max_en
        else:
            enemy_is_new = True
            enemy_pve_state = PveEntityState(
                entity_id=f"enemy_{event_index}",
                current_hp=enemy_snapshot.max_hp,
                current_en=enemy_snapshot.max_en,
                max_hp=enemy_snapshot.max_hp,
                max_en=enemy_snapshot.max_en,
                last_combat_time=now
            )
            enemy_state = PveEnemyState(
                event_index=event_index,
                entity_state=enemy_pve_state,
                enemy_template_id=enemy_template_id
            )

        spec = EngagementSpec(
            mecha_a=player_snapshot,
            mecha_b=enemy_snapshot,
            context=EngagementContext(source="pve"),
        )
        return spec, PveAssemblyContext(
            player_state=player_state,
            enemy_state=enemy_state,
            enemy_is_new=enemy_is_new,
            event=current_event,
            event_index=event_index,
        )
