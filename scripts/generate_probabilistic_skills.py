"""
生成概率型和条件型技能配置
用于丰富技能系统的测试数据
"""

import json
import os

# ============================================================================
# 概率型技能配置 (trigger_chance < 1.0)
# ============================================================================

PROBABILISTIC_SKILLS = {
    # 精神指令 - 概率型
    "spirit_critical_burst": [
        {
            "id": "spirit_critical_burst",
            "name": "暴击爆发",
            "description": "30%概率本次攻击必定暴击",
            "hook": "HOOK_PRE_CRIT_RATE",
            "operation": "set",
            "value": 100.0,
            "duration": 1,
            "trigger_chance": 0.3,
            "priority": 95
        }
    ],

    "spirit_lucky_dodge": [
        {
            "id": "spirit_lucky_dodge",
            "name": "幸运闪避",
            "description": "25%概率将HIT转为DODGE",
            "hook": "HOOK_POST_ROLL_RESULT",
            "operation": "callback",
            "value": "cb_lucky_dodge",
            "duration": 1,
            "trigger_chance": 0.25,
            "priority": 95
        }
    ],

    "spirit_desperate_strike": [
        {
            "id": "spirit_desperate_strike",
            "name": "绝地一击",
            "description": "HP<30%时，40%概率造成1.5倍伤害",
            "hook": "HOOK_PRE_DAMAGE_MULT",
            "operation": "mul",
            "value": 1.5,
            "duration": 1,
            "trigger_chance": 0.4,
            "priority": 90,
            "conditions": [
                {
                    "type": "owner_hp_below",
                    "threshold": 0.3
                }
            ]
        }
    ],

    "spirit_enrage": [
        {
            "id": "spirit_enrage",
            "name": "狂怒",
            "description": "受到伤害后，20%概率提升攻击力50%，持续3回合",
            "hook": "HOOK_ON_DAMAGE_TAKEN",
            "operation": "callback",
            "value": "cb_enrage",
            "duration": 1,
            "trigger_chance": 0.2,
            "priority": 85,
            "side_effects": [
                {
                    "hook": "HOOK_PRE_ATTACK_POWER",
                    "operation": "add",
                    "value": 50.0,
                    "duration": 3
                }
            ]
        }
    ],

    "spirit_second_wind": [
        {
            "id": "spirit_second_wind",
            "name": "回光返照",
            "description": "HP<20%时，35%概率回复50% HP",
            "hook": "HOOK_ON_TURN_START",
            "operation": "callback",
            "value": "cb_second_wind",
            "duration": 1,
            "trigger_chance": 0.35,
            "priority": 90,
            "conditions": [
                {
                    "type": "owner_hp_below",
                    "threshold": 0.2
                }
            ]
        }
    ],

    "spirit_counter_attack": [
        {
            "id": "spirit_counter_attack",
            "name": "反击",
            "description": "被攻击时，30%概率立即反击一次",
            "hook": "HOOK_ON_ATTACK_END",
            "operation": "callback",
            "value": "cb_counter_attack",
            "duration": 1,
            "trigger_chance": 0.3,
            "priority": 88,
            "conditions": [
                {
                    "type": "is_defender"
                }
            ]
        }
    ],

    "spirit_precision_strike": [
        {
            "id": "spirit_precision_strike",
            "name": "精准打击",
            "description": "25%概率本次攻击无视敌方格挡和招架",
            "hook": "HOOK_PRE_IGNORE_DEFENSE",
            "operation": "set",
            "value": 1.0,
            "duration": 1,
            "trigger_chance": 0.25,
            "priority": 92
        }
    ],

    "spirit_energy_surge": [
        {
            "id": "spirit_energy_surge",
            "name": "能量涌动",
            "description": "EN<30%时，40%概率回复100 EN",
            "hook": "HOOK_ON_TURN_START",
            "operation": "callback",
            "value": "cb_energy_surge",
            "duration": 1,
            "trigger_chance": 0.4,
            "priority": 85,
            "conditions": [
                {
                    "type": "owner_en_below",
                    "threshold": 0.3
                }
            ]
        }
    ],

    "spirit_berserk": [
        {
            "id": "spirit_berserk",
            "name": "狂暴",
            "description": "HP<50%时，每回合30%概率提升暴击率30%，持续2回合",
            "hook": "HOOK_ON_TURN_START",
            "operation": "callback",
            "duration": 1,
            "trigger_chance": 0.3,
            "priority": 87,
            "conditions": [
                {
                    "type": "owner_hp_below",
                    "threshold": 0.5
                }
            ],
            "side_effects": [
                {
                    "hook": "HOOK_PRE_CRIT_RATE",
                    "operation": "add",
                    "value": 30.0,
                    "duration": 2
                }
            ]
        }
    ],

    # 机体特性 - 概率型
    "trait_critical_master": [
        {
            "id": "trait_critical_master",
            "name": "暴击大师",
            "description": "永久特性：每次暴击时，20%概率恢复10 EN",
            "hook": "HOOK_ON_CRIT",
            "operation": "callback",
            "value": "cb_critical_master_en",
            "duration": -1,
            "trigger_chance": 0.2
        }
    ],

    "trait_dodge_reflex": [
        {
            "id": "trait_dodge_reflex",
            "name": "闪避反射",
            "description": "永久特性：成功闪避后，25%概率立即反击",
            "hook": "HOOK_ON_DODGE",
            "operation": "callback",
            "value": "cb_dodge_reflex",
            "duration": -1,
            "trigger_chance": 0.25
        }
    ],

    "trait_last_stand": [
        {
            "id": "trait_last_stand",
            "name": "最后手段",
            "description": "永久特性：HP<10%时，50%概率防御+50，持续3回合",
            "hook": "HOOK_ON_TURN_START",
            "duration": -1,
            "trigger_chance": 0.5,
            "priority": 90,
            "conditions": [
                {
                    "type": "owner_hp_below",
                    "threshold": 0.1
                }
            ],
            "side_effects": [
                {
                    "hook": "HOOK_PRE_DEFENSE_MULT",
                    "operation": "add",
                    "value": 50.0,
                    "duration": 3
                }
            ]
        }
    ],

    "trait_adrenaline": [
        {
            "id": "trait_adrenaline",
            "name": "肾上腺素",
            "description": "永久特性：受到致死伤害时，30%概率保留1 HP",
            "hook": "HOOK_ON_DAMAGE_TAKEN",
            "operation": "callback",
            "value": "cb_adrenaline_survive",
            "duration": -1,
            "trigger_chance": 0.3,
            "priority": 95,
            "conditions": [
                {
                    "type": "would_be_fatal"
                }
            ]
        }
    ],

    "trait_vampirism": [
        {
            "id": "trait_vampirism",
            "name": "吸血鬼",
            "description": "永久特性：造成伤害时，15%概率回复伤害值20%的HP",
            "hook": "HOOK_ON_DAMAGE_DEALT",
            "operation": "callback",
            "value": "cb_vampirism_heal",
            "duration": -1,
            "trigger_chance": 0.15
        }
    ],

    "trait_lucky_star": [
        {
            "id": "trait_lucky_star",
            "name": "幸运星",
            "description": "永久特性：每次攻击未命中时，10%概率返还50% EN消耗",
            "hook": "HOOK_ON_MISS",
            "operation": "callback",
            "value": "cb_lucky_en_refund",
            "duration": -1,
            "trigger_chance": 0.1
        }
    ],

    "trait_mana_shield": [
        {
            "id": "trait_mana_shield",
            "name": "法力护盾",
            "description": "永久特性：受到伤害时，20%概率消耗EN代替HP（1 EN = 100伤害）",
            "hook": "HOOK_PRE_DAMAGE_TAKEN",
            "operation": "callback",
            "value": "cb_mana_shield",
            "duration": -1,
            "trigger_chance": 0.2,
            "priority": 92
        }
    ],

    "trait_berserk_mode": [
        {
            "id": "trait_berserk_mode",
            "name": "狂暴模式",
            "description": "永久特性：HP<30%时，每回合40%概率攻击力翻倍，防御减半，持续2回合",
            "hook": "HOOK_ON_TURN_START",
            "duration": -1,
            "trigger_chance": 0.4,
            "priority": 88,
            "conditions": [
                {
                    "type": "owner_hp_below",
                    "threshold": 0.3
                }
            ],
            "side_effects": [
                {
                    "hook": "HOOK_PRE_ATTACK_POWER",
                    "operation": "mul",
                    "value": 2.0,
                    "duration": 2
                },
                {
                    "hook": "HOOK_PRE_DEFENSE_MULT",
                    "operation": "mul",
                    "value": 0.5,
                    "duration": 2
                }
            ]
        }
    ],
}

