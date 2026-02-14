"""
事件转换器 - 将原始战斗事件转换为演出事件
负责从配置文件中读取模板，填充占位符，生成完整的演出数据
"""

import random
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from .models import RawAttackEvent, PresentationAttackEvent


class EventMapper:
    """事件转换器 - 核心映射逻辑

    职责：
    1. 加载演出配置文件 (presentation.yaml)
    2. 根据 [武器类型][攻击结果] 选择文本模板
    3. 填充模板占位符 ({attacker}, {damage}, {location} 等)
    4. 附加视觉资源ID (动画、特效、音效)
    5. 生成完整的 PresentationAttackEvent

    使用方式：
        mapper = EventMapper()
        pres_event = mapper.map_attack(raw_event)
    """

    # 命中部位库 - 用于生成 HIT/CRIT 事件的命中部位描述
    HIT_LOCATIONS = [
        "装甲连接部", "驾驶舱外壁", "动力管路", "胸部装甲",
        "左侧肩甲", "右侧肩甲", "腿部关节", "背包推进器",
        "武器挂架", "能量分配器"
    ]

    # CRIT 高概率部位
    CRIT_LOCATIONS = ["头部传感器", "能量分配器", "驾驶舱", "动力核心"]

    def __init__(self, config_path: Optional[str] = None):
        """初始化事件转换器

        Args:
            config_path: 配置文件路径，默认为项目根目录下的 config/presentation.yaml
        """
        if config_path is None:
            # 默认配置文件路径
            project_root = Path(__file__).parent.parent.parent
            config_path = str(project_root / "config" / "presentation.yaml")

        self.config_path = Path(config_path)
        self.config: Dict = self._load_config()

    def _load_config(self) -> Dict:
        """加载 YAML 配置文件

        Returns:
            配置字典，包含 templates 和 mappings
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            # 如果配置文件不存在，返回空配置（使用默认值）
            print(f"[警告] 未找到演出配置文件: {self.config_path}")
            return {"templates": {}, "mappings": {}}

    def map_attack(self, raw_event: RawAttackEvent) -> PresentationAttackEvent:
        """将原始攻击事件映射为演出攻击事件

        映射流程：
        1. 确定文本段落类型和模板选择路径
        2. 从配置中选择合适的文本模板
        3. 随机选择命中部位（如果是 HIT/CRIT）
        4. 填充模板占位符
        5. 从配置中获取动画、特效、音效ID
        6. 组装完整的 PresentationAttackEvent

        Args:
            raw_event: 原始攻击事件

        Returns:
            演出攻击事件
        """
        # 1. 选择模板
        template = self._select_template(raw_event)

        # 2. 准备模板变量
        template_vars = self._prepare_template_vars(raw_event)

        # 3. 填充模板
        text = template.format(**template_vars)

        # 4. 获取视觉资源ID
        anim_id = self._get_animation_id(raw_event)
        camera_cam = self._get_camera_id(raw_event)
        vfx_ids = self._get_vfx_ids(raw_event)

        # 5. 组装演出事件
        pres_event = PresentationAttackEvent(
            round_number=raw_event.round_number,
            is_first_attack=raw_event.is_first_attack,
            text=text,
            display_tags=self._get_display_tags(raw_event),
            section_type=self._get_section_type(raw_event),
            anim_id=anim_id,
            camera_cam=camera_cam,
            vfx_ids=vfx_ids,
            sfx_ids=self._get_sfx_ids(raw_event),
            damage_display=raw_event.damage,
            hit_location=template_vars.get("location", ""),
            attacker_name=raw_event.attacker_name,
            defender_name=raw_event.defender_name,
            weapon_name=raw_event.weapon_name,
            attack_result=raw_event.attack_result,
            range_tag=template_vars.get("range_tag", ""),
            raw_event=raw_event
        )

        return pres_event

    def _select_template(self, raw_event: RawAttackEvent) -> str:
        """根据武器类型和攻击结果选择文本模板

        模板选择路径：
        - 攻击事件: templates.attack.[WEAPON_TYPE].[RESULT]
        - 优先使用配置文件中的模板
        - 如果未找到，使用默认模板

        Args:
            raw_event: 原始攻击事件

        Returns:
            文本模板字符串
        """
        templates = self.config.get("templates", {})
        attack_templates = templates.get("attack", {})

        # 尝试获取 [武器类型][结果] 的模板
        weapon_templates = attack_templates.get(raw_event.weapon_type, {})
        template_list = weapon_templates.get(raw_event.attack_result, [])

        if template_list and len(template_list) > 0:
            # 随机选择一个模板
            return random.choice(template_list)

        # 如果没有找到，使用默认模板
        return "{attacker}使用{weapon}攻击{defender}，{result}！伤害 {damage}"

    def _prepare_template_vars(self, raw_event: RawAttackEvent) -> Dict[str, str]:
        """准备模板变量

        生成文本模板中所有占位符的实际值：
        - {attacker}: 攻击方名称
        - {defender}: 防御方名称
        - {weapon}: 武器名称
        - {damage}: 伤害值
        - {result}: 攻击结果
        - {location}: 命中部位（仅HIT/CRIT）
        - {distance}: 交战距离
        - {range_tag}: 距离区间标签

        Args:
            raw_event: 原始攻击事件

        Returns:
            模板变量字典
        """
        vars_dict = {
            "attacker": raw_event.attacker_name,
            "defender": raw_event.defender_name,
            "weapon": raw_event.weapon_name,
            "damage": raw_event.damage,
            "result": raw_event.attack_result,
            "distance": raw_event.distance,
            "range_tag": self._get_range_tag(raw_event.distance)
        }

        # 仅对 HIT/CRIT 添加命中部位
        if raw_event.attack_result in ["HIT", "暴击", "CRIT"]:
            vars_dict["location"] = self._get_hit_location(raw_event.attack_result == "CRIT")

        return vars_dict

    def _get_hit_location(self, is_crit: bool) -> str:
        """随机选择命中部位

        Args:
            is_crit: 是否为暴击（暴击时优先选择关键部位）

        Returns:
            命中部位描述字符串
        """
        if is_crit and random.random() < 0.6:
            # 暴击时60%概率命中关键部位
            return random.choice(self.CRIT_LOCATIONS)
        return random.choice(self.HIT_LOCATIONS)

    def _get_range_tag(self, distance: int) -> str:
        """根据距离返回区间标签

        Args:
            distance: 交战距离（米）

        Returns:
            距离标签字符串
        """
        if distance < 500:
            return "极近距离"
        elif distance < 1500:
            return "近距离"
        elif distance < 3000:
            return "中距离"
        elif distance < 6000:
            return "远距离"
        else:
            return "超远距离"

    def _get_animation_id(self, raw_event: RawAttackEvent) -> str:
        """获取动画资源ID

        从配置文件中读取 mappings.animations.[weapon_id].[result]
        如果未找到，返回默认动画ID

        Args:
            raw_event: 原始攻击事件

        Returns:
            动画资源ID字符串
        """
        mappings = self.config.get("mappings", {})
        anim_mappings = mappings.get("animations", {})

        # 尝试获取武器特定的动画
        weapon_anims = anim_mappings.get(raw_event.weapon_type.lower(), {})
        if weapon_anims:
            # 优先使用结果特定的动画
            result_key = raw_event.attack_result.lower()
            if result_key in weapon_anims:
                return weapon_anims[result_key]
            # 否则使用默认动画
            if "default" in weapon_anims:
                return weapon_anims["default"]

        return "anim_default"

    def _get_camera_id(self, raw_event: RawAttackEvent) -> str:
        """获取运镜方式ID

        Args:
            raw_event: 原始攻击事件

        Returns:
            运镜方式ID字符串
        """
        if raw_event.attack_result == "CRIT":
            return "close_up_dynamic"
        elif raw_event.attack_result == "暴击":
            return "close_up_dynamic"
        elif raw_event.distance < 500:
            return "close_up_static"
        else:
            return "medium"

    def _get_vfx_ids(self, raw_event: RawAttackEvent) -> List[str]:
        """获取视觉特效ID列表

        根据攻击结果从配置文件中读取特效列表

        Args:
            raw_event: 原始攻击事件

        Returns:
            特效ID列表
        """
        mappings = self.config.get("mappings", {})
        effect_mappings = mappings.get("effects", {})

        result_key = raw_event.attack_result
        if result_key in effect_mappings:
            return effect_mappings[result_key]

        # 默认特效
        if raw_event.attack_result in ["HIT", "暴击", "CRIT"]:
            return ["vfx_screen_shake_light"]
        return []

    def _get_sfx_ids(self, raw_event: RawAttackEvent) -> List[str]:
        """获取音效ID列表

        Args:
            raw_event: 原始攻击事件

        Returns:
            音效ID列表
        """
        # 简单实现：根据武器类型返回音效
        weapon_type = raw_event.weapon_type.lower()
        if weapon_type == "melee":
            return ["sfx_melee_hit"]
        elif weapon_type in ["rifle", "awakening", "heavy"]:
            return ["sfx_beam_fire"]
        else:
            return ["sfx_default"]

    def _get_display_tags(self, raw_event: RawAttackEvent) -> List[str]:
        """获取需要高亮显示的标签

        根据技能触发情况和攻击结果生成标签列表

        Args:
            raw_event: 原始攻击事件

        Returns:
            标签字符串列表
        """
        tags = []

        # 攻击结果标签
        if raw_event.attack_result == "CRIT" or raw_event.attack_result == "暴击":
            tags.append("暴击")
        elif raw_event.attack_result == "HIT":
            tags.append("命中")
        elif raw_event.attack_result == "DODGE":
            tags.append("躲闪")
        elif raw_event.attack_result == "PARRY":
            tags.append("招架")
        elif raw_event.attack_result == "BLOCK":
            tags.append("格挡")
        elif raw_event.attack_result == "MISS":
            tags.append("未命中")

        # 技能触发标签（如果有的话）
        # 这里可以扩展，根据技能ID添加对应的显示名
        skill_display_names = {
            "spirit_critical_burst": "集中射击",
            "spirit_lucky_dodge": "直觉回避",
            "spirit_desperate_strike": "热血",
            "spirit_guard_break": "破甲弹"
        }

        for skill_id in raw_event.triggered_skills:
            if skill_id in skill_display_names:
                tags.append(skill_display_names[skill_id])

        return tags

    def _get_section_type(self, raw_event: RawAttackEvent) -> str:
        """获取文本段落类型

        Args:
            raw_event: 原始攻击事件

        Returns:
            段落类型字符串 (CONTEXT/ACTION_FIRST/ACTION_SECOND/SUMMARY)
        """
        if raw_event.is_first_attack:
            return "ACTION_FIRST"
        else:
            return "ACTION_SECOND"
