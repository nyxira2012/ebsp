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

from src.config import Config
from src.factory import MechaFactory
from src.models import EnvironmentConfig, MechaSnapshot
from src.pve.models import PveEntityState, PveEnemyState, PveEvent, PveSessionData
from src.pve.services import MothershipIntegrationService
from src.skill_system.effect_factory import EffectFactory
from src.user.repository import UserAssetRepository
from src.core.factory import SnapshotFactory

from .engagement import EngagementContext, EngagementSpec

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.api.presentation_api import BattleRequest
    from src.database.models import User, UserMecha


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


def _apply_environment(env: EnvironmentConfig, mecha_a: MechaSnapshot, mecha_b: MechaSnapshot) -> None:
    """把环境声明的效果注入对应侧参战快照（Doc 16 §5.3 环境通道）。

    不走 TraitManager 链（该链无 src 生产调用方）——装配期显式注入是
    本设计的结构性护栏：效果只进本场快照，不落存档/共用机体表。
    按效果 id 幂等去重，重复注入不叠加。

    Args:
        env: 环境配置（grants 声明按侧授予的效果）。
        mecha_a: 我方快照（注入目标之一）。
        mecha_b: 敌方快照（注入目标之一）。
    """
    targets = {"a": (mecha_a,), "b": (mecha_b,), "all": (mecha_a, mecha_b)}
    for grant in env.grants:
        for snapshot in targets[grant.side]:
            for effect_id in grant.effect_ids:
                if any(e.id == effect_id for e in snapshot.effects):
                    continue
                # 空创建 = 未定义效果 id：不告警会静默变成零效果标签，
                # 环境承诺的保护（如力场免死）不存在却无迹可查（告警风格
                # 对齐 loader 加载/剔除告警）
                created = EffectFactory.create_trait_effects(effect_id)
                if not created:
                    # 「未注入」而非「已跳过」：与上方去重 continue 的 skip 消歧
                    print(f"环境 {env.id} 引用了未定义的效果，未注入: {effect_id} (side={grant.side})")
                    continue
                snapshot.effects.extend(created)


