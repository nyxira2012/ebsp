一、现状诊断：代码 vs 文档的核心差距
通过对比文档 6 与现有代码，发现以下 6 个关键问题：

#	问题	受影响文件	文档对应机制
P1	ODR 路由缺失：
mapper.py
 没有"结局前置路由"，致死判定由下游 selector 末端处理，存在路由失效风险	
mapper.py
 L51~85	机制 1
P2	攻防未解耦：
PresentationTemplate
 仍是大一统结构（action_text + reaction_text 捆绑），无法独立竞标	
template.py
机制 3
P3	T2 缺乏原子化：
presentation.yaml
 中模板是完整长句，
_pick_t2
 只是 random.choice，没有三段拼装	
selector.py
 L92~96, 
presentation.yaml
机制 5
P4	DHL 是占位符：
_create_reaction_event
 中 hit_location="body" 是硬编码，未实现动态部位映射	
mapper.py
 L159	机制 12
P5	物理类约束缺失：
IntentExtractor
 只抽取意图，无物理类（Energy/Kinetic/Blade/Impact）概念，模板无法按物理类约束受击描述	
intent_extractor.py
, 
constants.py
机制 4
P6	
RawAttackEvent
 契约不完整：缺少 spirit_commands 字段在 
AttackEventBuilder
 中的填充逻辑	
event_builder.py
 L74~116	数据契约
二、重构目标
重构后的系统需满足：

RawAttackEvent
    → [L1: ODR Router] → Channel (FATAL/EVADE/IMPACT/SPECIAL)
    → [L2: Dual Bidder] → ActionBone + ReactionBone (独立竞标)
    → [L3: Assembler]  → final_text (原子拼装 + SVI注入 + DHL部位)
    → [L4: AV Dispatch]→ PresentationAttackEvent (镜头/特效/节奏)
三、重构路线图（分步骤）
📦 Phase 0：数据契约补全（前置，不影响现有功能）
目标：补全引擎和演出之间的数据接口，为后续层奠定基础。

Step 0.1：
RawAttackEvent
 增加字段
方法：在 
models.py
 的 
RawAttackEvent
 中新增两个字段（已有定义但未使用）：

spirit_commands: List[str]  ← 已存在，但 builder 未填充
is_lethal: bool             ← 【新增】预计算的致死标志
physics_class: str          ← 【新增】Energy/Kinetic/Blade/Impact
为什么需要 is_lethal 字段：ODR 的"终局扫描"必须在第一步执行。若每次由 L1 重新计算 hp_after <= 0，逻辑可以工作，但将"是否致死"这个战斗引擎最权威的结论留在演出侧计算违反契约原则。让引擎在 
AttackEventBuilder
 中直接填写 is_lethal=damage >= defender.current_hp，演出侧无需反算。

Step 0.2：AttackEventBuilder.build() 填充新字段
方法：在 
build()
 的参数列表和返回值中补充：

spirit_commands 从 ctx 或调用方传入
is_lethal = (damage >= defender.current_hp_before_damage)（引擎层已知）
physics_class 根据 weapon.tags 在 Builder 内一次性计算，抽取为 _classify_physics(tags) -> str
核心逻辑（不需要写很多代码，一个 if/elif 链）：

if "beam" in tags: return "Energy"
if "missile/projectile/shell" in tags: return "Kinetic"  
if "slash/blade/saber" in tags: return "Blade"
return "Impact"
🔴 Phase 1：L1 ODR 路由层（核心优先级最高）
目标：在 
mapper.py
 的 
map_attack()
 入口实现"结局前置路由"，完全按文档机制 1 执行。

Step 1.1：将路由逻辑提取为 OutcomeRouter 类
方法：新建 src/presentation/router.py，不超过 60 行。

OutcomeRouter.route(event: RawAttackEvent) -> Channel

Channel 是一个新枚举（加入 
constants.py
）：

python
class Channel(str, Enum):
    FATAL   = "FATAL"    # 致死
    EVADE   = "EVADE"    # 闪避/招架/未命中
    IMPACT  = "IMPACT"   # 命中/格挡/暴击
    SPECIAL = "SPECIAL"  # 支援/反击
路由优先级（严格有序）：

event.is_lethal → FATAL
event.is_counter or event.is_support → SPECIAL
event.attack_result in (MISS, DODGE, PARRY) → EVADE
其余 → IMPACT
为什么要单独建类：
map_attack()
 目前把 T0、T1、lethal 判定、hp 计算混在一起，职责不清。OutcomeRouter 对应文档"频道领土锁定"的物理实现，它的输出 channel 是后续所有层的"门卫令牌"。

Step 1.2：修改 mapper.map_attack() 的主流程
方法：将 
map_attack()
 改为严格的四步流水线：

