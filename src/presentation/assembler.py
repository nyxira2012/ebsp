"""
L3 动态丰满层 - 原子化组合 + DHL + SVI

职责：让每一句话都独一无二。
- 三段式拼装：Text = [启动姿态] + [执行过程] + [结果反馈]
- DHL：动态受击部位映射
- SVI：语义化变量注入
"""

import random
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass

from .models import RawAttackEvent
from .constants import Channel
from .template import ActionBone, ReactionBone


class DhlMapper:
    """
    Dynamic Hit Location Mapper - 动态受击部位映射

    核心理念：【视觉精准性，击中而非笼统】
    - FATAL: 锁定关键节点（驾驶舱、动力炉）
    - CRIT: 锁定精密部位（主摄像机、推进器端口）
    - HIT: 锁定外甲
    """

    # 部位映射表
    # 注意：部位名不要包含"装甲"、"盾牌"等词，避免与模板拼接时重复
    _LOCATION_MAP: Dict[str, List[str]] = {
        "FATAL": ["驾驶舱", "动力炉", "核心反应堆"],
        "CRIT": ["主摄像机", "推进器端口", "关节部位", "传感器阵列"],
        "HIT": ["机体侧翼", "腰部", "肩部", "机头"],
        "BLOCK": ["盾牌", "前部", "防御力场"],
        "EVADE": [],  # 没有受击部位
    }

    @classmethod
    def get_hit_location(cls, channel: Channel, attack_result: str) -> Optional[str]:
        """
        根据频道和攻击结果获取受击部位。

        Returns:
            部位名称，或 None（如果是 EVADE）
        """
        if channel == Channel.EVADE:
            return None

        # 优先级：FATAL > CRIT/PARRY/BLOCK > HIT
        # 致命频道优先使用致命部位
        if channel == Channel.FATAL:
            pool = cls._LOCATION_MAP["FATAL"]
        elif attack_result == "CRIT":
            pool = cls._LOCATION_MAP["CRIT"]
        elif attack_result in ("BLOCK", "PARRY"):
            pool = cls._LOCATION_MAP["BLOCK"]
        else:
            pool = cls._LOCATION_MAP["HIT"]

        return random.choice(pool) if pool else None


class DamageGrader:
    """
    损伤量级分级器

    根据伤害值进行分级（使用绝对伤害基准）：
    - 0: 无伤
    - 1-800: 轻伤（轻微擦伤）
    - 801-2000: 中伤（明显损伤）
    - 2001-4000: 重伤（严重损伤）
    - >4000: 濒死（致命打击）

    注意：如果提供了 max_hp，则使用百分比分级；
          否则使用绝对伤害值分级（默认基准 HP=10000）。
    """

    # 默认机体 HP 基准值
    _DEFAULT_HP = 10000

    @classmethod
    def get_grade(cls, damage: int, max_hp: int = 0) -> str:
        """获取损伤量级描述"""
        if damage <= 0:
            return "无伤"

        # 如果提供了有效的 max_hp，使用百分比分级
        if max_hp > 0:
            ratio = damage / max_hp
            if ratio < 0.08:
                return "轻伤"
            elif ratio < 0.25:
                return "中伤"
            elif ratio < 0.5:
                return "重伤"
            else:
                return "濒死"
        else:
            # 否则使用绝对伤害值分级（基于默认 HP）
            ratio = damage / cls._DEFAULT_HP
            if ratio < 0.08:
                return "轻伤"
            elif ratio < 0.25:
                return "中伤"
            elif ratio < 0.5:
                return "重伤"
            else:
                return "濒死"

    @classmethod
    def get_hp_status_words(cls, hp_after: int, max_hp: int) -> List[str]:
        """根据剩余 HP 百分比获取状态词"""
        if max_hp <= 0:
            return ["状态未知"]

        ratio = hp_after / max_hp

        if ratio <= 0:
            return ["机能停止", "彻底损毁"]
        elif ratio < 0.2:
            return ["濒临崩溃", "勉强支撑", "警报大作"]
        elif ratio < 0.5:
            return ["中度损伤", "运转尚可"]
        elif ratio < 0.8:
            return ["轻微损伤", "状态良好"]
        else:
            return ["几乎无损", "完好如初"]


