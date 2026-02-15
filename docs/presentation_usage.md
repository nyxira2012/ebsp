# 战斗演出系统实施指南 (Combat Presentation System Implementation Guide)

> **版本**: 3.0 (握手协议与全量架构)
> **状态**: 实施指南 (Implementation Ready)
> **目标**: 像工业流水线一样处理演出，确保逻辑闭环，通过 **Intent (意图)** 和 **Priority (优先级)** 构建逻辑严密的视听叙事。

---

## 1. 系统核心理念 (Core Philosophy)

本系统旨在解决回合制战斗中“动作与描述割裂”的核心难题，通过一套严密的**握手协议**，将战斗逻辑的输出转化为连贯、符合直觉的战场叙事。

### 1.1 核心机制：握手协议 (Handshake Protocol)
演出不再是两个独立的积木拼凑，而是一个完整的**“发球-接球”**过程：

1.  **Action (发球方)**：攻击者不仅执行动作，还必须抛出一个明确的视觉意图（`Visual Intent`）。
    *   *例*：使用光束步枪 → 抛出intent: `INTENT_BEAM_INSTANT`
2.  **Reaction (接球方)**：防御者根据自身状态，**必须订阅**并响应这个意图。
    *   *例*：试图格挡 → 检查是否能格挡 `INTENT_BEAM_INSTANT`？
    *   *结果*：如果能，播放抗光束涂层蒸发的动画；如果不能，播放装甲熔穿的动画。

### 1.2 优先级瀑布流 (Priority Waterfall)
系统摒弃复杂的“黑名单”机制，采用**短路逻辑**的优先级扫描：
**一旦高优先级规则匹配成功，系统立即停止扫描并返回结果。** 低优先级规则无需知道高优先级的存在。

---

## 2. 意图系统设计 (Visual Intent Methodology)

意图是连接攻击与防御的纽带。策划必须定义一套标准的、物理层面的交互语言，而非视觉层面的（如颜色）描述。

### 2.1 标准意图字典 (Standard Intent Dictionary)

| Intent 代码                | 物理含义   | 典型的 Action 表现   | 期待的 Reaction 表现                                 |
| :------------------------- | :--------- | :------------------- | :--------------------------------------------------- |
| **INTENT_SLASH_HEAVY**     | 重型斩击   | 巨剑挥砍、热能斧劈下 | 金属格挡、火花四溅、狼狈躲避（不可写“侧身让过光束”） |
| **INTENT_BEAM_INSTANT**    | 光束瞬发   | 光束步枪、短激光     | 护盾光晕、空气电离、涂层蒸发（不可写“听到了炮弹声”） |
| **INTENT_PROJECTILE_RAIN** | 实弹弹幕   | 导弹齐射、火神炮扫射 | 烟尘弥漫、连续爆炸、视线遮蔽                         |
| **INTENT_IMPACT_MASSIVE**  | 质量撞击   | 机体冲撞、陨石投掷   | 驾驶舱剧烈震动、平衡丧失、地面碎裂                   |
| **INTENT_PSYCHO_WAVE**     | 精神感应波 | 浮游炮、精神力场     | 空间扭曲、脑波共鸣、非物理层面的压迫感               |

### 2.2 命中部位逻辑 (Hit Location Injection)

命中部位通过 **Tag 过滤** 与 **变量注入** 双重机制融入瀑布流：

1.  **随机池 (Random Pool)**：结算引擎根据判定结果，从当前机体的“受击部位字典”中随机抽取一个值（如：`左侧肩甲`、`头部监视器`）。
2.  **变量映射 (Variable Mapping)**：
    *   **通用场景**：在 T2/T3 文本中使用占位符 `{location}`。
    *   **特例场景**：如果抽取到关键部位（如 `HEAD`），系统会自动注入标签 `TAG_LOC_HEAD`。
3.  **高优抢占 (Preemption)**：T1 层级可以针对 `TAG_LOC_HEAD` 编写专属演出（如“监视器损毁特写”），从而阻断通用的 `{location}` 描述。

---

## 3. 优先级层级定义 (Priority Tiers)

系统严格按照 T0 -> T3 的顺序进行匹配。

### T0: 剧情与强制演出 (Scripted/Forced)
*   **定义**: 无论发生什么，必须播放的特定演出。
*   **场景**: 
    *   BOSS开场白 / 变身阶段
    *   剧情必杀技（如“暴走初号机啃食”）
    *   特定关卡的对话事件
*   **逻辑**: 只要 Condition 满足，**绝对锁定**。