class BattleEntryService:
    """收发室：各界面进战斗的唯一装配口（Doc 15 §2/§4 红线 5）。

    只管"快照从哪来"，不做裁定也不写回——裁定走 Engagement，
    写回归各玩法（PVE 在 battle_bridge）。
    """

    @staticmethod
    async def build_debug(
        loader: Any,
        req: "BattleRequest",
        user: "User",
        db_session: "AsyncSession",
        owned_mechas: "list[UserMecha] | None" = None,
    ) -> EngagementSpec:
        """调试来源装配（POST /battle/simulate 专用，Doc 15 §5 消费方表）。

        静态配置直构快照；勾存档覆盖时用**玩家持有的机体**替换（simulate 已
        强制登录，Doc 7 v2.2 §11.1 批B——user=None 匿名分支废除）。

        2026-09-22 修订（用户裁决：编队功能暂不开放，所有对战/练习一律开
        玩家配备的机体）：出战机体自出战编队改为**持有清单取首台**（B 位
        次台、仅一台时复用首台），编队不参与战斗装配——无编队不再是降级
        或拦截条件，只要持有即出战。

        Args:
            loader: 静态资源加载器。
            req: 调试请求（双方机体 ID、入口标记、存档覆盖开关与可选规则环境）。
            user: 当前登录用户（simulate 401 收口后不再有匿名调用方）。
            db_session: 数据库会话（用户存档查询用）。
            owned_mechas: 预取的玩家持有机体列表——调用方已做出战资格校验
                （无机体 → 400 STARTER_NOT_CLAIMED）时透传，免二次查询；
                None 时按需自行取。

        Returns:
            EngagementSpec: 值冻结的战斗委托（source 取 req.route，Doc 14 v1.7）。

        Raises:
            KeyError: 机体 ID 不存在（由 handler 翻译为 404，Doc 14 §2）。
        """
        # 获取基础配置（未知 ID 时 get_mecha_config 抛 KeyError → 404 契约）
        config_a = loader.get_mecha_config(req.mecha_a_id)
        config_b = loader.get_mecha_config(req.mecha_b_id)

        # 创建基础快照
        mecha_a = MechaFactory.create_mecha_snapshot(config_a, weapon_configs=loader.equipments)
        mecha_b = MechaFactory.create_mecha_snapshot(config_b, weapon_configs=loader.equipments)

        # 勾了存档覆盖则以玩家持有机体替换（未勾覆盖时玩家机体用不上，不白查）
        if req.use_user_save_for_a or req.use_user_save_for_b:
            mechas = owned_mechas
            if mechas is None:
                mechas = await UserAssetRepository.list_user_mechas(db_session, user.id)

            if mechas:
                try:
                    factory = SnapshotFactory(loader, UserAssetRepository())

                    # A 位 = 持有首台；B 位 = 次台（仅一台时复用首台，平滑过渡保留）
                    if req.use_user_save_for_a:
                        mecha_a = await factory.create_combat_snapshot(db_session, user.id, mechas[0].id)

                    if req.use_user_save_for_b:
                        second_id = mechas[1].id if len(mechas) > 1 else mechas[0].id
                        mecha_b = await factory.create_combat_snapshot(db_session, user.id, second_id)

                except (ValueError, KeyError) as e:
                    # 养成数据无效/引用未知机体，忽略并使用默认配置
                    # （404 只指向请求字段；存档缺陷走降级语义，Doc 14 §2）
                    print(f"⚠️ 玩家出战数据无效，使用默认配置: {e}")

        # 规则环境（Doc 16 §5.3）：存档覆盖之后、值冻结之前注入——降级到
        # 演示配置时力场同样生效；快照随 EngagementSpec 深拷贝冻结，效果
        # 只活在委托副本里。未知环境 ID 的 KeyError 走上层 404 通道（同机体）。
        if req.environment_id is not None:
            _apply_environment(
                loader.get_environment_config(req.environment_id), mecha_a, mecha_b
            )

        return EngagementSpec(
            mecha_a=mecha_a,
            mecha_b=mecha_b,
            # route 由客户端声明（debug/training，练习场发 training——Doc 16 §2.1；
            # BattleRequest 的 Literal 校验已挡住 pve/pvp 伪造）
            context=EngagementContext(
                source=req.route,
                environment_id=req.environment_id,
            ),
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
        instance_config: Any = None,
    ) -> tuple[EngagementSpec, PveAssemblyContext]:
        """PVE 接敌装配（Doc 15 §5：会话还原 + 事件点实例化）。

        我方从 locked_config 还原（snapshot_dict → mecha_id，缺配即
        ValueError），时间回能与残血注入全部算进快照——不触碰
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
            instance_config: 副本配置（敌方模板与缩放来源），由调用方
                加载一次传入；None 时走默认敌方模板。

        Returns:
            tuple[EngagementSpec, PveAssemblyContext]: 值冻结的委托 + 写回定位。

        Raises:
            ValueError: 当 event_index 在序列中越界时。
        """
        # 1. 还原己方机体（snapshot_dict → mecha_id，双链都缺即缺陷：
        # 默认机体静默回退已废除——Doc 7 v2.2 §11.2 rx78 假 ID 地雷拆除，
        # enter 期 400 后不可达，此处显式失败）
        player_state = session.squad_state.members[player_index]

        mechas_config = session.squad_state.locked_config.get("mechas", [])
        if player_index >= len(mechas_config):
            raise ValueError(
                f"PVE 锁定配置缺成员快照（成员下标 {player_index}，共 {len(mechas_config)} 台）"
            )

        m_config_data = mechas_config[player_index]
        snapshot_dict = m_config_data.get("snapshot_dict")

        if snapshot_dict:
            player_snapshot = MechaSnapshot.model_validate(snapshot_dict)
        else:
            mecha_id = m_config_data.get("mecha_id")
            if not mecha_id:
                raise ValueError("PVE 锁定配置缺 mecha_id 且无快照，无法还原机体")
            try:
                mecha_config = loader.get_mecha_config(mecha_id)
            except KeyError:
                # 引用未知机体同属缺陷级，统一 ValueError（Doc 7 v2.2 §11.2）
                raise ValueError(f"PVE 锁定配置引用未知机体: {mecha_id}")
            player_snapshot = mecha_factory.create_mecha_snapshot(mecha_config, weapon_configs=loader.equipments)

        # 2. 时间回能 + 残血注入：算进快照拷贝，不触碰 PveEntityState（失败原子）
        hp_regen, en_regen = MothershipIntegrationService.calculate_regeneration(
            player_state.last_combat_time, now, mothership_config
        )
        player_snapshot.current_hp = min(player_state.max_hp, player_state.current_hp + hp_regen)
        player_snapshot.current_en = min(player_state.max_en, player_state.current_en + en_regen)
        player_snapshot.final_max_hp = player_state.max_hp
        player_snapshot.final_max_en = player_state.max_en

        # 3. 敌方：事件点模板实例化（模板缺失回退默认杂兵）
        events = session.event_sequence.events
        if event_index < 0 or event_index >= len(events):
            raise ValueError(f"Event index {event_index} out of range in event sequence")

        current_event = events[event_index]
        enemy_template_id = current_event.event_id or Config.DEFAULT_ENEMY_TEMPLATE_ID

        # 解析敌方模板（Doc 13：由机体+驾驶员+缩放系数组成）
        enemy_mecha_id = enemy_template_id
        scaling = None

        if instance_config and enemy_template_id in instance_config.enemy_templates:
            template = instance_config.enemy_templates[enemy_template_id]
            enemy_mecha_id = template.mecha_id
            scaling = template.scaling

        try:
            enemy_config = loader.get_mecha_config(enemy_mecha_id)
        except KeyError:
            enemy_config = loader.get_mecha_config(Config.DEFAULT_ENEMY_MECHA_ID)
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
