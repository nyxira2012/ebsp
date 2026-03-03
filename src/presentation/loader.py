import yaml
import os
from typing import List, Dict, Any, Tuple
from .template import ActionBone, ReactionBone
from .constants import TemplateTier, MotionStyle, Channel

class TemplateLoader:
    """
    Loads presentation templates from YAML configuration files.

    v5.0 架构：
    - 只加载 action_bones 和 reaction_bones
    - T0 脚本模板通过 ScriptedPresentationManager 代码直接创建
    """

    @staticmethod
    def load_from_file(file_path: str) -> Tuple[List[ActionBone], List[ReactionBone]]:
        """Loads action_bones and reaction_bones from a YAML file.

        Returns:
            (action_bones, reaction_bones) 元组
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
        """解析 ActionBone"""
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
        """解析 ReactionBone"""
        # Parse channel
        channel_str = data.get('channel', 'IMPACT')
        try:
            channel = Channel[channel_str] if channel_str in Channel.__members__ else Channel(channel_str)
        except ValueError:
            channel = Channel.IMPACT

        # Parse tier
        tier_str = data.get('tier', 'T2_TACTICAL')
        try:
            tier = TemplateTier[tier_str]
        except KeyError:
            tier = TemplateTier.T2_TACTICAL

        return ReactionBone(
            bone_id=data['bone_id'],
            channel=channel,
            damage_material=data.get('damage_material', 'GENERIC'),
            motion_style=data.get('motion_style', 'ANY'),
            text_fragments=data.get('text_fragments', []),
            vfx_ids=data.get('vfx_ids', []),
            sfx_ids=data.get('sfx_ids', []),
            tier=tier,
            weight=data.get('weight', 1.0),
            tags=data.get('tags', []),
            attack_result=data.get('attack_result')
        )