# ============================================================================
# 条件型技能配置 (有 conditions 字段)
# ============================================================================

CONDITIONAL_SKILLS = {
    # 精神指令 - 条件型
    "spirit_execute": [
        {
            "id": "spirit_execute",
            "name": "处决",
            "description": "对HP<50%的敌人，造成1.5倍伤害",
            "hook": "HOOK_PRE_DAMAGE_MULT",
            "operation": "mul",
            "value": 1.5,
            "duration": 1,
            "priority": 90,
            "conditions": [
                {
                    "type": "target_hp_below",
                    "threshold": 0.5
                }
            ]
        }
    ],

    "spirit_guard_break": [
        {
            "id": "spirit_guard_break",
            "name": "破防",
            "description": "对防御率>50%的敌人，无视50%防御",
            "hook": "HOOK_PRE_DEFENSE_PENETRATION",
            "operation": "add",
            "value": 50.0,
            "duration": 1,
            "priority": 85,
            "conditions": [
                {
                    "type": "target_defense_high",
                    "threshold": 0.5
                }
            ]
        }
    ],

    "spirit finish": [
        {
            "id": "spirit_finish",
            "name": "终结",
            "description": "对HP<20%的敌人，命中率+50%",
            "hook": "HOOK_PRE_HIT_RATE",
            "operation": "add",
            "value": 50.0,
            "duration": 1,
            "priority": 92,
            "conditions": [
                {
                    "type": "target_hp_below",
                    "threshold": 0.2
                }
            ]
        }
    ],

    "spirit_defensive_stance": [
        {
            "id": "spirit_defensive_stance",
            "name": "防御姿态",
            "description": "HP<50%时，防御+30，机动-20",
            "hook": "HOOK_PRE_EN_STATS",
            "operation": "callback",
            "value": "cb_defensive_stance",
            "duration": 1,
            "priority": 80,
            "conditions": [
                {
                    "type": "owner_hp_below",
                    "threshold": 0.5
                }
            ],
            "side_effects": [
                {
                    "hook": "HOOK_PRE_DEFENSE_MULT",
                    "operation": "add",
                    "value": 30.0,
                    "duration": -1
                },
                {
                    "hook": "HOOK_PRE_MOBILITY",
                    "operation": "sub",
                    "value": 20.0,
                    "duration": -1
                }
            ]
        }
    ],

    "spirit_offensive_stance": [
        {
            "id": "spirit_offensive_stance",
            "name": "攻击姿态",
            "description": "HP>80%时，攻击+30，防御-20",
            "hook": "HOOK_PRE_EN_STATS",
            "operation": "callback",
            "value": "cb_offensive_stance",
            "duration": 1,
            "priority": 80,
            "conditions": [
                {
                    "type": "owner_hp_above",
                    "threshold": 0.8
                }
            ],
            "side_effects": [
                {
                    "hook": "HOOK_PRE_ATTACK_POWER",
                    "operation": "add",
                    "value": 30.0,
                    "duration": -1
                },
                {
                    "hook": "HOOK_PRE_DEFENSE_MULT",
                    "operation": "sub",
                    "value": 20.0,
                    "duration": -1
                }
            ]
        }
    ],

    # 机体特性 - 条件型
    "trait_hp_guardian": [
        {
            "id": "trait_hp_guardian",
            "name": "生命守护",
            "description": "永久特性：HP越低，防御越高（最多+50%）",
            "hook": "HOOK_PRE_DEFENSE_MULT",
            "operation": "callback",
            "value": "cb_hp_guardian",
            "duration": -1,
            "priority": 75,
            "conditions": [
                {
                    "type": "owner_hp_below",
                    "threshold": 1.0  # 总是触发，在回调中计算具体值
                }
            ]
        }
    ],

    "trait_momentum": [
        {
            "id": "trait_momentum",
            "name": "气势",
            "description": "永久特性：连续命中时，伤害递增（每次+5%，最多+25%）",
            "hook": "HOOK_POST_ATTACK_HIT",
            "operation": "callback",
            "value": "cb_momentum_counter",
            "duration": -1
        }
    ],

    "trait_counter_attack": [
        {
            "id": "trait_counter_attack",
            "name": "反击",
            "description": "永久特性：被攻击时有30%概率反击",
            "hook": "HOOK_ON_ATTACK_END",
            "operation": "callback",
            "value": "cb_trait_counter",
            "duration": -1,
            "trigger_chance": 0.3,
            "priority": 85,
            "conditions": [
                {
                    "type": "is_defender"
                }
            ]
        }
    ],

    "trait_executioner": [
        {
            "id": "trait_executioner",
            "name": "处刑者",
            "description": "永久特性：对HP<30%的敌人，暴击率+20%",
            "hook": "HOOK_PRE_CRIT_RATE",
            "operation": "add",
            "value": 20.0,
            "duration": -1,
            "priority": 88,
            "conditions": [
                {
                    "type": "target_hp_below",
                    "threshold": 0.3
                }
            ]
        }
    ],

    "trait_elemental_advantage": [
        {
            "id": "trait_elemental_advantage",
            "name": "属性优势",
            "description": "永久特性：对特定类型敌人伤害+25%",
            "hook": "HOOK_PRE_DAMAGE_MULT",
            "operation": "mul",
            "value": 1.25,
            "duration": -1,
            "priority": 82,
            "conditions": [
                {
                    "type": "target_type",
                    "value": "biological"  # 对生物型敌人
                }
            ]
        }
    ],

    "trait_desperado": [
        {
            "id": "trait_desperado",
            "name": "死斗",
            "description": "永久特性：HP越低，攻击力越高（最多+50%）",
            "hook": "HOOK_PRE_ATTACK_POWER",
            "operation": "callback",
            "value": "cb_desperado_atk",
            "duration": -1,
            "priority": 90
        }
    ],

    "trait_energy_efficiency": [
        {
            "id": "trait_energy_efficiency",
            "name": "高效",
            "description": "永久特性：EN>50%时，EN消耗减半",
            "hook": "HOOK_PRE_EN_COST_MULT",
            "operation": "callback",
            "value": "cb_efficient_en",
            "duration": -1,
            "priority": 88,
            "conditions": [
                {
                    "type": "owner_en_above",
                    "threshold": 0.5
                }
            ]
        }
    ],

    "trait_phase_shift": [
        {
            "id": "trait_phase_shift",
            "name": "相位转移",
            "description": "永久特性：第1-3回合防御+50%，第4-6回合攻击+50%",
            "hook": "HOOK_ON_TURN_START",
            "operation": "callback",
            "value": "cb_phase_shift",
            "duration": -1,
            "priority": 85
        }
    ],

    "trait_combo_master": [
        {
            "id": "trait_combo_master",
            "name": "连击大师",
            "description": "永久特性：连续命中3次后，下一次必定暴击",
            "hook": "HOOK_POST_ATTACK_HIT",
            "operation": "callback",
            "value": "cb_combo_counter",
            "duration": -1,
            "priority": 92
        }
    ],

    "trait_adaptive_armor": [
        {
            "id": "trait_adaptive_armor",
            "name": "适应性装甲",
            "description": "永久特性：受到相同类型伤害后，对该类型伤害抗性+20%",
            "hook": "HOOK_ON_DAMAGE_TAKEN",
            "operation": "callback",
            "value": "cb_adaptive_defense",
            "duration": -1,
            "priority": 80
        }
    ],

    "trait_rage_building": [
        {
            "id": "trait_rage_building",
            "name": "怒气累积",
            "description": "永久特性：每次受到伤害时，暴击率+2%（最多+20%）",
            "hook": "HOOK_ON_DAMAGE_TAKEN",
            "operation": "callback",
            "value": "cb_rage_counter",
            "duration": -1,
            "priority": 87
        }
    ],
}