class SVI:
    """
    Semantic Variable Injector - 语义化变量注入

    处理变量替换：
    - {attacker}, {defender}, {weapon}: 基础信息
    - {hit_part}: 受击部位（由 DHL 提供）
    - {skill_name}: 优先精神指令，其次技能，最后武器
    - {damage_grade}: 损伤量级
    - {status_word}: 状态描述词
    """

    @classmethod
    def build_variables(
        cls,
        event: RawAttackEvent,
        hit_part: Optional[str] = None
    ) -> Dict[str, str]:
        """构建变量字典用于 str.format()"""
        return {
            "attacker": event.attacker_name,
            "defender": event.defender_name,
            "weapon": event.weapon_name,
            # 别名适配 (MDDC 模板建议使用全名)
            "attacker_name": event.attacker_name,
            "defender_name": event.defender_name,
            "weapon_name": event.weapon_name,
            "hit_part": hit_part or "目标",
            "skill_name": cls._pick_skill_label(event),
            "damage_grade": DamageGrader.get_grade(event.damage, event.defender_max_hp),
            "status_word": random.choice(DamageGrader.get_hp_status_words(
                event.defender_hp_after, event.defender_max_hp
            )),
        }

    @classmethod
    def _pick_skill_label(cls, event: RawAttackEvent) -> str:
        """
        优先返回精神指令名，其次技能名，最后武器名。
        这是文档机制 6 的核心策略。
        """
        # 优先精神指令（热血、魂等）
        spirit_commands = getattr(event, 'spirit_commands', [])
        if spirit_commands:
            # 简单的中文化映射
            cmd_map = {
                "hot_blood": "热血",
                "soul": "魂",
                "flash": "闪身",
                "trust": "信赖",
                "hope": "希望",
            }
            cmd = spirit_commands[0]
            result = cmd_map.get(cmd, cmd)
            if result:
                return result

        # 其次触发技能名
        if event.triggered_skills:
            return event.triggered_skills[0]

        # 最后返回武器名
        return event.weapon_name


class TextAssembler:
    """
    文本组装器 - 三段式拼装

    拼装公式：
    action_text = [启动姿态] + [执行过程] + [意图标签]
    react_text  = [受击部位] + [物理反馈] + [状态反馈]
    """

    def assemble(
        self,
        action_bone: Optional[ActionBone],
        react_bone: Optional[ReactionBone],
        event: RawAttackEvent,
        channel: Channel
    ) -> Tuple[str, str, Optional[str]]:
        """
        组装最终的行动文本和反应文本。

        Returns:
            (action_text, reaction_text, hit_part) 元组
        """
        # 获取受击部位
        hit_part = DhlMapper.get_hit_location(channel, event.attack_result)

        # 构建变量字典
        variables = SVI.build_variables(event, hit_part)

        # 组装 Action 文本
        action_text = self._assemble_action(action_bone, event, variables)

        # 组装 Reaction 文本
        reaction_text = self._assemble_reaction(react_bone, event, channel, variables)

        return action_text, reaction_text, hit_part

    def _assemble_action(
        self,
        bone: Optional[ActionBone],
        event: RawAttackEvent,
        variables: Dict[str, str]
    ) -> str:
        """组装攻击方文本"""
        if bone and bone.text_fragments:
            text = random.choice(bone.text_fragments)
        else:
            # 默认兜底
            text = "{attacker}使用{weapon}展开了攻击！"

        # 变量注入
        try:
            return text.format(**variables)
        except KeyError:
            return text

        # 变量注入
        try:
            return text.format(**variables)
        except KeyError:
            return text

    def _assemble_reaction(
        self,
        bone: Optional[ReactionBone],
        event: RawAttackEvent,
        channel: Channel,
        variables: Dict[str, str]
    ) -> str:
        """
        组装防御方文本。

        逻辑优先级：
        1. 优先使用传入的 bone 中的片段
        2. 变量注入
        3. 附加判定结果和伤害数值
        """
        if bone and bone.text_fragments:
            base_text = random.choice(bone.text_fragments)
        else:
            # 理论上 Bidder 已经保证了有骨架提供，这里作为防御性兜底
            if event.is_lethal:
                base_text = "{defender}被彻底摧毁了。"
            elif event.attack_result == "CRIT":
                base_text = "{defender}遭受了沉重打击！"
            elif event.attack_result == "BLOCK":
                base_text = "{defender}挡住了攻击。"
            elif event.attack_result == "PARRY":
                base_text = "{defender}招架了攻击。"
            elif event.attack_result == "DODGE":
                base_text = "{defender}巧妙地躲开了。"
            elif event.attack_result == "MISS":
                base_text = "攻击没能命中{defender}。"
            else:
                base_text = "{defender}被击中了。"

        # 变量注入
        try:
            base_text = base_text.format(**variables)
        except KeyError:
            pass

        # 统一附加判定结果和伤害信息
        result_map = {
            "CRIT": "暴击",
            "HIT": "命中",
            "BLOCK": "格挡",
            "PARRY": "招架",
            "DODGE": "躲闪",
            "MISS": "未命中"
        }
        result_name = result_map.get(event.attack_result, event.attack_result)
        damage = event.damage
        
        # 根据是否致死选择图标
        icon = " 💀" if event.is_lethal else ""
        
        if damage > 0:
            # 自动附加伤害基准
            damage_grade = DamageGrader.get_grade(damage, event.defender_max_hp)
            base_text += f"（{result_name}！-{damage}，{damage_grade}{icon}）"
        else:
            base_text += f"（{result_name}！{icon}）"

        return base_text