### T1: 技能与特质演出 (Skill/Trait Oriented) - **关键层级**
*   **定义**: 体现角色个性和技能特性的演出。这里是**技能触发演出的核心入口**。
*   **场景**:
    *   **技能触发**: “新人类（Newtype）”感应并发动。
    *   **特殊装备**: “I力场”发生器中和了光束。
    *   **精神指令**: “必闪”生效时的特殊闪避动作。
*   **逻辑**: 检测 `combat_context.triggered_skills` 或 `unit_tags`。

### T2: 战术与武器分类 (Tactical/Weapon Type)
*   **定义**: 基于武器类型和战术动作的通用描述。
*   **场景**:
    *   光束步枪的暴击（Headshot）。
    *   光束军刀的拼刀（Clash）。
*   **逻辑**: 主要检查 `weapon_type`, `attack_result`。

### T3: 通用保底 (Generic Fallback)
*   **定义**: 最基础的物理描述，确保系统永远有话可说。
*   **场景**: “A击中了B”。
*   **逻辑**: `Condition` 恒为 True，接受所有 Intent。

---

## 4. 技能演出触发逻辑 (Skill Performance Triggering)

技能演出不仅仅是播放一个特效，它必须深度介入到 Action/Reaction 的文本构建中。

### 4.1 技能演出的生命周期
1.  **Hook 触发**: 
    *   战斗逻辑层触发 Hook（如 `HOOK_PRE_DODGE_RATE`）。
    *   技能逻辑层返回修改值，并标记 `triggered_skill: "NEWTYPE_FLASH"`。
2.  **Tag 注入**:
    *   `CombatContext` 获得标签 `TAG_SKILL_NEWTYPE`。
3.  **演出匹配 (T1)**:
    *   Presentation 引擎在 T1 层级扫描到配置：
        *   `condition: has_tag("TAG_SKILL_NEWTYPE")`
    *   **Cut-in 插入**: 系统首先播放技能特写（Cut-in / Face close-up）。
    *   **文本替换**: 使用带有技能描述的模板替换通用模板。

### 4.2 案例说明：新人类闪避 (Newtype Flash)

**没有技能时 (T2/T3)**:
> 强袭高达侧身推进，避开了扎古的机枪扫射。

**触发技能时 (T1)**:
> **[Cut-in: 额头闪电特效 + 驾驶员特写]**
> 基拉瞳孔瞬间收缩，仿佛预知了未来——强袭高达在弹雨尚未触及前便已完成了规避机动，扎古的子弹只能徒劳地撕裂残影。

---

## 5. 配置方法论 (Configuration Strategy)

配置文件需严格区分 Action 和 Reaction 的职责，并利用 `output_intent` 和 `accept_intents` 实现逻辑闭环。

### 5.1 Action 配置模版
重点在于**输出什么意图**。

```yaml
# 动作配置 (action_rules.yaml)

# [T1] 技能特化：NT-D系统发动
- id: "act_unicorn_ntd_attack"
  tier: T1
  conditions:
    unit_tag: "NTD_ACTIVE"
    weapon_type: "PSYCHO_FIELD"
  text: "独角兽高达的精神感应框架发出耀眼的红光，直接干涉了物理法则，将敌机的装甲强行剥离。"
  output_intent: "INTENT_PSYCHO_WAVE" # 输出特殊意图

# [T2] 武器通用：光束步枪
- id: "act_beam_rifle_snipe"
  tier: T2
  conditions:
    weapon_type: "RIFLE"
    range_tag: "LONG"
  text: "{attacker} 锁定了远处的敌机，光束步枪喷射出致命的粒子流。"
  output_intent: "INTENT_BEAM_INSTANT" # 输出标准意图
```

### 5.2 Reaction 配置模版
重点在于**接受什么意图**。

```yaml
# 反应配置 (reaction_rules.yaml)

# [T1] 技能特化：I力场发生器 (克制光束)
- id: "react_i_field_block"
  tier: T1
  conditions:
    skill_triggered: "I_FIELD_GENERATOR" # 仅当技能触发时
  accept_intents: ["INTENT_BEAM_INSTANT", "INTENT_BEAM_MASSIVE"] # 只接光束
  text: "光束撞击在机体周围不可见的力场上，瞬间扭曲溃散，未能触及装甲分毫。"

# [T2] 战术特化：盾牌格挡实弹
- id: "react_shield_block_projectile"
  tier: T2
  conditions:
    result: "BLOCK"
    shield_equipped: true
  accept_intents: ["INTENT_PROJECTILE_RAIN", "INTENT_IMPACT_MASSIVE"] # 专接实弹/撞击
  text: "{defender} 举起盾牌，金属弹头在盾面上撞击出一连串耀眼的火花。"

# [T3] 通用保底 (兜底)
- id: "react_generic_hit"
  tier: T3
  conditions:
    result: "HIT"
  accept_intents: ["ANY"] # 照单全收
  text: "{defender} 机体被击中，装甲受损，碎片四散。"
```