python
def map_attack(self, raw_event):
    # L1: ODR
    channel = OutcomeRouter.route(raw_event)
    
    # T0 拦截（脚本优先，独立于流水线）
    if forced := self.scripted_manager.get_forced_template(...):
        return self._build_events(raw_event, forced, channel)
    
    # L2: Dual Bidder
    action_bone, react_bone = self.bidder.bid(raw_event, channel)
    
    # L3: Assemble
    final_text_pair = self.assembler.assemble(action_bone, react_bone, raw_event)
    
    # L4: AV Dispatch
    return self.av_dispatcher.dispatch(raw_event, final_text_pair, channel)
这让 
mapper.py
 变成纯粹的"导演"，它不再包含任何业务逻辑。

🟠 Phase 2：L2 双轨解耦（攻防独立竞标）
目标：实现文档机制 3"动反双轨独立竞标"。

Step 2.1：拆分模板数据模型
方法：修改 
template.py
 中的 
PresentationTemplate
，将内容层拆分：

python
# 旧方式（一体模板）
class TemplateContent:
    action_text: str
    reaction_text: str
# 新方式（原子骨架）
class ActionBone:
    bone_id: str
    intent: VisualIntent
    physics_class: str
    text_fragments: List[str]  # 用于 L3 拼装
    anim_id: str
    
class ReactionBone:
    bone_id: str
    channel: Channel           # 只匹配对应频道
    physics_class: str
    text_fragments: List[str]
    vfx_ids: List[str]
关键原则：ActionBone 关心"谁、用什么、怎么打"；ReactionBone 关心"频道是什么、物理类是什么、反应如何"。二者通过 physics_class 做软约束（同族物理才能组合出合理的画面）。

Step 2.2：实现 DualBidder
方法：新建 src/presentation/bidder.py。

DualBidder.bid(event, channel) -> (ActionBone, ReactionBone)

内部逻辑：

Action 竞标：过滤 intent 匹配 + cooldown 清零 的 ActionBone 列表，用优先级分排序
Reaction 竞标：过滤 channel 匹配 + physics_class 兼容 的 ReactionBone 列表，随机加权选出
两次竞标完全独立，互不影响
为什么不合并：若攻守捆绑，10攻+10守只有10种组合；解耦后得到100种。这是文档"组合红利"的数学基础。

Step 2.3：更新 YAML 数据格式
方法：将 
presentation.yaml
 的 templates 分拆为 action_bones 和 reaction_bones 两个独立 section：

yaml
action_bones:
  - bone_id: "act_beam_rifle_shoot"
    intent: BEAM_INSTANT
    physics_class: Energy
    tier: T2_TACTICAL
    text_fragments:
      - "{attacker}锁定能量特征，随着电荷汇聚完毕"
      - "{attacker}的{weapon}瞄准系统锁定目标"
    anim_id: "anim_rifle_shoot_01"
reaction_bones:
  - bone_id: "react_energy_hit"
    channel: IMPACT
    physics_class: Energy
    tier: T2_TACTICAL
    text_fragments:
      - "光束灼穿{defender}的装甲表面，留下熔融痕迹"
      - "{defender}的装甲涂层在高热中迅速蒸发"
    vfx_ids: ["vfx_beam_impact", "vfx_armor_melt"]
旧的大一统 templates 列表保留做兼容（T0_LETHAL 模板不需要解耦）。

🟡 Phase 3：L3 动态丰满（原子拼装 + DHL + SVI）
目标：实现机制 5（原子化组合）、机制 6（SVI 注入）、机制 12（DHL 部位映射）。

Step 3.1：TextAssembler 三段式拼装
方法：新建 src/presentation/assembler.py。

TextAssembler.assemble(action_bone, react_bone, event) -> (action_text, react_text)

三段拼装公式（对应文档机制 5）：

action_text = [启动姿态 from action_bone.text_fragments[0]] 
            + [执行过程 根据 is_first_attack / spirit_commands 选词]
            + [意图标签 根据 VisualIntent 注入]
react_text  = [受击部位 from DHL]
            + [物理反馈 from react_bone.text_fragments]
            + [状态反馈 从 damage_grade 和 hp_status 选词]
实施关键：每个"段"是一个小词库（字典），系统在运行时 random.choice() 组合。文字内容在 YAML 里扩展，代码只管拼装逻辑。

Step 3.2：DHL 动态部位映射
方法：在 assembler.py 中增加 DhlMapper 内部类（或静态方法）：

python
DHL_MAP = {
    "FATAL":  ["驾驶舱", "动力炉"],
    "CRIT":   ["主摄像机", "推进器端口", "关节部位"],
    "HIT":    ["外装甲", "机体侧翼", "腰部装甲"],
    "BLOCK":  ["盾牌表面", "前装甲"],
    "EVADE":  [],  # 没有受击部位
}
逻辑（文档机制 12）：