# ============================================================================
# 生成扩展技能文件
# ============================================================================

def generate_extended_skills():
    """生成扩展技能配置"""
    # 合并所有技能
    all_skills = {}
    all_skills.update(PROBABILISTIC_SKILLS)
    all_skills.update(CONDITIONAL_SKILLS)

    # 确保输出目录存在
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)

    # 读取现有技能文件
    existing_skills_path = os.path.join(output_dir, "skills.json")
    if os.path.exists(existing_skills_path):
        with open(existing_skills_path, "r", encoding="utf-8") as f:
            existing_skills = json.load(f)

        # Merge skills (keep existing, add new)
        for skill_id, skill_data in all_skills.items():
            if skill_id not in existing_skills:
                existing_skills[skill_id] = skill_data
            else:
                print(f"WARNING: Skill {skill_id} already exists, skipping")

        all_skills = existing_skills

    # 写入文件
    output_path = os.path.join(output_dir, "skills_extended.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_skills, f, ensure_ascii=False, indent=2)

    print(f"[OK] Generated extended skills config: {output_path}")
    print(f"  - Probabilistic skills: {len(PROBABILISTIC_SKILLS)}")
    print(f"  - Conditional skills: {len(CONDITIONAL_SKILLS)}")
    print(f"  - Total skills: {len(all_skills)}")

    # Generate statistics report
    print("\nSkill classification statistics:")
    print("\n[Probabilistic Skills]")
    for skill_id, skill_data in PROBABILISTIC_SKILLS.items():
        skill = skill_data[0]
        chance = skill.get("trigger_chance", 1.0)
        trigger_chance = f"{chance*100:.0f}%" if chance < 1.0 else "-"
        condition_count = len(skill.get("conditions", []))
        condition_str = f"+{condition_count} conditions" if condition_count > 0 else ""
        print(f"  {skill['name']:<20} ({skill_id}): chance={trigger_chance} {condition_str}")

    print("\n[Conditional Skills]")
    for skill_id, skill_data in CONDITIONAL_SKILLS.items():
        skill = skill_data[0]
        conditions = skill.get("conditions", [])
        condition_types = [c.get("type", "unknown") for c in conditions]
        condition_str = ", ".join(condition_types)
        chance = skill.get("trigger_chance", 1.0)
        trigger_chance = f"{chance*100:.0f}%" if chance < 1.0 else "-"
        print(f"  {skill['name']:<20} ({skill_id}): {condition_str} {f'(chance:{trigger_chance})' if chance < 1.0 else ''}")

if __name__ == "__main__":
    generate_extended_skills()
