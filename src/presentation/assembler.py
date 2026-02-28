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
    _LOCATION_MAP: Dict[str, List[str]] = {
        "FATAL": ["驾驶舱", "动力炉", "核心反应堆"],
        "CRIT": ["主摄像机", "推进器端口", "关节部位", "传感器阵列"],
        "HIT": ["外装甲", "机体侧翼", "腰部装甲", "肩部装甲"],
        "BLOCK": ["盾牌表面", "前装甲", "防御力场"],
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

    根据 damage/defender_max_hp 比例分级：
    - <10%: 骚扰级
    - 10-30%: 有效级
    - 30-60%: 重创级
    - >60%: 毁灭级
    """

    @classmethod
    def get_grade(cls, damage: int, max_hp: int) -> str:
        """获取损伤量级描述"""
        if max_hp <= 0:
            return "骚扰级"

        ratio = damage / max_hp

        if ratio < 0.1:
            return "骚扰级"
        elif ratio < 0.3:
            return "有效级"
        elif ratio < 0.6:
            return "重创级"
        else:
            return "毁灭级"

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
            return cmd_map.get(cmd, cmd)

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
        if not bone:
            # 默认描述 - 根据意图生成更丰富的默认文本
            from .intent_extractor import IntentExtractor, VisualIntent
            intent = IntentExtractor.extract_intent(event.weapon_type, event.weapon_tags)

            # 基于意图的默认描述
            default_texts = {
                VisualIntent.SLASH_LIGHT: f"{event.attacker_name}身形一闪，挥动{event.weapon_name}斩向敌机！",
                VisualIntent.SLASH_HEAVY: f"{event.attacker_name}抡起沉重的{event.weapon_name}，以泰山压顶之势猛然砸下！",
                VisualIntent.STRIKE_BLUNT: f"{event.attacker_name}踏步出击，试图以雷霆万钧的重击击碎对方的防御！",
                VisualIntent.BEAM_INSTANT: f"{event.attacker_name}将准星锁定在对方的轮廓上，{event.weapon_name}喷薄出高度压缩的粒子流！",
                VisualIntent.BEAM_MASSIVE: f"{event.attacker_name}的机身四周因能量聚集而扭曲，{event.weapon_name}蓄势待发！",
                VisualIntent.PROJECTILE_SINGLE: f"{event.attacker_name}扣动扳机，{event.weapon_name}的退壳机排出一缕青烟。",
                VisualIntent.PROJECTILE_RAIN: f"「覆盖前方区域！别放过他！」{event.attacker_name}的{event.weapon_name}向前方喷吐出密集的火蛇。",
                VisualIntent.IMPACT_MASSIVE: f"{event.attacker_name}完全放弃了射击，将辅助推进器全部开启，机体化作一枚钢铁陨石撞向前方！",
                VisualIntent.PSYCHO_WAVE: f"「去吧！按照我的意志！」{event.attacker_name}的意识通过感应系统无限扩张！",
                VisualIntent.AOE_BURST: f"{event.attacker_name}启动了禁忌的武器序列，地平线上仿佛升起了第二颗太阳。",
            }
            text = default_texts.get(intent, f"{event.attacker_name}使用{event.weapon_name}发起攻击！")
            try:
                return text.format(**variables)
            except KeyError:
                return text

        fragments = bone.text_fragments if bone.text_fragments else []

        if not fragments:
            return f"{event.attacker_name}使用{event.weapon_name}发起攻击！"

        # 随机选择一个 fragment（每个 fragment 是一个完整的描述选项）
        text = random.choice(fragments)

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
        """组装防御方文本"""
        base_text = ""

        if channel == Channel.EVADE:
            # 区分 MISS（攻击方打偏）、DODGE（防御方躲闪）、PARRY（武器招架）
            if event.attack_result == "MISS":
                # MISS - 攻击方打偏了
                miss_texts = [
                    f"{event.attacker_name}的攻击准头完全偏离，不知飞向何处！",
                    f"{event.attacker_name}的攻击打空了，只在远处扬起一片尘土！",
                    f"{event.attacker_name}未能锁定目标，攻击完全落空！",
                    f"准星偏差过大，{event.attacker_name}的攻击在虚空中消散！",
                ]
                base_text = random.choice(miss_texts)
            elif event.attack_result == "PARRY":
                # PARRY - 用武器招架，根据攻击方武器类型区分
                physics = event.physics_class
                if physics == "Blade":
                    parry_texts = [
                        f"{event.defender_name}以武器精准招架，刀刃相交的刺耳声响彻战场！",
                        f"火花四溅！{event.defender_name}的武器成功架住了斩击！",
                        f"{event.defender_name}精妙地用武器偏转了锋利的斩击！",
                        f"金属碰撞的尖锐声响！{event.defender_name}用武器化解了斩击攻势！",
                    ]
                elif physics == "Kinetic":
                    parry_texts = [
                        f"{event.defender_name}用武器精准弹开来袭的弹头！",
                        f"火花四溅！{event.defender_name}的武器成功格挡了实弹攻击！",
                        f"{event.defender_name}以武器将弹丸击飞，攻击被化解！",
                        f"{event.defender_name}的武器与弹头相撞，将攻击完全偏转！",
                    ]
                elif physics == "Impact":
                    parry_texts = [
                        f"{event.defender_name}以武器撑住冲锋，在千钧一发之际完成招架！",
                        f"{event.defender_name}用武器格开冲击，成功化解了撞击！",
                        f"武器与机体碰撞！{event.defender_name}成功招架了重击！",
                    ]
                else:  # Energy
                    parry_texts = [
                        f"{event.defender_name}的I-Field感应场及时展开，光束被武器精准偏转！",
                        f"光束在{event.defender_name}的武器表面划过，没有留下痕迹！",
                        f"{event.defender_name}以武器诱导光束偏转，攻击被化解！",
                        f"抗光束涂层闪耀！{event.defender_name}用武器架住了光束！",
                    ]
                base_text = random.choice(parry_texts)
            else:  # DODGE - 防御方躲闪
                physics = event.physics_class
                if physics == "Blade":
                    dodge_texts = [
                        f"{event.defender_name}的姿态控制喷嘴喷出耀眼的火焰，完美躲过了斩击！",
                        f"刀刃擦着装甲划过，{event.defender_name}险险避过！",
                        f"{event.defender_name}以精妙的步法闪开了锋利的斩击！",
                    ]
                elif physics == "Kinetic":
                    dodge_texts = [
                        f"{event.defender_name}推进器反向喷射，滑步闪避！",
                        f"侧身跃起，{event.defender_name}险险避过致命一击！",
                        f"在千钧一发之际，{event.defender_name}完成闪避！",
                    ]
                elif physics == "Impact":
                    dodge_texts = [
                        f"{event.defender_name}侧身跃起，险险避过致命一击！",
                        f"推进器全开，{event.defender_name}在千钧一发之际完成闪避！",
                    ]
                else:  # Energy
                    dodge_texts = [
                        f"{event.defender_name}推进器喷射，侧身闪开！",
                        f"残影晃动，{event.defender_name}已不在原位！",
                        f"{event.defender_name}机敏地躲过了攻击！",
                    ]
                base_text = random.choice(dodge_texts)

        elif not bone or event.attack_result == "BLOCK":
            # 基于频道的默认描述
            if channel == Channel.FATAL:
                fatal_texts = [
                    f"{event.defender_name}的{variables.get('hit_part', '核心部位')}被击中，机体在烈焰中化为燃烧的残骸坠落！",
                    f"核心机能停止！{event.defender_name}在连锁爆裂中支离破碎！",
                    f"{event.defender_name}的系统显示大面积离线，机体在爆炸中逐渐支离破碎。",
                ]
                base_text = random.choice(fatal_texts)
            elif event.attack_result == "CRIT":
                crit_texts = [
                    f"{event.defender_name}的{variables.get('hit_part', '装甲')}遭受重创，机体在剧痛中剧烈震颤！",
                    f"致命一击！{event.defender_name}的多处系统同时报错，驾驶舱内火花四溅！",
                    f"{event.defender_name}的装甲被贯穿，内部结构在连环爆炸中彻底崩溃！",
                ]
                base_text = random.choice(crit_texts)
            elif event.attack_result == "BLOCK":
                # BLOCK - 盾牌/装甲格挡，根据武器类型和伤害值区分
                physics = event.physics_class
                damage = abs(event.damage)  # 格挡后实际受到的伤害

                # 伤害分级：轻微 < 300，中等 300-800，沉重 800-1500，危险 > 1500
                if physics == "Blade":
                    if damage < 300:
                        block_texts = [
                            f"{event.defender_name}轻描淡写地举盾格挡，斩击如微风般掠过！",
                            f"刀刃在盾牌上轻擦，{event.defender_name}几乎无感地挡下攻击！",
                            f"{event.defender_name}的盾牌微微一震，轻松架住了斩击！",
                        ]
                    elif damage < 800:
                        block_texts = [
                            f"刀刃在{event.defender_name}的盾牌上擦出火花，攻击被挡下！",
                            f"{event.defender_name}举盾格挡，金属摩擦声刺耳！",
                            f"{event.defender_name}的盾牌微微凹陷，但成功架住了斩击！",
                        ]
                    elif damage < 1500:
                        block_texts = [
                            f"{event.defender_name}以盾牌硬扛斩击，手臂传来剧痛但防御未破！",
                            f"刀刃深深切进盾牌！{event.defender_name}咬紧牙关挡下了攻击！",
                            f"{event.defender_name}的盾牌被斩出一道深痕，勉强撑住了！",
                        ]
                    else:
                        block_texts = [
                            f"{event.defender_name}的盾牌险些被斩断！勉强挡下了致命一击！",
                            f"盾牌发出悲鸣！{event.defender_name}以极限状态架住了斩击！",
                            f"{event.defender_name}被斩击震退数步，但盾牌终究没有破碎！",
                        ]

                elif physics == "Kinetic":
                    if damage < 300:
                        block_texts = [
                            f"{event.defender_name}的盾牌稳稳接下弹丸，几乎纹丝不动！",
                            f"实弹攻击在盾牌表面轻弹开，{event.defender_name}轻松格挡！",
                            f"{event.defender_name}举盾一立，弹丸便无力坠落！",
                        ]
                    elif damage < 800:
                        block_texts = [
                            f"{event.defender_name}的盾牌死死顶在前方，弹丸被完全挡下！",
                            f"盾牌表面迸溅出火花！{event.defender_name}成功挡下了实弹！",
                            f"弹丸在盾牌上炸开，{event.defender_name}的防御依然稳固！",
                        ]
                    elif damage < 1500:
                        block_texts = [
                            f"{event.defender_name}举盾格挡，实弹爆炸的冲击让机体滑行数米！",
                            f"{event.defender_name}的盾牌表面被炸得凹凸不平，但撑住了！",
                            f"爆炸的烟尘散去，{event.defender_name}的盾牌依然挺立！",
                        ]
                    else:
                        block_texts = [
                            f"{event.defender_name}的盾牌被炸得千疮百孔！但终究没有破碎！",
                            f"剧烈爆炸！{event.defender_name}被冲击波震退，盾牌受损严重！",
                            f"{event.defender_name}的盾牌发出濒临破碎的声音，勉强挡下攻击！",
                        ]

                elif physics == "Impact":
                    if damage < 300:
                        block_texts = [
                            f"{event.defender_name}举盾轻挡，冲击如挠痒般被化解！",
                            f"盾牌微微一震，{event.defender_name}轻松挡住了撞击！",
                            f"{event.defender_name}以盾牌轻推便化解了冲锋！",
                        ]
                    elif damage < 800:
                        block_texts = [
                            f"{event.defender_name}以盾牌硬抗冲击，机体微微滑行后稳住！",
                            f"盾牌承受重击！{event.defender_name}成功挡住了撞击！",
                            f"{event.defender_name}举盾格挡，冲击力被大部分吸收！",
                        ]
                    elif damage < 1500:
                        block_texts = [
                            f"{event.defender_name}举起盾牌，被冲击力震得滑行十数米！",
                            f"盾牌发出咯吱声！{event.defender_name}咬紧牙关挡下了重击！",
                            f"推进器全开抵消冲击！{event.defender_name}勉强稳住防线！",
                        ]
                    else:
                        block_texts = [
                            f"{event.defender_name}的盾牌发出濒临破碎的悲鸣，但终究没有垮！",
                            f"巨大冲击！{event.defender_name}被撞飞，盾牌已到极限！",
                            f"{event.defender_name}以盾牌拼命格挡，机体被撞退数十米！",
                        ]

                else:  # Energy
                    if damage < 300:
                        block_texts = [
                            f"{event.defender_name}的I-Field微微闪烁，光束便消散于无形！",
                            f"光束轻触盾牌即逝，{event.defender_name}轻松格挡！",
                            f"{event.defender_name}的抗光束涂层几乎未损，光束被完全偏转！",
                        ]
                    elif damage < 800:
                        block_texts = [
                            f"{event.defender_name}的I-Field展开，光束在感应场表面扭曲消散！",
                            f"{event.defender_name}的抗光束盾牌闪耀，光束攻击被完全偏转！",
                            f"能量雾气弥漫！{event.defender_name}的盾牌成功化解了光束！",
                        ]
                    elif damage < 1500:
                        block_texts = [
                            f"光束灼烧盾牌表面！{event.defender_name}的防御阵线依然稳固！",
                            f"{event.defender_name}的盾牌表面被烧得通红，但成功挡下了光束！",
                            f"I-Field剧烈闪烁！{event.defender_name}以极限状态偏转了光束！",
                        ]
                    else:
                        block_texts = [
                            f"{event.defender_name}的盾牌几乎被熔穿！但光束终究未能穿透！",
                            f"盾牌发出刺耳警报！{event.defender_name}拼死挡下了高能光束！",
                            f"光束贯穿盾牌一角！{event.defender_name}以濒死状态完成格挡！",
                        ]

                base_text = random.choice(block_texts)
            else:
                hit_texts = [
                    f"{event.defender_name}的{variables.get('hit_part', '装甲')}受到攻击！",
                    f"攻击命中了{event.defender_name}的{variables.get('hit_part', '机体')}！",
                    f"{event.defender_name}承受了这次打击，机体表面多了一道伤痕。",
                ]
                base_text = random.choice(hit_texts)

            try:
                base_text = base_text.format(**variables)
            except KeyError:
                pass

        else:
            fragments = bone.text_fragments if bone.text_fragments else []

            if not fragments:
                if channel == Channel.FATAL:
                    base_text = f"{event.defender_name}被击中要害，机体严重损毁！"
                else:
                    base_text = f"{event.defender_name}受到攻击！"
            else:
                # 随机选择一个 fragment（每个 fragment 是一个完整的描述选项）
                base_text = random.choice(fragments)

            # 变量注入
            try:
                base_text = base_text.format(**variables)
            except KeyError:
                pass

        # 添加判定结果和伤害信息
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
        base_text += f"（{result_name}！{-damage}）"

        return base_text