channel 决定候选部位池
random.choice() 选出 {hit_part}
同时写入 PresentationAttackEvent.hit_location（供 L4 驱动视觉损毁）
Step 3.3：SVI 变量注入
方法：在 assembler.py 中统一处理 str.format() 的变量字典：

python
variables = {
    "attacker": event.attacker_name,
    "defender": event.defender_name,
    "weapon":   event.weapon_name,
    "hit_part": dhl_result,
    "skill_name": _pick_skill_label(event.triggered_skills, event.spirit_commands),
    "damage_grade": _get_damage_grade(event.damage, event.defender_max_hp),
}
_pick_skill_label() 优先返回精神指令名（"热血"、"魂"），其次返回触发技能名，最后返回武器名。这是文档机制 6 的核心策略。

🟢 Phase 4：L4 AV 调度（镜头与节奏）
目标：将散落在 
_create_action_event()
 和 
_create_reaction_event()
 中的魔法数字和 if/else 提取为规则驱动的调度器。

Step 4.1：AVDispatcher 规则树
方法：新建 src/presentation/av_dispatcher.py。

将 
mapper.py
 中分散的相机 if/else 改写为规则表：

python
CAMERA_RULES = [
    # (优先级, 条件函数, 摄像机ID)
    (100, lambda e, ch: ch == Channel.FATAL,            "cam_dramatic_zoom"),
    (90,  lambda e, ch: e.attack_result == "CRIT",      "cam_dramatic_zoom"),
    (80,  lambda e, ch: e.distance > 800,               "cam_long_shot"),
    (70,  lambda e, ch: e.distance < 100,               "cam_close_up"),
    (60,  lambda e, ch: e.attack_result == "DODGE",     "cam_tracking_evade"),
    (50,  lambda e, ch: e.damage > 500,                 "cam_shake_heavy"),
    (0,   lambda e, ch: True,                           "cam_default"),
]
取优先级最高的匹配规则，消灭硬编码阈值 500（改为从配置读取）。

Step 4.2：时间轴 timestamp 自适应（机制 10，阶段C）
方法：AVDispatcher.dispatch() 根据规则计算 reaction_timestamp：

python
base_delay = 1.5
if event.attack_result == "CRIT": base_delay += 0.5
if intent == VisualIntent.BEAM_MASSIVE: base_delay += 0.3
这就是文档"语义化时间轴自适应"的最小实现，只需几行，但效果显著。

四、各文件变更摘要
src/presentation/
├── constants.py        ← 【修改】新增 Channel 枚举, PhysicsClass 枚举
├── models.py           ← 【修改】RawAttackEvent 增加 is_lethal, physics_class
├── template.py         ← 【修改】新增 ActionBone, ReactionBone dataclass
├── event_builder.py    ← 【修改】填充 spirit_commands, is_lethal, physics_class
├── router.py           ← 【新建】OutcomeRouter (L1)
├── bidder.py           ← 【新建】DualBidder (L2)
├── assembler.py        ← 【新建】TextAssembler + DhlMapper (L3)
├── av_dispatcher.py    ← 【新建】AVDispatcher (L4)
├── mapper.py           ← 【大改】精简为纯流水线编排，删除业务逻辑
├── selector.py         ← 【弱化】冷却/权重衰减逻辑迁移入 Bidder，可逐步退役
├── helpers.py          ← 【保留】HpStatus 和 calculate_hp_status
├── loader.py           ← 【修改】支持解析 action_bones / reaction_bones
└── registry.py         ← 【修改】分别索引 ActionBone / ReactionBone 库
data/config/
└── presentation.yaml   ← 【大改】增加 action_bones / reaction_bones 两个 section
五、兼容与迁移策略
原则：不要一次性重写，按层迭代，保证每个 Phase 后测试可通过

Phase 0：
RawAttackEvent
 新字段全部设默认值，零破坏性
Phase 1：OutcomeRouter 新建后，在 
mapper.py
 内仅插入路由调用，旧逻辑暂时保留在分支中
Phase 2：DualBidder 和新 YAML 格式并行存在。
Loader
 先尝试解析新格式，失败则回退到旧 templates 列表解析。
Selector
 暂时作为旧路径的备用
Phase 3：TextAssembler 建立后，只对"有 ActionBone + ReactionBone"的事件走新路径；仍使用旧 TemplateContent 的走旧路径
Phase 4：AVDispatcher 直接替换 
_create_action_event
 和 
_create_reaction_event
 中散落的逻辑
六、实施优先级建议
P0 (本周) → Phase 0 + Phase 1   [数据契约 + ODR 路由]
P1 (下周) → Phase 2             [双轨解耦 + YAML 重构]
P2 (后续) → Phase 3             [原子组装 + DHL]
P3 (稳定后) → Phase 4           [AV 调度规则化]
Phase 1 的收益最高、风险最低，是最值得优先实施的一步。 Phase 2 的 YAML 重构是工作量最大的一步，但它是让"组合爆炸"变成现实的关键。