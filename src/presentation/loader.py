"""
模板加载器 - Template Loader

职责：从 YAML 配置文件加载演出模板数据，
      将原始数据解析为 ActionBone 和 ReactionBone 对象。

在 CPS v5.0 四层架构中的位置：
- 作为 TemplateRegistry 的底层加载器
- 负责将 YAML 配置转换为内存中的 Python 对象

YAML 结构示例：
    action_bones:
      - bone_id: "slash_beam_saber"
        motion_style: "SLASH_LIGHT"
        damage_material: "ENERGY"
        text_fragments: ["{attacker} 挥舞{weapon}斩向{defender}"]
        anim_id: "anim_slash_beam"

    reaction_bones:
      - bone_id: "hit_energy_impact"
        channel: "IMPACT"
        damage_material: "ENERGY"
        text_fragments: ["{defender} 的{hit_part}被光束灼烧"]
        macro_motion: "MELEE_CLASH"
"""

import yaml
import os
from typing import List, Dict, Any, Tuple
from .template import ActionBone, ReactionBone
from .constants import TemplateTier, MotionStyle, Channel


class TemplateLoader:
    """
    模板加载器。

    从 YAML 配置文件加载 presentation 模板，
    将配置数据解析为 v5.0 架构所需的 ActionBone 和 ReactionBone 对象。

    设计原则：
    - 只加载 action_bones 和 reaction_bones
    - T0 脚本模板通过 ScriptedPresentationManager 代码直接创建，不走配置
    - 自动识别 T2.5_Decay 层模板（GENERIC + macro_motion != ANY）
    """

    @staticmethod
    def load_from_file(file_path: str) -> Tuple[List[ActionBone], List[ReactionBone]]:
        """从 YAML 文件加载 action_bones 和 reaction_bones。

        Args:
            file_path: YAML 配置文件路径

        Returns:
            (action_bones, reaction_bones) 元组，如果加载失败则返回空列表

        Raises:
            本方法捕获所有异常并打印警告，不会向上抛出
        """
        if not os.path.exists(file_path):
            print(f"[WARN] Template config not found: {file_path}")
            return [], []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not data:
                return [], []

            # 加载 action_bones
            action_bones = []
            if 'action_bones' in data:
                for item in data['action_bones']:
                    try:
                        bone = TemplateLoader._parse_action_bone(item)
                        action_bones.append(bone)
                    except Exception as e:
                        print(f"[ERROR] Failed to parse action_bone {item.get('bone_id', 'unknown')}: {e}")

            # 加载 reaction_bones
            reaction_bones = []
            if 'reaction_bones' in data:
                for item in data['reaction_bones']:
                    try:
                        bone = TemplateLoader._parse_reaction_bone(item)
                        reaction_bones.append(bone)
                    except Exception as e:
                        print(f"[ERROR] Failed to parse reaction_bone {item.get('bone_id', 'unknown')}: {e}")

            return action_bones, reaction_bones

        except Exception as e:
            print(f"[ERROR] Failed to load template file {file_path}: {e}")
            return [], []

    @staticmethod
    def _parse_action_bone(data: Dict[str, Any]) -> ActionBone:
        """解析 ActionBone 配置数据。

        Args:
            data: 包含 ActionBone 字段的字典

        Returns:
            解析后的 ActionBone 实例

        Raises:
            KeyError: 当必需的 bone_id 字段缺失时
        """
        # Parse motion_style
        style_str = data.get('motion_style', 'SHOOT_INSTANT')
        try:
            motion_style = MotionStyle[style_str] if style_str in MotionStyle.__members__ else MotionStyle(style_str)
        except ValueError:
            motion_style = MotionStyle.SHOOT_INSTANT

        # Parse tier
        tier_str = data.get('tier', 'T2_TACTICAL')
        try:
            tier = TemplateTier[tier_str]
        except KeyError:
            tier = TemplateTier.T2_TACTICAL

        return ActionBone(
            bone_id=data['bone_id'],
            motion_style=motion_style.value,
            damage_material=data.get('damage_material', 'ANY'),
            text_fragments=data.get('text_fragments', []),
            anim_id=data.get('anim_id', 'anim_default'),
            tier=tier,
            priority_score=data.get('priority_score', 0),
            cooldown=data.get('cooldown', 0),
            weight=data.get('weight', 1.0),
            tags=data.get('tags', [])
        )

    @staticmethod
    def _parse_reaction_bone(data: Dict[str, Any]) -> ReactionBone:
        """解析 ReactionBone 配置数据。

        Args:
            data: 包含 ReactionBone 字段的字典

        Returns:
            解析后的 ReactionBone 实例

        Note:
            自动识别 T2.5_Decay 层模板：如果 damage_material 为 GENERIC
            且 macro_motion 不为 ANY，则自动设为 T2_5_DECAY tier
        """
        # Parse channel
        channel_str = data.get('channel', 'IMPACT')
        try:
            channel = Channel[channel_str] if channel_str in Channel.__members__ else Channel(channel_str)
        except ValueError:
            channel = Channel.IMPACT

        # Parse tier (自动识别 T2.5_Decay 层)
        tier_str = data.get('tier', None)
        if tier_str:
            try:
                tier = TemplateTier[tier_str]
            except KeyError:
                tier = TemplateTier.T2_TACTICAL
        else:
            # 自动判断：GENERIC + macro_motion != ANY → T2.5_Decay 层
            damage_mat = data.get('damage_material', 'GENERIC')
            macro_motion = data.get('macro_motion', 'ANY')
            if damage_mat == 'GENERIC' and macro_motion != 'ANY':
                tier = TemplateTier.T2_5_DECAY
            else:
                tier = TemplateTier.T2_TACTICAL

        return ReactionBone(
            bone_id=data['bone_id'],
            channel=channel,
            damage_material=data.get('damage_material', 'GENERIC'),
            motion_style=data.get('motion_style', 'ANY'),
            text_fragments=data.get('text_fragments', []),
            vfx_ids=data.get('vfx_ids', []),
            sfx_ids=data.get('sfx_ids', []),
            macro_motion=data.get('macro_motion', 'ANY'),
            tier=tier,
            weight=data.get('weight', 1.0),
            tags=data.get('tags', []),
            attack_result=data.get('attack_result')
        )
