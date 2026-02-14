"""
演出系统数据模型
定义原始事件（RawEvent）和演出事件（PresentationEvent）
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional
from datetime import datetime


@dataclass
class RawAttackEvent:
    """原始攻击事件 - 战斗引擎生成的纯数据事件

    该事件由战斗系统（Logic Layer）生成，不包含任何文本描述，
    仅记录客观的战斗数据，用于后续转换为演出事件。

    Attributes:
        round_number: 当前回合数
        attacker_id: 攻击方机体ID
        defender_id: 防御方机体ID
        attacker_name: 攻击方机体名称
        defender_name: 防御方机体名称
        weapon_id: 使用的武器ID
        weapon_name: 武器名称
        weapon_type: 武器类型枚举值 (MELEE/RIFLE/AWAKENING等)
        attack_result: 攻击判定结果 (HIT/MISS/CRIT/DODGE/PARRY/BLOCK)
        damage: 实际造成的伤害值
        distance: 交战距离（米）
        attacker_will_delta: 攻击方气力变化
        defender_will_delta: 防御方气力变化
        initiative_holder: 先手方ID
        initiative_reason: 先手原因枚举值
        triggered_skills: 触发的技能ID列表
        is_first_attack: 是否为先攻（True）或反击（False）
    """

    round_number: int
    attacker_id: str
    defender_id: str
    attacker_name: str
    defender_name: str
    weapon_id: str
    weapon_name: str
    weapon_type: str
    attack_result: str
    damage: int
    distance: int
    attacker_will_delta: int
    defender_will_delta: int
    initiative_holder: str
    initiative_reason: str
    triggered_skills: List[str] = field(default_factory=list)
    is_first_attack: bool = True


@dataclass
class PresentationAttackEvent:
    """演出攻击事件 - 包含文本、视觉效果的完整演出数据

    该事件由转换器（Mapping Layer）生成，包含文本描述、动画ID、
    特效列表等完整的演出信息，可直接用于前端渲染。

    Attributes:
        event_type: 事件类型标识，固定为 "ATTACK"
        timestamp: 事件时间戳
        round_number: 回合数
        is_first_attack: 是否为先攻

        # 文本演出相关
        text: 完整的描述文本（已填充占位符）
        display_tags: 需要高亮显示的标签列表，如 ["暴击", "NT感知"]
        section_type: 文本段落类型 (CONTEXT/ACTION_FIRST/ACTION_SECOND/SUMMARY)

        # 视觉演出相关（前端用）
        anim_id: 动画资源ID，如 "anim_beam_rifle_fire"
        camera_cam: 运镜方式，如 "close_up_dynamic"
        vfx_ids: 视觉特效ID列表，如 ["vfx_explosion_small", "vfx_cam_shake"]
        sfx_ids: 音效ID列表

        # 数据快照（用于UI显示）
        damage_display: 显示的伤害数字
        hit_location: 命中部位描述，如 "左侧肩甲"
        attacker_name: 攻击方名称
        defender_name: 防御方名称
        weapon_name: 武器名称
        attack_result: 攻击结果字符串
        range_tag: 距离区间标签（如 "近距离"、"中距离"）

        # 原始数据引用（用于调试）
        raw_event: 关联的原始攻击事件
    """

    # 基础信息
    event_type: str = "ATTACK"
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    round_number: int = 0
    is_first_attack: bool = True

    # 文本演出
    text: str = ""
    display_tags: List[str] = field(default_factory=list)
    section_type: str = "ACTION"  # CONTEXT, ACTION_FIRST, ACTION_SECOND, SUMMARY

    # 视觉演出
    anim_id: str = "default"
    camera_cam: str = "default"
    vfx_ids: List[str] = field(default_factory=list)
    sfx_ids: List[str] = field(default_factory=list)

    # 数据快照
    damage_display: int = 0
    hit_location: str = ""
    attacker_name: str = ""
    defender_name: str = ""
    weapon_name: str = ""
    attack_result: str = ""
    range_tag: str = ""

    # 原始数据
    raw_event: Optional[RawAttackEvent] = None


@dataclass
class PresentationRoundEvent:
    """演出回合事件 - 包含一个完整回合的所有演出信息

    一个回合包含四个标准段落：
    - L1: 环境和先手信息
    - L2: 先手方攻击
    - L3: 后手方反击
    - L4: 回合总结

    Attributes:
        round_number: 回合数
        context_event: 环境段落事件 (L1)
        first_attack_event: 先手方攻击事件 (L2)
        second_attack_event: 后手方反击事件 (L3)
        summary_event: 回合总结事件 (L4)
    """

    round_number: int
    context_event: Optional[PresentationAttackEvent] = None
    first_attack_event: Optional[PresentationAttackEvent] = None
    second_attack_event: Optional[PresentationAttackEvent] = None
    summary_event: Optional[PresentationAttackEvent] = None

    def get_all_events(self) -> List[PresentationAttackEvent]:
        """获取本回合的所有演出事件（按顺序）"""
        events = []
        if self.context_event:
            events.append(self.context_event)
        if self.first_attack_event:
            events.append(self.first_attack_event)
        if self.second_attack_event:
            events.append(self.second_attack_event)
        if self.summary_event:
            events.append(self.summary_event)
        return events