---

## 6. 开发实施步骤 (Implementation Roadmap)

### 步骤 1: 建立意图与Tag字典 (Dictionary Definition)
*   **任务**: 全团队统一 `INTENT_*` 和 `TAG_*` 的枚举列表。
*   **产出**: `src/consts/presentation_tags.py`。包含所有物理意图和常用技能Tag。

### 步骤 2: 实现 Tag 注入逻辑 (Tag Injection)
*   **任务**: 在战斗逻辑结算后，将 triggers 转换为 tags。
*   **位置**: `CombatResolver` -> `PresentationMapper`。
*   **逻辑**: `if skill.id in triggered_skills: context.add_tag(skill.presentation_tag)`。

### 步骤 3: 编写 T3 保底层 (The Safety Net)
*   **任务**: 为所有 `WEAPON_TYPE` x `RESULT` 组合编写最简短的通用描述。
*   **要求**: 必须覆盖所有 Intent，通过 `accept_intents: ["ANY"]` 确保程序不报错。

### 步骤 4: 填充 T2 战术层 (The Meat)
*   **任务**: 对主流武器（光束步枪、光束剑、火箭筒）增加 T2 级别的详细描述。
*   **要求**: 引入 Action -> Reaction 的连贯性检查，确保“光束不产生弹壳”。

### 步骤 5: 植入 T1 技能演出 (The Soul)
*   **任务**: 挑选 5-10 个核心技能（如“王牌机师”、“底力”、“NT感应”），编写专属 T1 规则。
*   **要求**: 配合前端特效 ID，设计 Cut-in演出点。

---

## 7. 案例模板展示 (Case Template Showcase)

为了直观理解“意图+优先级+部位”的运作，以下展示三个典型的演出配置案例。

### 案例 A：高精密打击（意图驱动 + 部位特化）

*   **输入数据**: 武器：狙击步枪，结果：暴击，部位：`HEAD`。
*   **演出逻辑**:
    1.  系统抽中 `HEAD`，自动注入 `TAG_LOC_HEAD`。
    2.  **Action (T2)**: 匹配到“精确狙击”条目，输出内容：`{attacker} 冷静地修正了风偏，光束穿透了传感器的死角。` 意图：`INTENT_BEAM_INSTANT`。
    3.  **Reaction (T1)**: 匹配到 `TAG_LOC_HEAD` + `accepts: BEAM_INSTANT` 条目。
    4.  **最终文本**: `[Action] 独角兽高达冷静地修正了风偏，光束穿透了传感器的死角。[Reaction] 报丧女妖的头部主监视器被瞬间熔穿，电火花在驾驶舱屏幕上疯狂跳动。`

### 案例 B：战术格挡（意图握手 + 资源联动）

*   **输入数据**: 武器：热能斧，结果：格挡，意图：`INTENT_SLASH_HEAVY`。
*   **演出逻辑**:
    1.  **Action (T2)**: `扎古挥动加热到红热状态的热能斧，带着沉重的质量向下劈砍。`
    2.  **Reaction (T2)**: 匹配 `BLOCK` + `accepts: SLASH_HEAVY` 条目。
    3.  **最终文本**: `[Action] 扎古挥动加热到红热状态的热能斧，带着沉重的质量向下劈砍。[Reaction] 高达举起盾牌死死抵住对方的刃部，红热的金属摩擦声刺痛着驾驶员的耳膜。`

### 案例 C：技能觉醒（优先级瀑布 T1 抢占）

*   **输入数据**: 触发技能：`底力 (POTENTIAL)`，结果：被击中。
*   **演出逻辑**:
    1.  注入 `TAG_SKILL_POTENTIAL`。
    2.  **Presentation (T1)**: 扫描到 `TAG_SKILL_POTENTIAL` 规则，直接抢占 T2/T3。
    3.  **最终文本**: `[Cut-in: 斗气爆发特效] 哪怕装甲在悲鸣，真治的眼神却愈发凝练——初号机在损伤中爆发出了超越极限的功率，强行稳住了机身。`

---

## 8. 总结

本指南的核心是通过 **握手协议** 和 **优先级瀑布** 来管理演出的复杂性。
*   **Action** 负责定义“我做了什么”（Intent）。
*   **Reaction** 负责定义“我能应对什么”（Accept）。
*   **Skill** 负责在两者之间插入高光时刻（Priority T1）。

遵循此逻辑，新增一个技能或武器只需添加少量配置条目，而无需修改现有代码，从而实现低成本的可持续维护。