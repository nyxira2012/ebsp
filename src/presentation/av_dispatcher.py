"""
L4 视听调度层 - 影视级调色

职责：将文字翻译成镜头与节奏。
- 规则树驱动的摄像机选择
- 语义化时间轴自适应
"""

from typing import List, Optional, Callable, Tuple
from dataclasses import dataclass

from .models import RawAttackEvent, PresentationAttackEvent
from .constants import Channel, TemplateTier
from .intent_extractor import VisualIntent


@dataclass
class CameraRule:
    """摄像机选择规则"""
    priority: int
    condition: Callable[[RawAttackEvent, Channel], bool]
    camera_id: str
    description: str = ""


class AVDispatcher:
    """
    AV 调度器 - 将原始事件转换为完整的视听演出事件。

    特性：
    1. 规则树驱动的摄像机选择
    2. 语义化时间轴自适应（根据结果和意图调整延迟）
    3. 统一处理 Action 和 Reaction 事件的生成
    """

    # Threshold constants for camera selection
    HEAVY_DAMAGE_THRESHOLD = 500      # Damage threshold for heavy camera shake
    LONG_RANGE_THRESHOLD = 800         # Distance threshold for long shot camera
    CLOSE_RANGE_THRESHOLD = 100        # Distance threshold for close-up camera
    CLOSE_COMBAT_DODGE_THRESHOLD = 200 # Distance threshold for close combat dodge camera

    # 摄像机选择规则表（优先级从高到低）
    CAMERA_RULES: List[CameraRule] = [
        CameraRule(
            priority=100,
            condition=lambda e, ch: ch == Channel.FATAL,
            camera_id="cam_dramatic_zoom",
            description="致死：戏剧性缩放"
        ),
        CameraRule(
            priority=90,
            condition=lambda e, ch: e.attack_result == "CRIT",
            camera_id="cam_dramatic_zoom",
            description="暴击：戏剧性缩放"
        ),
        CameraRule(
            priority=85,
            condition=lambda e, ch: e.attack_result == "DODGE" and e.distance < 200,
            camera_id="cam_close_combat_dodge",
            description="近战闪避"
        ),
        CameraRule(
            priority=80,
            condition=lambda e, ch: e.distance > 800,
            camera_id="cam_long_shot",
            description="远距离：远景"
        ),
        CameraRule(
            priority=75,
            condition=lambda e, ch: e.distance < 100,
            camera_id="cam_close_up",
            description="近距离：特写"
        ),
        CameraRule(
            priority=70,
            condition=lambda e, ch: e.attack_result == "DODGE",
            camera_id="cam_tracking_evade",
            description="闪避：追踪镜头"
        ),
        CameraRule(
            priority=60,
            condition=lambda e, ch: e.damage > 500,
            camera_id="cam_shake_heavy",
            description="大伤害：剧烈震动"
        ),
        CameraRule(
            priority=55,
            condition=lambda e, ch: e.attack_result in ("HIT", "BLOCK"),
            camera_id="cam_shake_light",
            description="普通命中：轻微震动"
        ),
        CameraRule(
            priority=0,
            condition=lambda e, ch: True,
            camera_id="cam_default",
            description="默认镜头"
        ),
    ]

    # 时间轴基准延迟
    BASE_DELAY = 1.5

    def __init__(self):
        pass

    def dispatch(
        self,
        raw_event: RawAttackEvent,
        action_text: str,
        reaction_text: str,
        channel: Channel,
        action_anim_id: Optional[str] = None,
        reaction_anim_id: Optional[str] = None,
        vfx_ids: Optional[List[str]] = None,
        sfx_ids: Optional[List[str]] = None,
        hit_location: Optional[str] = None,
        action_template_id: Optional[str] = None,
        reaction_template_id: Optional[str] = None,
    ) -> Tuple[PresentationAttackEvent, PresentationAttackEvent]:
        """
        调度生成 Action 和 Reaction 两个事件。

        Args:
            hit_location: 受击部位（由 TextAssembler.DhlMapper 提供的中文部位名）

        Returns:
            (action_event, reaction_event) 元组
        """
        # 选择摄像机
        action_cam = self._select_camera(raw_event, channel, is_action=True)
        reaction_cam = self._select_camera(raw_event, channel, is_action=False)

        # 计算时间轴
        action_ts = 0.0
        reaction_ts = self._calculate_timestamp(raw_event, channel)

        # 构建 Action 事件
        action_event = PresentationAttackEvent(
            event_type="ACTION",
            round_number=raw_event.round_number,
            timestamp=action_ts,
            text=action_text,
            tier=TemplateTier.T2_TACTICAL,  # 默认战术层级
            anim_id=action_anim_id or self._get_default_action_anim(raw_event),
            camera_cam=action_cam,
            vfx_ids=vfx_ids or [],
            sfx_ids=sfx_ids or [],
            template_id=action_template_id or "",
            raw_event=raw_event,
            attacker_name=raw_event.attacker_name,
            defender_name=raw_event.defender_name,
            weapon_name=raw_event.weapon_name,
            attack_result=raw_event.attack_result,
        )

        # 构建 Reaction 事件
        reaction_event = PresentationAttackEvent(
            event_type="REACTION",
            round_number=raw_event.round_number,
            timestamp=reaction_ts,
            text=reaction_text,
            tier=TemplateTier.T2_TACTICAL,
            anim_id=reaction_anim_id or self._get_default_reaction_anim(raw_event, channel),
            camera_cam=reaction_cam,
            vfx_ids=vfx_ids or [],
            sfx_ids=sfx_ids or [],
            damage_display=self._get_damage_display(raw_event, channel),
            hit_location=hit_location or "body",
            template_id=reaction_template_id or "",
            raw_event=raw_event,
            attacker_name=raw_event.attacker_name,
            defender_name=raw_event.defender_name,
            weapon_name=raw_event.weapon_name,
            attack_result=raw_event.attack_result,
        )

        return action_event, reaction_event

    def _select_camera(self, event: RawAttackEvent, channel: Channel, is_action: bool) -> str:
        """根据规则树选择摄像机"""
        for rule in sorted(self.CAMERA_RULES, key=lambda r: -r.priority):
            if rule.condition(event, channel):
                return rule.camera_id
        return "cam_default"

    def _calculate_timestamp(self, event: RawAttackEvent, channel: Channel) -> float:
        """
        语义化时间轴自适应。

        根据以下因素调整延迟：
        - 暴击增加 0.5s 戏剧停顿
        - 光束武器持续 0.3s
        - 致死增加 0.4s 冲击感
        """
        delay = self.BASE_DELAY

        # 暴击增益
        if event.attack_result == "CRIT":
            delay += 0.5

        # 致死冲击
        if channel == Channel.FATAL:
            delay += 0.4

        # 意图相关延迟（根据武器类型）
        from .intent_extractor import IntentExtractor
        intent = IntentExtractor.extract_intent(event.weapon_type, event.weapon_tags)

        if intent in (VisualIntent.BEAM_MASSIVE, VisualIntent.AOE_BURST):
            delay += 0.3  # 光束武器/地图武器需要更多飞行时间
        elif intent == VisualIntent.PROJECTILE_RAIN:
            delay += 0.2  # 导弹齐射

        return delay

    def _get_default_action_anim(self, event: RawAttackEvent) -> str:
        """获取默认攻击动画"""
        from .intent_extractor import IntentExtractor
        intent = IntentExtractor.extract_intent(event.weapon_type, event.weapon_tags)

        anim_map = {
            VisualIntent.SLASH_LIGHT: "anim_slash_fast",
            VisualIntent.SLASH_HEAVY: "anim_slash_heavy",
            VisualIntent.STRIKE_BLUNT: "anim_strike",
            VisualIntent.BEAM_INSTANT: "anim_rifle_shoot",
            VisualIntent.BEAM_MASSIVE: "anim_mega_beam",
            VisualIntent.PROJECTILE_SINGLE: "anim_shoot_single",
            VisualIntent.PROJECTILE_RAIN: "anim_missile_rain",
            VisualIntent.IMPACT_MASSIVE: "anim_collision",
            VisualIntent.PSYCHO_WAVE: "anim_psycho",
            VisualIntent.AOE_BURST: "anim_aoe_burst",
        }
        return anim_map.get(intent, "anim_default_attack")

    def _get_default_reaction_anim(self, event: RawAttackEvent, channel: Channel) -> str:
        """获取默认反应动画"""
        if channel == Channel.FATAL:
            return "anim_explosion_fatal"
        if channel == Channel.EVADE:
            return "anim_evade"
        if event.attack_result == "BLOCK":
            return "anim_block"
        if event.attack_result == "CRIT":
            return "anim_hit_critical"

        # 根据物理类选择
        physics = getattr(event, 'physics_class', 'Impact')
        anim_map = {
            "Energy": "anim_hit_energy",
            "Kinetic": "anim_hit_kinetic",
            "Blade": "anim_hit_blade",
            "Impact": "anim_hit_impact",
        }
        return anim_map.get(physics, "anim_hit_default")

    def _get_damage_display(self, event: RawAttackEvent, channel: Channel) -> int:
        """
        获取显示的伤害值。

        规则：
        - EVADE/MISS/DODGE: 0
        - PARRY: 0（招架完全避开）
        - BLOCK: 实际伤害（格挡会受伤害但减少）
        - FATAL/HIT/CRIT: 实际伤害
        """
        if channel == Channel.EVADE:
            return 0
        if event.attack_result in ("PARRY", "MISS", "DODGE"):
            return 0  # 招架、未命中、闪避完全无伤害
        return event.damage
