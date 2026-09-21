# Development Log (DEVLOG.md)

## 2026-09-21 用户系统批B「401 收口」落地——文档7后端收口（Doc 7 §11.0，gate 先行兑现）

> **项目快照**：批B 唯一剩余后端项，按其自带的 gate 顺序执行——ebs-duo 登录最小闭环先行合入，随即落 401 收口 | simulate/练习场强制登录、匿名回退语义整体废除 | Doc 16 v1.5 + Doc 14 v1.9 升版 | 测试 677→679 全绿，Pyright 0 错误

### 执行顺序说明（gate 不是摆设）

批B的放行条件是 ebs-duo 前端登录闭环（注册/登录页 + apiClient token 注入 + 401 拦截，Doc 7 §11.0），本次按序兑现：先落前端闭环（`#/auth` 注册/登录页 + `engine/session` token 持久化 + `fetchEngineJson` 全通路 Bearer 注入与 401 统一拦截），再收后端口子。注意区分：ebs-duo 的 4.1 门面登录页（`#/login`）是彩蛋页，其规格明文"不是真账号系统"，与本次闭环无关。

### 交付内容（批B）

1. **simulate/practice 强制登录**（`src/api/presentation_api.py`）：两端点换 `get_current_user`，匿名 401；练习场 v1.0"无鉴权只读"裁决随之废除（Doc 16 v1.5 落字）。
2. **匿名回退语义整体废除**：`get_optional_user`/`optional_security` 移除（`src/user/dependencies.py` + `user/__init__` re-export，消费面清零）；`build_debug` 签名收口为 `user: User`（`src/combat/entry.py`），`user is not None` 分支删除——存档缺陷降级臂保留（养成数据无效仍降级演示配置，Doc 14 §2 语义）。
3. **存量匿名用例重写**（F6 清单）：`test_practice_api.py` 七例改登录态 + 新增匿名 401 断言；`test_battle_entry.py` 两例 HTTP 用例改 `authenticated_client` + 新增匿名 401 用例，三例 build_debug 直构用例改持离线 User（不再传 None）；`authenticated_client` 通用夹具仿 test_inventory_api.py 上提 `tests/conftest.py`（inventory 本地特化版保留，同名遮蔽）。

### 文档联动（Doc 7 §11.7 清单）

- **Doc 16 v1.5**：§2 列表鉴权收口；§2.1 降级口径"四态作废两态"（匿名臂死于 401、无编队臂死于批A 400 分流，仅存存档缺陷一态）；新号动线两段式注记（领取前 `use_user_save=false` 演示局即可玩）。字段契约不变（八项）。
- **Doc 14 v1.9**：§2 鉴权改强制 JWT；错误码补 `401` 与 `400` 两码分流，冻结 401（`detail` 字符串）与 400（`detail: {code, message, ...}`）错误体结构——前端按状态码 + `detail.code` 分支。
- roadmap §9 批B ✅、§1 ebs-duo 登录闭环 ✅。

### 坑（下一个实现者会踩的）

- **登录接口自身的 401 别落进全局拦截**：`POST /user/login` 凭据错误也回 401——前端 `fetchEngineJson` 的 401 拦截（清会话+跳 `#/auth`）若先吃掉它，登录页会把自己弹走。解法是 statusErrors 先行抛出（登录通路自备 `{ 401: '账号或密码错误' }`），骨架顺序：statusErrors → 401 拦截 → ok 检查。
- **ebs-duo 取数是单点骨架**：token 注入与 401 拦截都落在 `engine/client.js#fetchEngineJson` 一处（全站唯一 fetch 通路，已核实无裸 fetch）；调用方显式传的 Authorization 头优先不被覆盖（战报重放自管 token 通路不受影响）。
- **测试配置 `-rN` 吞摘要**：pytest.ini 不打印 passed 汇总行，验收看退出码与 `--collect-only -q` 计数（当前 679）。

---

## 2026-09-21 用户系统 v2.3 开发期放宽——编队不再强制进入战斗（Doc 7 §11.2.1）

> **项目快照**：用户裁决"编队内容不要设置成必须的，因为这是开发中" | enter 通道拆除无编队 400 门槛，恢复演示机体回退（`mech_rx78` 正确 ID）| 测试 676→677 全绿

### 交付内容

1. **`_prepare_locked_config` 回退链恢复并修正**（`src/pve/services.py`）：未锁定机体 → 取出战编队 → 仍无有效编队 → 回退演示机体 `mech_rx78` 静态快照（条目无 `user_mecha_id`，与养成快照区分）。v2.2 拆掉的 "rx78" 定性修正：真地雷是假 ID 让旧回退永远 KeyError 落空，回退语义本身开发期合理。
2. **enter-region 前置门槛拆除**（`src/api/pve_api.py`）：`assert_squad_ready` 从 enter 通道移除，`STARTER_NOT_CLAIMED`/`NO_ACTIVE_SQUAD` 两码在 enter 停用；`locked_mechas` 显式指定的归属校验（`MECHA_NOT_OWNED`）保留。

### 保留不变

- simulate 勾 `use_user_save` 仍走编队就绪 400 分流（显式请求存档，静默降级违背显式语义）；
- 归属校验全量保留（建队/部署/会话属主）；claim-starter 与 `/user/me` 引导状态位照旧。
- 转正条件：编队玩法正式化（阵位/轮换）时恢复 enter 前置校验，§11.2.1 随即废除。

### 测试

- `test_prepare_locked_config_empty_raises` → `test_prepare_locked_config_empty_falls_back_to_demo` + 新增 `test_prepare_locked_config_demo_config_missing_raises`（缺陷级 ValueError 兜底）；
- `test_enter_region_without_claim_points_to_claim` / `..._with_mecha_but_no_squad_points_to_squad` 改断言 200 回退进入（含内存态会话管理器跨用例销毁收尾）；
- 全量 677 passed。

---

## 2026-09-21 用户系统 v2.2 批A收口——新号动线与属主安全（Doc 7 §11）

> **项目快照**：newfun 三轮拷问（D1–D13，用户逐项批复）+ 四角色评审（26 条 findings，用户拍板拆批与 ms_01 拆雷）| 批A 落地：claim-starter、400 结构化分流、PVE/编队属主、三处地雷拆除 | 测试 643→676 全绿，Pyright 0 错误

### 交付内容（批A「新号动线与属主安全」）

1. **claim-starter（`POST /user/mechas/claim-starter`）**：免费领取 `mech_grunt` + 编队防御性补齐（无队建「默认编队」，有队塞入并激活）+ 出战标记，同事务落库；users 行锁串行化并发领取，重复领取 409 附当前资产摘要（终态等价成功语义）。`/user/me` 扩 `has_mecha`/`has_active_squad` 引导状态位。破除 D3+D4 死锁（新号无机体进不了任何战斗）。
2. **无编队 400 结构化分流**：simulate 勾 `use_user_save` 与 PVE enter-region 前置校验——无机体质 `STARTER_NOT_CLAIMED`、有机体无有效编队 `NO_ACTIVE_SQUAD`，不再指错门/静默回退。
3. **PVE 属主统一入口**：`get_pve_session_or_404(session_id, user_id)` 六端点接入（含重放端点换用），他人会话与不存在同口径 404。
4. **编队引用完整性**：create_squad 校验 `mecha_ids` 归属（他人机体 400 `MECHA_NOT_OWNED`，封堵借队以他人养成资产出账的后门）；`set_active_squad` 补属主过滤（现状即可激活他人编队，评审侦察员 F2）；`get_active_squad` 改 `.first()` 防存量双激活 500。
5. **三处地雷拆除**：engage/extract 母舰硬编码 `ms_01` 改读玩家当前母舰记录（D13）；`_prepare_locked_config` 与 build_pve 三处 `rx78` 假 ID 静默回退改显式 ValueError——顺手发现并补实"空锁定取出战编队"语义从未实装（旧实现全靠假 ID 回退兜底）。

### 关键裁决

- **D12 拆批**：401 收口（simulate/练习场强制登录、匿名回退删除、Doc 16/14 修订、存量用例重写）独立为批B，gate 在 ebs-duo 前端登录闭环——顾问 F1：后端 401 先落地会掐死 roadmap 第一优先级（前端练习场全链路验证）。
- **D13 ms_01 顺手拆**：否则新号全链在 engage 断头（测试全绿但玩家动线 500），验收新增 `test_new_account_full_pve_chain`（enter→advance→engage→extract 全程 2xx）。
- **评审否决与采纳**：金样张 401 全红之虞被侦察员证据否决（直构路径不经 HTTP）；claim 并发双领、409 死胡同、编队后门等 9 项 Blocker 全部采纳落地；extract 幂等缓存次序与 replay 锚会话寿命为存量语义，挂账不混入。

### 留痕

- 拷问记录：`docs/tmp/7_需求拷问记录.md`（D1–D13）
- 评审 findings：`docs/tmp/7_评审findings.md`（四角色 26 条 + 处置）
- 契约：`docs/7.user_system_implementation.md` v2.2 §11（含 §11.0 批A/批B拆分与 §11.8 测试要求）
- 新用例：`tests/api/test_user_onboarding.py`（11 项）；存量回退用例重写 3 处（test_battle_entry.py / test_pve_services.py ×2）

## 2026-09-19 Doc 16 v1.2/v1.3 实现：环境通道 + 训练力场 + 防御测试木桩上线（mawang 两批交付）

> **项目快照**：D9 设计落地 | 引擎零改动（engine/resolver 未动）| 列表契约七项→八项（增 `environment_id`，主 agent 裁决待追认）| 防御局 5 种子实测 45–53 回合落 D4 带带 | 测试 643→665 全绿 | 新增 data/environments.json（训练力场/靶场/野战）

### 落点裁决

1. **效果注入落装配层（entry.py 收发室），不落引擎也不落特质链**：`_apply_environment` 在存档覆盖之后、EngagementSpec 构造之前注入——降级到演示配置时力场同样生效；spec 构造即深拷贝（Effect 元素粒度也逐个拷贝），护栏结构性成立。否掉引擎侧方案：环境对引擎不可见（只见效果），`HOOK_ON_DAMAGE_TAKEN` 返回值即落血伤害的现成语义足够。
2. **免死钳制身份判定用 `is` 不用 `==`**：pydantic BaseModel 相等按字段值，镜像同配双快照会误判；`ctx.get_defender()` 以 ctx.weapon 归属推导受击方，效果持有者由 processor 从 ctx 原对象配对——`owner is defender` 在真实引擎路径恒成立（攻击期 ctx 恒以 mecha_a=攻方构建）。
3. **钳制效果 priority=100**：同钩子按优先级升序执行、高者最后执行拥有最终决定权——钳制必须吃在其他伤害修正之后，否则会被后续效果改写。
4. **列表条目直带 `environment_id`（七项→八项）**：D9 留下的缺口——前端从哪拿条目环境 ID？隐映射（kind 反猜环境）是两处真相会漂的老病。环境 ID 是规则上下文引用不属红线封锁面（不泄数值、不携图片），D9 已授权 v1.2 契约版本化切换。会话内用户未应答，主 agent 按授权内判断落地，**Doc 16 §7 留痕待追认**（否决则删字段回退，可逆单点）。
5. **环境不进战报 meta**（用户开工裁决）：前端自选自知，进 meta 只扩契约面；将来按环境渲染背景走 Doc 14 非破坏增补先例。

### 坑（下一个实现者会踩的）

- **生产链路被动技能是死链**：`TraitManager.apply_traits` 无任何 src 调用方（仅测试直调），快照 `.skills` 字符串列表从不转成 Effect——"现成模式"现成的是效果处理管线，不是特性自动挂载。环境效果必须自己显式 append（本次 `_apply_environment` 即是）。将来接特质挂载链时别假设它已生效。
- **conftest 每测试清空 SkillRegistry 注册表 + reload 还原义务**：全战斗 API 测试要 `importlib.reload(src.skills)` 重注册回调；reload 会把模块属性重绑到新类，测试结束**必须还原模块属性**（processor 调用期按模块属性懒加载拿新类、engine 顶层导入持旧类，不还原则注册与查找落两类——实测红过 test_integration_complex/test_skills_processor 各一例）。夹具已上移 tests/conftest.py 共享（`reloaded_skills`），别再复制本地副本。
- **兜底撞击会从距离空档劫持**：只配 EN 经济不够——第一回合距离收敛带 3000–7000，武器射程并集若留空档（如步枪 ≤6000 + 锤 ≤1200），空档回合双武器齐哑照样触发威力 600 兜底撞击。重火力木桩补了 `wpn_bazooka`（3000–8000）封死距离维，EN 维 20/回合 > 最贵 15/发，两个维度结构性不可达（5 种子零出现）。
- **dict 撞键"保位置换值"，装载后去重不可达**：`container[obj.id] = obj` 对已有键只换值不换位置——加载完再想 keep-first 已无物可去重。先到先得必须在装载期拦截（`_load_from_json` 的 opt-in `keep_first` 参数，仅 environments/practice_scenarios 开启）。
- **策展内容里免死护栏是待命态**：重火力木桩最高单发对演示机体非致死，钳制在策展局不实际触发——这是对的（护栏本该兜真实入场路径：登录玩家低血存档 `use_user_save_for_a` 才接致死刀）。别为了"验证护栏"去调高木桩单发，那会摧毁"看每回合被打穿多少"的观察价值。

### 交付物

- 代码（3 批提交）：环境通道（EnvironmentConfig/Grant + 容缺加载与交叉校验 + 装配期注入）、`env_regen_full`/`env_no_death` 两效果与回调、练习场契约切换（kind 环境派生 + environment_id 透传）、mech_defense_dummy + practice_defense_dummy 上线、撞键先到先得收口。金样张/debug 老路径零变化（缺省 environment_id=None 不注入）。
- 文档：Doc 16 v1.3（八项契约、实现注记、实现偏差 §7）、Doc 14 v1.8（§2 请求增补 environment_id）。
- 测试：test_environment_effects.py（19 测：钳制四态+镜像钉+全链路 processor+注入/隔离+加载校验）、test_practice_api.py（八项契约+content_floor 反转+防御局全链路免死断言）、test_loader.py（撞键 keep-first）。全量 665 passed、pyright 0 新增错误。

## 2026-09-19 D9 设计修订：防御测试机制改"快照注入 + 环境通道"（纯设计，引擎文档同步）

> **项目快照**：用户两轮拍板（效果注入玩家快照 / 环境标注战斗类型）| Doc 16 v1.2 + Doc 15 v1.5 + Doc 1 §5.3 + roadmap §1 修账 | 顺手去重 kind 枚举声明 | 测试 643 不变全绿

### 落点裁决

1. **机制 v2（D9）**：训练力场=两个技能效果（回合回满、致死钳制），进入木桩战斗时**装配期注入玩家快照**——快照每场深拷贝，效果不落存档/共用机体表/PVE，护栏从纪律变构造。管线事实双确认：回满走 `cb_regen_hp` 同款自向回调（HOOK_ON_TURN_END）；免死走 `HOOK_ON_DAMAGE_TAKEN` 钳制，该钩子返回值即落血伤害（resolver.py 落血前最后一站）——**零引擎改动**，评审 B2 的特质挂载链三环整个绕开。
2. **环境通道吸收 kind**：环境（ID+名称+可选按侧授予效果）成为战斗委托级规则上下文（`EngagementContext.scene` 槽升级为 `environment_id`）；`kind` 在 v1.2 实现时被环境吸收（场景引用环境、角标从环境派生，契约随 v1.2 版本化切换）；route（来源）×环境（规则）正交。否掉：木桩特质跨方向（原 D7，需跨方向副作用机器+护栏靠纪律）、木桩机体惰性标记（设施语义在场合不在机体+roadmap §1 环境管道迟早要开）、请求加 kind 参数（契约加宽+匿名免死口子）。
3. **引擎预留现状核账**：`Terrain` 枚举与 `BattleContext.terrain` 槽位在、**全库零消费**；roadmap §1"伤害公式含地形适应性"的 🟩 标记超前，已修正；将来地形补正挂环境通道扩展不再另开槽。
4. **v1.2 排期（D8）维持但理由减半**：特质链不再是前置，剩余依赖只有底力死亡语义的文档口径（随技能系统 Doc 2 定调，钳制形态为其第一实现候选）。

### 坑（下一个实现者会踩的）

- **钳制效果必须判 owner==受击方**：HOOK_ON_DAMAGE_TAKEN 处理器对双方效果都跑，不判会把木桩挨的刀也钳到 1。
- **快照注入的时机**：在 EngagementSpec 构造前注入（spec 构造即深拷贝冻结），注入的是拷贝链上正确的那份。
- **工厂 falsy-or 前科**：本次已修 0 值吞默认（见上条日志）；环境配置装载时同理——0/空串/空列表是合法值就用 None 检查。

### 交付物

- Doc 16 v1.2（§5.3 重写为环境通道方案、§7 增 D9、变更记录 1.2）；Doc 15 v1.5（§3 scene 槽升级说明）；Doc 1 新增 §5.3 战场环境通道规划节；roadmap §1 两条修账。
- 代码仅一处去重：`PracticeScenarioItem.kind` 改引 `PracticeScenarioKind` 别名（models 单源）。643 passed、pyright 0 errors。

## 2026-09-19 练习场 newfun 收口（Doc 16 v1.1 定稿并实现零引擎增量）

> **项目快照**：newfun 三轮拷问（D1-D7）+ 四角色评审（D8，用户批复"按建议来改"）| v1.1 落地：七字段列表、route=training、攻击测试木桩 | 顺手修复快照工厂 falsy-or 吞 0 值保真 bug | 测试 640→643 全绿

### 落点裁决（为什么落这里、否掉了哪里）

1. **文档形态（D0）→ 保持后端契约形态，用 newfun 流程收口**（Doc 15 拷问 D1 同款先例）：不转纯人话规格（一份文档两种受众互相干扰）。lint 的 S2/S3（无场景四段/无验收勾选）与全部 ⚠️ 技术词为该形态的已知偏差，随先例携带。
2. **三轮拷问七裁决**（留痕 tmp/16_需求拷问记录.md）：D1 登录默认玩家自己的出战机体（试车场定位，场景配置降为演示/降级配置）；D2 列表带双方机体官方名（名字单一真相归后端，加载器派生）；D3 现在引入 route=training（Doc 14 v1.7 可选参数，客户端只可声明 debug/training，pve/pvp 422 拒）；D4 木桩时长配置凑合（高血量约 50 回合，真无限违反裁定封闭+战报预算被否）；D5 木桩双生（攻击测试+防御测试）；D6 类别声明在场景级 kind 字段（D4 后无战斗行为耦合，机体表不掺产品语义）；D7 防御测试=训练力场（每回合奶满+免死，木桩特质跨方向授予，火力不限）。
3. **评审四角色**（findings 留痕 tmp/16_评审findings.md）：2 Blocker 消解——B1"登录但小队空"降级态被侦察员代码事实裁为措辞补全（entry.py 守卫本就静默降级）；B2 特质挂载链三环全缺（MechaConfig 无 skills 字段→simulate 聚合恒空→TraitManager 生产零调用）揭出引擎增量实况。D8 排期拆分（用户选 B）：v1.1 先落零引擎增量，防御木桩实现挂 v1.2 随 roadmap §4 技能系统同窗（底力被动触及死亡语义核心，不在练习场单方面塑形）；v1.2 前不得配置 defense_test 场景条目。
4. **实现期踩中的真雷（工厂 falsy-or）**：`wpn_dummy` 零耗能被 `en_cost or 10` 吞成 10——木桩约十回合耗竭 EN 后改用 600 威力兜底撞击把玩家磨死（真服务器四局实测三局撞死复现）。修复：`create_weapon_snapshot` 数值字段改 None 检查（0 是合法配置值），爆炸半径全库仅 wpn_dummy 一个 0 值武器。修复后四局实测：玩家全程满血、44-49 回合 KO（80,000 血量定标，免再调参）。

### 交付物

- Doc 16 v1.1（评审采纳全入册：降级四态合一、坏配置总则、力场护栏红线、登录态显示规范、内容底线）；Doc 14 v1.7（route 请求参数）。
- 代码：`PracticeScenarioConfig.kind`（Literal，非法值加载期剔除）、列表七字段（官方名派生）、`BattleRequest.route`、`entry.py` 装配接线、`factory.py` 0 值保真修复。
- 数据：mech_dummy（全装甲测试木桩）+ 木桩靶场场景（attack_test）；场景描述全部改为围绕敌方写（D1 之后卡片不再承诺"某机对某机"）。
- 测试：契约测试重写为七字段版 + 内容底线 + route 三态（默认 debug/training 生效/pve-pvp 422）+ 坏配置剔除两类。全量 643 passed、pyright 0 errors。

### 交接（下一步不在本会话）

- v1.2（防御测试木桩）：特质挂载链三环 + 底力型被动 + "恢复对方 HP"副作用类型（回合结束钩子处无攻防语义，"对方"须显式定侧）——随 roadmap §4 技能系统同窗，mawang 消费 Doc 16 §5.3。
- 前端练习场页：ebs-duo 侧立项（列表页+立绘对照表+"你的机体"显示规范）；提示 /naofu 登记新文档。

## 2026-09-19 收拾桌子 + 练习场最小一枪（Doc 16 立项并落地）

> **项目快照**：第0步 roadmap 进度对齐真实状态 | 第1步练习场后端全链路落地（`GET /battle/practice` + Doc 16 v1.0 + Doc 14 §9.1 裁决）| 测试 635→640 全绿

### 第0步：收拾桌子

- 31 个改动文件已在 864c3c1 落盘（工作区干净，无待提交代码）。
- roadmap（z.game_feature_roadmap.md）第 6/9 节进度标记对齐真实状态：§6 补"战斗编排与战报链路"🟨（Doc 15 四阶段已交付，母舰硬编码地雷如实标注）、线性副本推进/战术节点/物资提取翻 🟨 并注明遗留缺口；§9 账户鉴权翻 🟨（注册/登录/JWT/编队/母舰已实装）、Web GUI 翻 🟨（ebs-duo 已接通真实数据源）。Next Steps 校准：EXCLUSIVE 槽位检查已实装（factory.py）删去过时项，练习场登顶优先级 1，PVE 存量地雷列优先级 2。

### 第1步：练习场（落点裁决）

1. **文档归属 → 新建 Doc 16（练习场），不并入既有文档**。否掉的方案：并入 Doc 14（受众与生命周期错位——那是战报输出契约、实现后冻结，塞进配置列表接口稀释 SSOT）；并入 Doc 10/13（练习场无 PVE 语义：无会话/经济/属主）；并入 ebs-duo 前端文档（后端侧契约需要后端仓的锚点）。Doc 16 兼任跨端立绘规则的裁决落点。
2. **立绘规则当场定死（Doc 14 §9.1 待裁决 → 已裁决，用户拍板方案 A）**：后端契约只报配置 ID，图片路径归前端"配置 ID → 图片路径"对照表，缺图降级归前端（先例 ebs-duo 2.3 §4.4）；`init.portrait` 保留占位不携带路径语义，是否降级可空待前端对照表落地后随下版契约清理。无字段变更，金样张不动。
3. **接口最小化**：`GET /battle/practice` 只读、无鉴权、纯配置投影；条目字段恰为 名字/描述/`mecha_a_id`/`mecha_b_id` 四项（配置文件的 `id` 是容器键不进响应）；a/b 侧位语义对齐 Doc 14 §1.4。**不发明第二个开战入口**——前端拿条目直接打 simulate。
4. **配置加载两条规则**：内容级容缺（文件不存在=空列表不阻断启动，weapons.json 合并加载同款先例，保住临时目录测试）；交叉校验前置（引用不存在机体的条目加载期剔除——"列表能选、打不起来"的契约漂移在启动时暴露，不留到 simulate 404）。

### 验证

- 新增 `tests/api/test_practice_api.py` 5 项：字段恰四项（契约最小化）、机体引用存在、顺序保持、免鉴权、取列表第一场直接打 simulate 出 Doc 14 四块结构+结算（列表→开战链路锁定）；外加加载期剔除无效条目的单测。
- 真服务器（uvicorn 8765）全链路烟测：`GET /battle/practice` 4 场 → 取"初次出击"打 `POST /battle/simulate` → 3 回合 KO 结算（winner=b，高达 0% / 扎古 24.7%），演出事件 text/damage/attack_result 同源在场。
- 全量 640 passed；pyright 0 errors。

## 2026-09-18 战斗编排层 (Doc 15) 四阶段交付：P0/E1/P1/P2 全部落地

> **项目快照**：mawang 照 Doc 15 v1.2 实现 | 新增 contracts/engagement/entry 三模块 | simulate 收缩薄适配器 + PVE 接敌并入战报 | 影响战报的随机流全线注入 | 测试 581→630 全绿

### 落点裁决（为什么落这里、否掉了哪里）

1. **战报契约唯一拼装点 → `src/presentation/contracts.py` + `src/combat/engagement.py`（Doc 15 红线 1）**
   - 裁决：Doc 14 四块结构一次建模到位（含当时尚未生产的 P1 字段，给中性默认）；装配逻辑（presentation_timeline → 契约模型）只住在裁判 Engagement 里，`/battle/simulate` 挂 `response_model=TimelineDocument` 后缩为薄适配器。
   - 否掉的方案：JSONRenderer 补字段（Doc 14 v1.0 §8 原路线）——双装配点必然漂移，正是立项要消除的病根；实现后 JSONRenderer 全库零消费方，已删除（TextRenderer 保留，引擎在用）。
2. **装配单点 → `src/combat/entry.py` BattleEntryService（Doc 15 红线 5）**
   - 裁决：build_debug（simulate 静态配置+用户存档覆盖链）/ build_pve（locked_config 还原+时间回能+敌方实例化）两来源适配收编；battle_bridge 瘦身为"裁定后一次性写回"（305→200 行），PVE 侧零引擎 import（红线 2）。
   - 否掉的方案：把装配留在 handler 各写一份（现状）——训练/PVP 接入时必然再添装配点。
3. **快照值冻结 → 双层深拷贝**：EngagementSpec 构造即 `model_copy(deep=True)`（防调用方后续改动），resolve 时再拷一份喂引擎（引擎原地 mutate 快照）——init 块读 spec 原值，两层缺一不可。
4. **失败原子 → 装配零 mutation + 写回后置**：build_pve 全程不碰 session（回能算进快照拷贝），enemy_states 新建条目推迟到裁定成功后落盘；resolve 抛错 = session 零变更（有测试深比对锁定）。
5. **随机流注入 → 实例注入 + 模块回落（Doc 15 红线 3）**
   - 裁决：`rng=None` 时组件持有 `random` 模块对象（调用期属性查找）——**既有 22+ 测试文件的 `patch("random.uniform"...)` 全部继续生效**，这是注入方案不破坏存量测试的关键；BattleContext.rng 走 ctx 携带（resolver/processor/skills 回调链本就持有 ctx）。
   - 收编范围：影响战报的 12 点（圆桌/先手/距离/技能触发/本能/竞标×3/部位/状态词/片段×2）+ 六处战场内部 hook ctx；外围 4 类（掉落/装备生成/事件序列/隐藏节点）维持全局。
6. **裁定口径**：ruling 弃引擎 `a_wins/b_wins`，直接看战后快照推导 finish（ko/decision/draw）+ winner 正交表达；`timeline.result` 与 `report.ruling` 同一对象（三产物同源不变量）。

### 坑（下一个实现者会踩的）

- **pyright 不收窄 `get_args()` 成员判断**：`x in get_args(Literal别名)` 运行时对、类型错；要收窄只能字面值元组内联（`x in ("a","b")`）。测试侧枚举集合用 `get_args` 保持单源，装配侧手抄元组漏改由测试兜底。
- **MagicMock 的 ctx 自动属性会劫持 `(ctx.rng or random)`**：mock 的 BattleContext 任意属性恒真值，注入回落式判空拿到的不是 None 是 Mock——相关测试须显式 `ctx.rng = None`。
- **模块级 patch 够不到注入流**：Engagement 恒注入后，`monkeypatch.setattr(random, "uniform", ...)` 类的旧式压点对裁判路径失效（这正是红线 3 语义）；要压注入流得 patch `random.Random.uniform`（类级，同时压住注入与回落）。
- **金样张确定性**：P2 前靠测试内模块级 seed（用毕 `random.seed()` 复位防污染同进程其它测试）；P2 后 `EngagementSpec(seed=...)` 注入，重录用 `UPDATE_GOLDEN=1 pytest tests/test_battle_golden.py`。
- **armor=1e9 靶船是确定性长局的好工具**：任何判定伤害恒 0 → 打满回合上限、结局只由初始 HP 决定；但兜底撞击武器 EN 恒 0，"EN 枯竭空回合"实际不存在——空回合只在 EN 消耗钩子抬价时出现（有专门测试构造）。
- **预存地雷（本次未修，按现状交付）**：engage 端点母舰硬编码 `ms_01`（真实数据无此 ID，直调必 500，代码自带 Mock 注释）；`services._build_locked_config` 默认回退 ID `"rx78"`（真实 ID 是 `mech_rx78`，KeyError 被静默吞）；PVE 存量端点（engage/advance/extract/abandon）不查会话属主（新重放端点已带头做了全量校验，存量补齐择批统一）；loot 生成失败发生在残血写回之后（结算原子缺口，与旧实现同序）。

### 验证与闸门

- 全量 630 passed（基线 581 + 新增 49），pyright 0 errors；金样张锁 Doc 14 逐字段结构 + 体积 <512KB；确定性测试（同 seed 双跑全局流扰动下逐字段相等 + 概率技能链覆盖）；PVE 回归（残血写回行为与旧实现一致）+ 模拟器宏观验证（simulate_pve/sim_pres 全流程）。
- 提交序列：e84eed1(P0-a) → 1196112(P0-b) → 8a2a41c(E1) → ad90796(P1-a) → 64f322a(P1-b) → e9ad3a3(P2)。
- 前端切换时点达成：P1 完成 = ebs-duo 2.1 可切换真实数据源（Doc 15 §7 对接里程碑）。

## 2026-09-17 战斗时间轴输出契约文档立项 (Doc 14) 与实施架构定为 Engagement 战报模块

> **项目快照**：前后端战斗界面对接启动 | 新增输出契约 SSOT 文档 | 实施架构定为 Engagement 深模块 | 修订 Doc 0/1/6 交叉引用

### 逻辑变化与核心思路

1. **新增 `docs/14.battle_timeline_contract.md`（战斗时间轴输出契约 v1.0）**
   - **逻辑变化**：定义 `POST /battle/simulate` 对前端的完整输出结构（`meta` / `init` / `rounds` / `result` 四块）、演出事件字段表（演出层/裁定层/状态快照层/高光触发层）、判定枚举映射红线表（AttackResult → 中文口径 → 前端浮字）、以及带优先级的实现差距清单（后经评审升级为 Engagement 架构路线，见第 3 条）。
   - **设计思路**：对齐 `ebs-duo/docs/2.1战斗界面.md` §A5 的演出数据要求。研究结论：引擎内部已算出距离/先手/判定/数值快照，但 `JSONRenderer.render_timeline` 仅输出 7 个字段，且 `context_events`/`summary_events` 全库无生产者、`get_result()` 未被 API 调用——缺口以"字段三态（已输出/未序列化/待新增）+ 差距清单"形式固化，作为前后端对接的单一事实来源。

2. **联动修订既有文档**
   - `docs/6.combat_presentation.md`：版本号 v5.0 → v5.1（对齐代码与前端引用），新增"文档边界"一节声明内部管线与对外契约的分工，指向 Doc 14。
   - `docs/1.battle_design_doc.md`：§7.1 结局表标注"战术脱离"引擎未实现；补对外输出口径说明（`finish`+`winner` 正交表达，禁止将内部 `a_wins/b_wins` 直接作为前端口径）。
   - `docs/0.start.md`：§3.4 数据契约新增对外接口契约条目，声明战斗 API 字段变更须先修订 Doc 14。

3. **实施架构定为 Engagement 战报模块（根本解，替代补丁路线）**
   - **逻辑变化**：Doc 14 §8 由「renderer 补字段 + 两处 handler 装配」重写为「`src/combat/engagement.py`（EngagementSpec → resolve → BattleReport）+ `src/presentation/contracts.py`（契约唯一实现点）」架构。`/battle/simulate` 收缩为调试薄适配器；PVE `battle_bridge.py` 瘦身为输入组装 + `final_states` 写回两步；接敌确认卡走 spec 只读预览。差距清单按新架构重排 P0/P1/P2。
   - **设计思路**：评审纠偏（用户拷问"将就 vs 根本解"）确认原补丁方案会在两个 handler 重复装配契约、并使 BattleBridge 进一步上帝化——恰是 Doc 14 立项要消除的漂移病根。根本解把"一场战斗"升为一等公民：接口窄（两份快照进，一份战报出），引擎/CPS/契约装配全部内聚于深模块；同时解锁可注入 RNG（消除全局随机流的并发污染）与 `initiative_holder` 等悬空字段的明确归属。PVE 会话（锁定/事件/经济/迷雾）为独立内聚轴，保留不动，经 `EngagementSpec`/`final_states` 窄接口握手。另在 §9 新增第 5 条待裁决：PVE 接入后战斗页必须重放已裁定时间轴（2.1 §4.8"重进=新对局"仅适用于调试路由），待探索系统立规格时由前端修订。

4. **契约与实现架构文档分离（Doc 15 立项）**
   - **逻辑变化**：新增 `docs/15.battle_engagement.md`（战斗编排层设计文档），承接原 Doc 14 §8 的目标架构并扩写（模块地图、核心接口与不变量、架构红线、消费方适配器、关键设计决策、实施阶段与契约锚点表、测试策略、内部待裁决）；Doc 14 §8 收敛为"实现状态与锚点说明"，元数据表新增"实现架构"指向 Doc 15，`0.start.md` §3.4 同步补引用。
   - **设计思路**：Doc 14 是对外契约（前后端双方受众，实现后冻结归档），原 §8.1 是后端内部架构（单一受众、随代码演进）——受众与生命周期双错位。拆分后两文档互锚：Doc 15 §7 每个实施阶段标注交付 Doc 14 哪些章节能力，golden 测试三处同步规则（改字段 → 先改 Doc 14 → 改 `contracts.py` → 重录快照）跨两文档生效。

---

## 2026-09-14 美术处理工具链收敛重构 (artgen 收拢为双核心脚本)

> **项目快照**：美术脚本架构收敛 | 移除散落 JSON/处理脚本 | 形成生图与二次处理双核心

### 逻辑变化与核心思路

1. **ComfyUI 模板内嵌化**
   - **逻辑变化**：将原外部工作流描述文件 `landing_t2i.api.json` 作为常量 `DEFAULT_WORKFLOW_TEMPLATE` 完整合入 `scripts/artgen/generate_asset.py`，并移除外部 JSON 文件。
   - **设计思路**：消除生图脚本执行时的外部路径依赖，实现生图脚本的单文件完全自包含（Self-contained），同时保留 `--template` 参数以兼容自定义外部工作流覆盖。

2. **图像二次处理三合一 (`process_asset.py`)**
   - **逻辑变化**：将原有的 `remove_bg.py`（背景透明抠除）、`optimize_asset.py`（调色板量化与WebP深度重编码）和 `preview_bg.py`（UI 遮挡质检标注）三份脚本合并为统一的 `scripts/artgen/process_asset.py`，并删除旧的三份脚本。
   - **设计思路**：统一管理所有本地 CPU 图像二次处理算法，支持一键流水线模式（`--pipeline`：抠图+量化压缩一气呵成），同时支持单功能独立调用（`--remove-bg`、`--optimize`、`--preview`）。
   - **管线调度解耦**：`generate_asset.py` 内部后处理逻辑统一对接 `process_asset` 模块，管线职责清晰分为「AI 远程生图调度」与「本地图像算法二次处理」两层。

---

## 2026-09-13 前端仓库独立化 (ebs-duo) 与原型图完整迁移

> **项目快照**：前后端仓库解耦 | 前端独立工程: https://github.com/nyxira2012/ebs-duo

### 架构演进与核心思路

1. **前后端架构彻底解耦 (Multi-repo 治理)**
   - **逻辑变化**：将原存在于 `ebsp/prototype/` 的全屏 2D 动漫赛璐璐风机甲界面、交互逻辑、Mock 数据层、ComfyUI 素材生成管线产物及视觉规范（`ART_SPEC.md`）整体迁移至独立前端工程 `ebs-duo`（`git@github.com:nyxira2012/ebs-duo.git`）。`ebsp` 内清理未追踪的临时原型目录。
   - **设计思路**：`ebsp` 聚焦于 Python 高性能战斗模拟引擎、圆桌判定、装备/机体数据配置及核心 API 契约；`ebs-duo` 成为专属前端宿主仓库，两端独立发布与演进，避免单仓静态大文件污染与协同冲突。

2. **美术生成工具流适配跨工程输出**
   - **逻辑变化**：更新 `scripts/artgen/generate_asset.py`，检测到同级 `../ebs-duo/assets/` 时自动将 AI 赛璐璐机体与副官立绘生成至前端工程目录，保留后端 Python 美术管线工具链的连续性。

---

## 2026-03-30 PVE 系统测试修复与副本配置重构

> **项目快照**：代码文件 64 个（11442 行）| 设计文档 17 个（5571 行）

### 逻辑变化与核心思路

1. **PVE 系统测试修复与性能优化**
   - **逻辑变化**：修复了 `src/pve/services.py` 中 `PveEntryService` 的类型推断问题，优化了机体快照创建逻辑。将原有的串行 N+1 查询改为并行批量处理（`asyncio.gather`），显著提升了多机体编队的加载性能。
   - **设计思路**：解决 Pyright 类型检查器对 `asyncio.gather(*tasks, return_exceptions=True)` 返回值的类型推断问题。通过添加显式类型注解 `snapshot: MechaSnapshot = snapshot_or_error  # type: ignore[assignment]` 明确告知类型检查器异常已被过滤。同时，错误处理策略从"单个失败全盘回滚"改为"跳过失败个体"，提升了系统的容错性。
   - **测试覆盖**：修复了 `tests/test_pve_core.py` 中 Mock 对象的可迭代性问题，为 `mock_loader` 添加了必要的字典属性（`mechas`、`enemy_templates`），确保测试环境完整模拟生产数据结构。

2. **副本配置系统重构（Doc 13 架构落地）**
   - **逻辑变化**：实现了基于 `InstanceConfig` 的新副本配置体系，替代原有的单一 `RegionConfig` 模式。新增 `src/models.py` 下的副本配置模型族——`InstanceConfig`、`InstanceZoneConfig`、`EnemyTemplateConfig`、`LootTableConfig`、`ScalingConfig` 等，支持更精细化的内容设计。
   - **设计思路**：采用**组件化配置架构**（Component-Based Configuration）。副本（Instance）→ 子区域（Zone）→ 事件序列（Sequence）形成三级嵌套结构，设计师可以独立调整每个子区域的序列长度、固定遭遇位置、掉落倍率等参数，无需触及全局配置。
   - **敌方模板系统**：引入 `EnemyTemplateConfig`，通过"机体 + 驾驶员 + 缩放系数"的拼装模式生成敌人，替代原有硬编码的属性配置。设计师可以复用已有的机体配置，仅调整 `ScalingConfig`（HP/伤害/装甲/机动倍率）快速生成不同难度的敌方单位。

3. **事件生成器增强（支持固定遭遇与暗雷限制）**
   - **逻辑变化**：重构 `src/pve/event_generator.py` 的 `EventSequenceGenerator`，支持 Doc 13 定义的新配置格式。新增 `fixed_encounters`（固定遭遇位置）和 `total_random_encounters`（暗雷总数限制）参数，改变了原有纯随机生成的序列模式。
   - **设计思路**：采用**模板填充算法**（Template Filling Algorithm）。首先根据 `fixed_encounters` 配置在序列指定位置（如第 5 步固定 Boss）放置预设事件，剩余槽位再按权重随机填充。这种设计确保了关键剧情节点的固定性，同时保持了探索过程的重玩价值。
   - **向后兼容**：保留了对旧 `RegionConfig` 格式的支持，通过回退机制（`instance_zone_config or zone_config`）确保现有副本配置无需迁移即可运行。

4. **资源加载器扩展（副本配置热加载）**
   - **逻辑变化**：`src/loader.py` 新增 `get_instance_config()` 和 `get_instance_zone_config()` 方法，支持从 `data/instances.json` 加载副本配置。扩展现有的 `_load_from_json()` 通用加载方法，统一管理所有静态资源（装备、机体、驾驶员、副本等）。
   - **设计思路**：保持**单一数据源原则**（Single Source of Truth）。所有副本配置集中存储在 `instances.json`，加载时通过 Pydantic 进行类型校验，避免配置错误导致的运行时异常。设计师修改 JSON 后重启服务即可生效，无需代码变更。

5. **会话管理器优化（支持多配置格式）**
   - **逻辑变化**：`src/pve/session_manager.py` 的 `create_session()` 方法调整，优先尝试加载 `InstanceZoneConfig`，失败后回退到旧 `RegionConfig`。将配置解析逻辑从"单一来源"改为"优先级回退链"，提升了系统的兼容性。
   - **设计思路**：采用**优雅降级策略**（Graceful Degradation）。新副本使用 Doc 13 格式，旧副本继续使用 `RegionConfig`，两者共存于同一代码库中。这种设计允许设计师逐步迁移现有副本，避免大规模重构带来的风险。

6. **PVE 内容设计调优**
   - **逻辑变化**：`docs/13.pve_content_design.md` 调整了"废弃空间站"副本的参数。将常规区域 `dock` 的序列长度从 10 步缩短至 5 步，固定 Boss 位置从第 10 步提前至第 5 步。隐藏区域 `warehouse` 的掉落倍率从 2.5x 下调至 1.5x。
   - **设计思路**：基于**玩家体验优化**（Player Experience Optimization）。过长的序列容易导致疲劳感，缩短序列并提前 Boss 战可以提升节奏紧凑感。降低隐藏区域的掉落倍率是为了避免"高风险低回报"的负面体验，平衡探索收益与风险的曲线。

7. **静态数据文件补充**
   - **逻辑变化**：新增 `data/instances.json` 和 `data/items.json` 两个静态配置文件。`instances.json` 定义了"废弃空间站"副本的完整配置（区域信息、事件序列、敌方模板、掉落表）。`items.json` 定义了游戏内的道具物品（如"废料碎片"、"静默加密芯片"）。
   - **设计思路**：遵循**配置与代码分离**（Configuration-Code Separation）。将内容设计数据与游戏逻辑代码解耦，设计师可以直接编辑 JSON 文件调整副本参数，无需开发介入。同时，通过 Git 版本管理配置变更，保留完整的历史记录与回滚能力。

**技术要点**
- **并行查询优化**：使用 `asyncio.gather(*tasks, return_exceptions=True)` 批量加载机体快照，将 N 次串行数据库查询优化为 1 次并行批量查询，大幅降低网络延迟叠加
- **类型安全容错**：通过 `# type: ignore[assignment]` 标记告知类型检查器已显式处理异常分支，避免误报
- **配置兼容性回退**：`instance_zone_config or zone_config` 表达式实现新格式优先、旧格式兜底的双模式支持
- **模板填充算法**：固定位置先占位 + 随机槽位后填充的两阶段序列生成，确保关键事件位置可控
- **组件拼装生成敌人**：`mecha_id + pilot_id + scaling` 的三元组替代硬编码属性，提升配置复用率

---

## 2026-03-08 PVE 核心系统实现与测试覆盖扩展

> **项目快照**：代码文件 67 个（11034 行）| 设计文档 14 个（4709 行）

### 逻辑变化与核心思路

1. **PVE 核心系统完整实现（Doc 10 Phase 1-2）**
   - **逻辑变化**：新增 `src/pve/` 模块下 9 个核心文件（约 2500 行），实现了 PVE 探索系统的完整服务层。包含 `battle_bridge.py`（战斗桥接层）、`exploration.py`（探索逻辑）、`session_manager.py`（会话管理）、`reward_controller.py`（收益控制器）、`models.py`（数据模型）、`schemas.py`（API Schema）、`enums.py`（枚举定义）、`repository.py`（仓库层）和 `services.py`（服务层扩展）。
   - **设计思路**：采用**分层架构**（Layered Architecture）——桥接层负责连接战斗引擎与 PVE 系统，会话管理器负责状态持久化与恢复，收益控制器负责战利品的临时存储与最终入库。这种分层确保了各模块职责单一，便于单元测试与未来扩展。
   - **战斗桥接层**：`BattleBridge` 类负责将 PVE 实体状态转换为战斗引擎所需的 `Mecha` 对象，战斗结束后再将结果转换回 PVE 状态。支持基于现实时间的 HP/EN 恢复补偿机制。
   - **收益幂等性**：`RewardController.finalize()` 实现双层幂等校验——应用层软校验 + 数据库唯一索引硬拦截，彻底杜绝”双倍奖励”漏洞。

2. **PVE 完整测试覆盖（7 个测试文件）**
   - **逻辑变化**：新增 `tests/test_pve_*.py` 系列 7 个测试文件，覆盖核心模块、地图生成器、仓库层、收益控制器、服务层和会话管理器。
   - **设计思路**：测试文件与源码模块一一对应，确保每个关键逻辑都有独立验证。使用 pytest 的 mock 机制拦截随机数和数据库调用，保证测试结果的确定性与执行速度。

3. **战斗引擎增强（`get_result()` 方法）**
   - **逻辑变化**：`src/combat/engine.py` 新增 `get_result()` 方法，返回结构化的战斗结果（胜负、回合数、双方 HP/EN 状态）。
   - **设计思路**：PVE 系统需要战斗引擎提供标准化的结算接口，而非依赖内部状态。新增方法封装了胜负判定逻辑（存活优先、HP 次之、平局兜底），为外部系统提供清晰的数据契约。

4. **数据库模型扩展（PVE 幂等性支持）**
   - **逻辑变化**：`src/database/models.py` 扩展 `PveSession` 表，新增 `current_layer`、`session_data`（完整状态 JSON Blob）、`idempotency_key` 和 `expires_at`（断线保护 TTL）字段。新增 `PveRewardLedger` 表用于记录收益发放流水，通过 `session_id` 唯一约束实现硬幂等防线。
   - **设计思路**：`session_data` 字段存储完整的会话状态（地图图、实体状态、待领取奖励），支持断线重连时 100% 还原。`expires_at` 字段配合定时清理任务，自动回收超时的会话数据，防止 DB 膨胀。

5. **PVE 系统文档扩展（战争迷雾与数据裁剪）**
   - **逻辑变化**：`docs/10.pve_system.md` 新增 §8 章节，详细定义了战争迷雾机制与前端数据裁剪策略。
   - **设计思路**：采用**视图模型分离**（View Model Separation）原则——服务端保持完整地图数据（Domain Model），下发给客户端时通过 `PveSessionFogView` 过滤敏感信息。这防止了玩家通过抓包实现”开图透视”。

6. **用户系统文档更新（幂等性双轨制防御）**
   - **逻辑变化**：`docs/7.user_system_implementation.md` 将幂等性章节重构为”双轨制防御体系”，分离 API 级通用幂等与业务级流水幂等两种模式。
   - **设计思路**：API 级幂等使用通用 `idempotency_keys` 表 + 装饰器，适用于所有接口防连点。业务级幂等使用流水表唯一索引，适用于 P0 级资产变动（PVE 收益提现、商店购买、抽卡）。两者组合形成”软拦截 + 硬防线”的双重保护。

7. **工厂架构重构（消除 13 元组债务）**
   - **逻辑变化**：`src/factory.py` 的 `_apply_equipment_modifiers` 方法重构，移除 13 元组返回值和百行 if-elif 硬编码。采用字典累加容器（`stats_dict`）和别名路由表（`ALIAS_MAP`）统一处理基础数值修正与随机词条计算。
   - **设计思路**：贯彻”最小有效改动”原则——对外保持完全兼容，内部实现彻底解耦。返回值简化为 `(Dict, List[WeaponSnapshot])`，新增属性只需在 `stats` 字典中添加键值对，无需修改函数签名。

8. **装备生成测试大幅扩展（479 个用例）**
   - **逻辑变化**：`tests/core/test_item_generator.py` 从 29 行扩展到 463 行，新增覆盖 ilvl 浮动、词条档位权重、技能槽概率、词条不重复、颜色分计算等核心逻辑。
   - **设计思路**：使用 `pytest.mark.parametrize` 进行数据驱动测试，单个测试函数验证数十种组合。mock `random.uniform` 和 `random.randint` 确保测试结果可预测。

**技术要点**
- **双层幂等防线**：应用层查询 `PveRewardLedger` + DB 唯一索引抛 `IntegrityError`，确保极高并发下也不会重复发奖
- **状态无损流转**：`session_data` JSON Blob 存储完整会话状态，支持任意后端节点接管会话（水平扩展友好）
- **视图数据裁剪**：前端只获得”已探索区域 + 已触发事件”，暗雷位置和未探索节点信息完全隐藏
- **别名路由表**：`ALIAS_MAP` 处理早期设计遗留的同义词（`init_hp` → `final_max_hp`），保证向后兼容

**后续计划**
1. 实现 `src/pve/map_generator/` 地图生成器（Phase 3）：采用预设地块库拼接策略，避免原子随机游走的死锁风险
2. 实现 PVE API 端点（`src/api/pve_api.py`）：提供进入/退出/移动/结算等 REST 接口
3. 补充集成测试：验证从”进入地图”到”收益入库”的完整流程

---

## 2026-03-08 母舰、PVE 与库存系统：核心玩法闭环

> **项目快照**：代码文件 60 个（8970 行）| 设计文档 12 个（4653 行）

### 逻辑变化与核心思路

1. **母舰系统完整实现（Doc 11）**
   - **逻辑变化**：新增 `src/pve/services.py` 实现母舰集成服务层，定义 `MothershipConfig` 和 `RegionConfig` 数据模型。母舰作为玩家的”移动基地”，提供货舱容量（`cargo_capacity`）、区域准入（`region_level`）和商店刷新上限（`shop_ilvl_limit`）三大核心能力。
   - **设计思路**：母舰系统采用**能力提供者模式**（Provider Pattern）——`IMothershipProvider` 接口定义 `get_max_capacity()` 抽象方法，`DatabaseMothershipProvider` 从数据库和静态配置中查询玩家拥有的母舰，返回其中 `cargo_capacity` 的最大值。这种设计允许在母舰系统未完成时使用 `MockMothershipProvider` 进行测试，实现了”延迟依赖”的架构原则。
   - **区域准入逻辑**：`validate_region_entry()` 方法判断母舰是否具备进入指定区域的能力（`mothership.region_level >= region.min_region_level`）。这为未来的”区域探索限制”和”内容解锁节奏”预留了接口。
   - **PVE 锁定机制**：`is_pve_session_active()` 方法检查玩家是否处于活跃的 PVE 探索节点中，按 Doc 11 设定，处于活跃状态则阻断购舰与切换舰队，防止”战斗中作弊”。

2. **PVE 系统设计文档（Doc 10）**
   - **逻辑变化**：新增 `docs/10.pve_system.md`（691 行），定义了 PVE 探索系统的完整设计。
   - **设计思路**：采用**节点制探索**（Node-based Exploration）——玩家选择母舰出征，在不同区域节点间移动，遭遇敌人、资源点或事件。每个节点有独立的回合限制（`turn_limit`）和回合消耗（`turn_cost`），玩家需要在资源耗尽前完成探索或撤离。
   - **核心机制**：
     - **母舰出征**：玩家选择母舰和编队，消耗 `turn_cost` 进入节点，战斗继承上次状态（HP/EN 不回满）
     - **战利品结算**：击败敌人获得装备和材料，若货舱溢出则触发超载处理流程（玩家必须丢弃部分物品）
     - **区域解锁**：母舰的 `region_level` 决定可进入的区域等级，区域等级越高，敌人和奖励越强

3. **库存系统完整实现（Doc 12）**
   - **逻辑变化**：新增 `src/user/inventory.py` 实现背包服务层，`src/api/inventory_api.py` 实现 REST API 端点。数据库新增 `UserEquipment` 和 `UserItem` 两张表，分别存储不可堆叠装备（每件 1 格）和可堆叠材料（每类 1 格）。
   - **设计思路**：采用**分类堆叠规则**（Category-based Stacking）——装备独立存储（因为具有独立的随机词条和强化等级），材料按 `item_id` 唯一约束合并数量。容量计算逻辑：`占用格子 = 离舱装备数 + 材料种类数`。
   - **超载处理流程**：`finalize_overload()` 端点实现三步验证——（1）显式验证丢弃列表的合法性（数量匹配、权属校验）（2）执行物理删除（3）尝试添加新资产，若依然溢出则报错拦截。这防止了客户端作弊直接跳过清理流程。
   - **容量管控**：`can_add()` 方法在添加资产前预计算所需格子数（`calculate_required_slots()`），若超过剩余空间则返回 `AddResult.OVERFLOW`。这种”预检查”机制避免了”部分添加后失败”的数据一致性问题。

4. **数据库模型扩展**
   - **逻辑变化**：`src/database/models.py` 新增 `UserMothership`、`UserEquipment`、`UserItem`、`UserPilot`、`UserSquad` 五张表，实现玩家资产的完整持久化。
   - **设计思路**：采用**混合关系型架构**（Hybrid Relational Architecture）——核心资产（机体、装备、材料）使用独立表存储，支持复杂的查询和索引；游戏快照（战斗状态、编队配置）使用 JSON 字段存储，保持灵活性。例如 `UserEquipment.random_stats` 存储 `{“attack”: 15, “crit_rate”: 5}`，具体数值由运行时配置+公式还原。
   - **级联删除与关系映射**：使用 `ForeignKey(“users.id”, ondelete=”CASCADE”)` 确保用户删除时所有关联资产自动清理，避免孤儿数据。`relationship()` 配置 `lazy=”selectin”` 预加载关联数据，避免 N+1 查询问题。

5. **API 层扩展与用户系统集成**
   - **逻辑变化**：`src/api/user_api.py` 新增 `/api/mothership` 路由组，实现母舰购买、列表查询、当前出战切换等端点。`src/api/inventory_api.py` 新增 `/api/inventory` 路由组，实现状态查询、物品列表、超载处理等端点。
   - **设计思路**：保持 API 的**模块化与职责单一**——每个路由组对应一个业务领域（用户、母舰、库存），通过 `app.include_router()` 挂载到主应用。端点采用 RESTful 风格设计，如 `GET /api/mothership` 获取拥有的母舰列表，`POST /api/mothership/purchase` 购买新母舰。

6. **Google Style 文档规范补充**
   - **逻辑变化**：根据技术审计报告，为 `inventory.py`、`inventory_api.py`、`models.py` 中的所有类和方法补充了完整的 Google Style 文档字符串。包含模块级业务背景说明、类 Attributes 列表、方法 Args/Returns/Raises 说明、使用示例等。
   - **设计思路**：文档是代码的”第二接口”，特别是库存系统这种涉及复杂业务规则（容量计算、堆叠规则、超载处理）的模块，清晰的文档能大幅降低维护成本。例如 `get_occupancy()` 方法的文档明确说明了”已装备装备不计入容量”这一关键规则。

7. **类型检查修复**
   - **逻辑变化**：修复 `src/pve/services.py` 缺少 `AsyncSession` 导入、`src/user/service.py` 类型注解 `any` → `Any` 的类型错误。
   - **设计思路**：保持类型系统的完整性是大型 Python 项目的基础，pyright 的严格检查能提前发现大量潜在 bug（如方法拼写错误、参数类型不匹配）。所有新增代码必须通过 pyright 检查才能提交。

8. **双重工厂架构债务定点清除（消除 13 元组与硬编码）**
   - **逻辑变化**：重构 `src/factory.py` 的 `_apply_equipment_modifiers` 方法，移除了长达 13 个返回值的元组定义与成百行的 `if-elif` 硬编码链。采用字典累加容器（`stats_dict`）和内部别名路由表（`ALIAS_MAP`）统一处理基础数值修正与随机词条计算，返回值简化为 `(Dict, List[WeaponSnapshot])`。
   - **设计思路**：坚决贯彻”最小有效改动（微创手术）原则”。保留了对外界系统的完美兼容无感适配能力，不干扰业务层的逻辑边界划分，却一举消除了最深层次属性增订的连环改动负担。经过 479 个测试用例的绝对覆盖验证，该核心算子的解耦实现了彻底的未来可拓展性。

**技术要点**
- **唯一约束与堆叠**：`UserItem` 表的 `UniqueConstraint(“user_id”, “item_id”)` 确保同类材料自动合并，应用层只需 `quantity += new_quantity`
- **容量预计算**：`calculate_required_slots()` 方法通过 `new_item_ids - existing_item_ids` 差集运算，高效统计新增材料种类数
- **安全验证三步法**：超载处理端点先验证丢弃列表数量（`existing_count != len(unique_discard_ids)` 报错），再执行删除，最后添加新资产，确保原子性
- **Google Style 文档结构**：模块文档（业务背景）→ 类文档（用途说明）→ 方法文档（Args/Returns/Raises/Example），层次清晰

**后续计划**
1. 实现断线保护机制（P2 优先级）：超载处理时将待确认物品存入 `pending_rewards` 临时表，设置超时清理，防止玩家断线后战利品丢失
2. 补充 API 层集成测试（P3 优先级）：目前 API 测试覆盖率仅 37-67%，需要覆盖更多业务场景（如超载处理、母舰购买）
3. 实现邮件系统作为超载处理的回退方案：若玩家长时间未处理超载，将物品通过邮件系统发送，确保资产不丢失

---

## 2026-03-05 用户系统：数据库集成、身份认证与存档同步

> **项目快照**：代码文件 45 个（7911 行）| 设计文档 9 个（2516 行）

### 逻辑变化与核心思路

1. **用户数据库基础设施的完整构建**
   - **逻辑变化**：新增 `src/database/` 模块，实现了基于 SQLAlchemy 的异步数据层。包含 `base.py`（引擎与会话管理）、`models.py`（User 与 GameSave ORM 映射）、`session.py`（FastAPI 依赖注入）。采用 `aiosqlite` 作为 SQLite 异步驱动，确保 FastAPI 事件循环不被阻塞。
   - **设计思路**：贯彻"代码级完美适配"（Agnostic Code）原则——所有数据库逻辑使用 SQLAlchemy 抽象层编写，确保后期迁移到 PostgreSQL 时无需修改一行业务代码。例如使用 `sqlalchemy.JSON` 存储战斗快照，这种通用类型在 SQLite 和 PostgreSQL 中均原生支持。
   - **测试隔离性**：在测试配置中使用 `StaticPool` 强制所有会话共享同一个内存数据库实例，解决了异步 SQLite 测试中"不同 Session 连接到不同内存库"的经典陷阱。

2. **身份认证系统的 JWT 化**
   - **逻辑变化**：在 `src/user/security.py` 中实现了基于 bcrypt 的密码哈希（生产环境 12 轮，测试环境 4 轮加速）和基于 `python-jose` 的 JWT 签发/验证。采用 `HS256` 算法 + `SECRET_KEY` 签名，Token 有效期 30 分钟。在 `src/user/auth.py` 中实现了 `get_current_user` 依赖注入函数，用于保护需要登录的 API 端点。
   - **设计思路**：选择 JWT 而非 Session Cookie，主要考虑前后端分离架构（Next.js + FastAPI）的跨域限制。Session Cookie 依赖浏览器的同源策略，在开发环境（localhost:3000 → localhost:8000）和生产环境（不同域名）都会遇到 CORS 问题。JWT 通过 `Authorization: Bearer <token>` 头部传递，彻底规避 Cookie 跨域陷阱。
   - **可选用户模式**：在 `src/user/dependencies.py` 中实现了 `get_optional_user`，允许 API 端点"既支持匿名用户，也支持登录用户"。这为 `/battle/simulate` 端点提供了灵活性——未登录玩家使用默认机体配置，登录玩家可加载自己的存档覆盖。

3. **Repository 模式与业务模型的无缝集成**
   - **逻辑变化**：在 `src/user/repository.py` 中实现了 `GameSaveRepository` 类，封装了所有存档的 CRUD 操作。关键方法包括：
     - `save_mecha_snapshot()`：将 `MechaSnapshot` 通过 `model_dump(mode='json')` 序列化为 JSON 存储
     - `to_mecha_snapshot()`：通过 `MechaSnapshot.model_validate(data)` 反序列化为业务对象
     - `get_deployed()`：获取用户的"当前出战"存档
   - **设计思路**：充分复用 `src/models.py` 中已有的 Pydantic 模型作为 DTO（数据传输对象），数据库仅作为"透明存储层"。存档表中的 `save_data` 字段不仅存储机体数据，还包含版本号和元数据（`{"version": "1.0", "mecha": {...}, "metadata": {...}}`），为未来的模型迁移预留空间。

4. **用户 API 的模块化挂载**
   - **逻辑变化**：新增 `src/api/user_api.py`，实现了 `/api/register`、`/api/login`、`/api/saves`（CRUD）、`/api/deploy`（设置出战存档）等端点。通过 `app.include_router(user_api.router, prefix="/api")` 挂载到主应用，实现了路由的模块化管理。
   - **设计思路**：保持 `presentation_api.py` 的简洁性，用户相关逻辑完全隔离在独立模块中。API 端点采用 RESTful 风格设计，如 `GET /api/saves` 获取存档列表、`POST /api/saves` 创建存档、`DELETE /api/saves/{slot_id}` 删除存档。

5. **战斗 API 的用户集成**
   - **逻辑变化**：在 `src/api/presentation_api.py` 的 `/battle/simulate` 端点中集成了用户存档加载逻辑。新增 `use_user_save_for_a` 和 `use_user_save_for_b` 参数，允许玩家选择使用自己的存档覆盖默认机体配置。
   - **设计思路**：实现"战斗即服务"（Battle as a Service）——玩家可以在单机模式下调整机体配置，保存为出战存档，然后在 PvP 或 Boss 挑战中调用该配置。这为未来的"机体配置分享"和"排行榜"功能预留了接口。

6. **测试基础设施的性能优化**
   - **逻辑变化**：在 `tests/conftest.py` 中新增 `reduce_bcrypt_cost` fixture，将测试环境下的 bcrypt 工作因子从 12 降到 4，速度提升约 256 倍（300ms → 1ms）。新增 `test_app` 和 `async_client` fixture，实现了 FastAPI 测试客户端的会话级复用，避免了每次测试都重新 `init_db` 和 `load_all`。
   - **设计思路**：测试的执行速度直接影响开发效率。bcrypt 是密码哈希的必要开销，但在测试中这种"真·安全"毫无意义。通过动态调整工作因子，在保证测试逻辑不变的前提下，大幅缩短测试时间。同时，通过清空 FastAPI 的 `on_startup` 和 `on_shutdown` 事件，避免 AsyncClient 每次进入上下文都重新初始化数据库和数据加载器。

7. **虚拟环境的规范化配置**
   - **逻辑变化**：更新 `.claude/settings.local.json`，将虚拟环境路径（`.venv/bin/*`）加入权限白名单。更新 `pyrightconfig.json`，配置 `venvPath` 和 `venv` 字段，确保 Pyright 能正确识别虚拟环境中的类型存根。
   - **设计思路**：从"全局 Python"迁移到"虚拟环境"是 Python 项目的标准实践。通过配置工具链的权限和路径，确保所有命令（`pyright`、`pytest`、`python`）都在虚拟环境中执行，避免"系统 Python vs 项目 Python"的版本混淆。

8. **依赖清单化与环境模板**
   - **逻辑变化**：新增 `requirements.txt`，列举了所有生产依赖（`fastapi`、`uvicorn`、`sqlalchemy`、`aiosqlite`、`pydantic`、`passlib`、`python-jose`、`pytest` 等）。新增 `.env.example`，提供了环境变量模板（`SECRET_KEY`、`DATABASE_URL`、`ACCESS_TOKEN_EXPIRE_MINUTES`）。
   - **设计思路**：依赖清单是项目"可复制性"的基础——新开发者只需 `pip install -r requirements.txt` 即可获得完全一致的开发环境。环境变量模板则明确了"哪些配置需要保密或可变"（如 `SECRET_KEY`），避免将敏感信息提交到代码库。

**技术要点**
- **StaticPool 的必要性**：异步 SQLite 内存数据库的每个连接都是独立的内存实例，必须使用 `poolclass=StaticPool` 强制所有连接共享同一个内存库，否则测试 A 写入的数据，测试 B 无法读取
- **bcrypt 工作因子的安全/性能权衡**：12 轮（约 300ms）适合生产环境防止暴力破解，4 轮（约 1ms）适合测试环境加速执行，通过 `@pytest.fixture(autouse=True)` 在测试开始时自动切换
- **JWT 的 Token 过期策略**：`ACCESS_TOKEN_EXPIRE_MINUTES=30` 平衡了安全性和用户体验——太短（如 5 分钟）需要频繁登录，太长（如 7 天）增加 Token 泄露的风险
- **FastAPI 依赖注入的链式传递**：`Depends(get_async_session)` → `Depends(get_current_user)` → `Depends(get_optional_user)`，每一层都依赖下一层的返回值，形成了清晰的依赖链
- **Pydantic 的 `mode='json'` 序列化**：`model_dump(mode='json')` 会将所有复杂类型（如 datetime、Enum）转换为 JSON 兼容的字符串，确保存入数据库后能正确还原

**后续计划**
1. 实现存档的"版本迁移"逻辑，当 `save_data['version']` 不匹配当前版本时，自动执行数据升级（如 v1.0 → v1.1 添加新字段）
2. 扩展 `Users` 表，支持 `status`（active/banned）、`deleted_at`（软删除）等字段，为用户管理后台预留接口
3. 实现存档的"导出/导入"功能，允许玩家分享自己的机体配置（通过 JSON 文件或 Base64 编码）
4. 编写用户系统的性能测试，验证 1000 个并发用户同时请求 `/battle/simulate` 时的响应时间（目标：<100ms p95）

---

## 2026-03-07 物品与养成系统设计文档

> **项目快照**：代码文件 45 个（7911 行）| 设计文档 11 个（3296 行）

### 逻辑变化与核心思路

1. **物品系统设计文档（Doc 8）**
   - **逻辑变化**：新增 `docs/8.item_design.md`（218 行），定义了装备与物品系统的完整设计。
   - **设计思路**：采用**双轴独立评定**体系——装等（ilvl）控制数值深度，稀有度（颜色）评定潜力宽度。ilvl=1 的新手装备 roll 出满词条+技能照样是橙色传说，避免了"低等级装备无价值"的问题。
   - **核心机制**：
     - **词条分档制（Tiered Affixes）**：每件装备 3 个属性槽 + 1 个技能槽，独立 roll 出 T0~T4 五个档位。T4 顶级词条仅 1% 概率，技能槽 0.5% 概率
     - **颜色判定**：`颜色分 = 已 roll 属性数 + (有技能 ? +2 : 0)`，技能直接跳两级颜色体现其珍贵
     - **数据库存储**：`UserEquipment.random_stats` JSONB 仅存储 ilvl、词条 ID 和档位，具体数值运行时由配置+公式还原，极度紧凑

2. **养成系统设计文档（Doc 9）**
   - **逻辑变化**：新增 `docs/9.growth_system.md`（738 行），定义了五大养成轴的完整成长曲线。
   - **设计思路**：追求**极其漫长但节奏顺滑**的游戏期。总战力 = f(机体) + f(装备) + f(机师) + f(副驾驶) + f(母舰) + f(熟练度)，每条轴遵循收益递减、消耗递增的对数级增长规律。
   - **五大养成轴**：
     - **机体改造**：6 项底盘属性独立改造至 20 级，改造费用指数增长（1.35^n），触顶后研发新机体
     - **装备强化**：+0~+100，分段递减成功率（+96~+100 仅 10%），失败回退，满级装备可合成/洗练
     - **机师成长**：等级（多项式经验曲线）+ 击坠数（解锁 Ace Bonus）+ 觉醒突破
     - **副驾驶**：碎片招募 + 强化至 Lv5 + 立绘更换
     - **母舰**：货舱/修复/能量/航行/通讯五大模块纯信用点升级

3. **测试代码大规模重构**
   - **逻辑变化**：删除 7 个冗余测试文件，扩展现有测试文件覆盖 `factory.py`、`skill_callbacks.py` 等模块的更多分支。净减少约 732 行测试代码。
   - **设计思路**：
     - **删除冗余**：`test_complex_scenarios.py`、`test_event_manager_isolation.py`、`test_presentation_showcase.py`、`test_resolver_coverage.py`、`test_skill_event_system.py`、`test_trait_system_pytest.py`、`test_weapon_tags_debug.py` 的功能已被其他测试覆盖
     - **增强覆盖**：`test_factory.py` 新增 160 行测试，覆盖 `upgrade_bonuses` 字典路径、装备防御属性分支、`fixed_weapons` 加载等之前未覆盖的代码路径
     - **技能回调测试**：`test_skill_callbacks.py` 新增 8 个测试类，覆盖 `cb_auto_repair`、`cb_ablat`、`cb_vampirism`、`cb_rage_will`、`cb_regen_hp`、`_restore_en` 等回调函数

4. **配置文件更新与数据库清理**
   - **逻辑变化**：更新 `.gitignore` 完善数据库文件忽略规则（`*.db`、`*.db-journal`、`*.db-wal`、`*.db-shm`、`db/`），删除本地 `db/ebsp.db` 文件。
   - **设计思路**：本地数据库文件不应提交到版本控制，通过 `.gitignore` 确保所有 SQLite 相关文件都被忽略。更新 devlog skill 添加 git 提交确认流程，确保日志更新后必须确认提交。

**技术要点**
- 词条分档概率：T0（空槽）39%、T1（低档）35%、T2（中档）18%、T3（高档）7%、T4（顶级）1%
- 改造费用公式：`段位 n 的费用 = base_cost × (1.35 ^ n)`，段位 20 费用是段位 1 的 404 倍
- 经验曲线公式：`exp_to_next_level(level) = int(100 × (level ^ 1.8))`，Lv 50→51 需要 110,000 EXP
- 装备强化成功率：+0→+30 为 100%，+96→+100 为 10%（失败降 3 级）
- 日均信用点净收入 ~50,000 Cr（假设 500 场/天，每场 3-5 秒），母舰满级需 ~310 天纯投入

**后续计划**
1. 实现 `src/database/models.py` 中 `UserSubPilot` 和 `UserMothership` 表定义
2. 扩展 `SnapshotFactory.create_combat_snapshot()` 聚合管线，集成机体改造、装备强化、副驾驶等养成数据
3. 实现 `data/affixes.json`、`data/sub_pilots.json`、`data/upgrade_costs.json` 等配置文件
4. 编写养成系统的模拟器（`sim/sim_progression.py`），验证从新手期到终局的时间线（预期 12-18 个月）

---

## 2026-03-03 演出系统降级匹配锁链与架构精简：从精确匹配到兜底保障

> **项目快照**：代码文件 33 个（5799 行）| 设计文档 7 个（2300 行）

### 逻辑变化与核心思路

1. **降级匹配锁链机制（T2.5_Decay 层）的引入**
   - **逻辑变化**：在 `constants.py` 中新增 `MacroMotion` 枚举和 `MOTION_STYLE_TO_MACRO` 映射表，将 13 种 `MotionStyle` 映射为 4 大类宏观动作：`RANGED_DIRECT`（定向直射）、`MELEE_CLASH`（近战格斗）、`RANGED_AOE`（大范围覆盖）、`OMNI_DIRECTIONAL`（全方位空间）。在 `bidder.py` 的 `_bid_reaction()` 方法中实现三级匹配锁链：T2_Perfect（精确匹配 MotionStyle + DamageMaterial）→ T2.5_Decay（仅匹配 MacroMotion）→ T3_Fallback（硬编码兜底）。
   - **设计思路**：旧的 T2 层要求"动作风格 + 伤害材质"完全匹配，导致大量边缘情况无法匹配到模板（如"光束重斩"找不到"SLASH_HEAVY + ENERGY"模板时就直接跳到 T3）。新架构引入 T2.5_Decay 层作为"软着陆区"——即使材质不匹配，只要宏观动作分类一致，也能找到可用的通用模板。这大幅提升了模板覆盖率和演出多样性，同时避免了硬编码兜底的过度触发。

2. **T3 硬编码兜底的全面实施**
   - **逻辑变化**：在 `bidder.py` 的 `_bid_action()` 和 `_bid_reaction()` 方法中，将 T3 层从"模板加载"改为"硬编码生成"。当 T2 和 T2.5 层都无法匹配时，系统会根据 `attack_result`、`channel` 等信息动态生成兜底文本，而非返回空文本或抛出异常。
   - **设计思路**：T3 的核心价值是"永不空文本"。之前的 T3 模板虽然存在，但覆盖不全，导致某些边缘情况下返回 None。新架构通过硬编码兜底，确保无论输入是什么，系统都能生成合理的演出文本。例如，即使是一个从未配置过的武器组合，系统也能生成"{attacker}使用{weapon}展开了攻击！"这样的基础描述，保证玩家不会看到"空文本"这种破坏沉浸感的情况。

3. **模板配置的精简与标准化**
   - **逻辑变化**：在 `config/presentation_templates.yaml` 中进行了大规模精简和标准化。移除了冗余的描述性注释（如"# --- 光束类 (Beam/Energy) ---" 改为 "# --- 光束类 (ENERGY) ---"），统一使用 `DamageMaterial` 枚举值（ENERGY/KINETIC/PHYSICAL/GENERIC）。优化了 `bone_id` 命名（如 `act_beam_rifle_aim` → `act_beam_rifle`），移除了过于具体的状态词（如 `_aim`、`_charge`），使骨架更通用、更可复用。
   - **设计思路**：配置文件应该"清晰到一眼能看懂"。旧配置中，`beam_rifle_aim` 暗示"瞄准状态"，但实际上这个骨架也用于"立即射击"场景，命名与实际使用不符。新配置使用更抽象的命名（`beam_rifle`），通过 `motion_style` 和 `damage_material` 区分具体场景，实现了"一个骨架，多种用途"。同时，注释从"分类描述"改为"枚举值标注"，与代码保持一致，减少了认知负担。

4. **双轨竞标机制的精细化调整**
   - **逻辑变化**：在 `bidder.py` 中优化了 `_weighted_select()` 方法的权重计算逻辑。对于 `ReactionBone`，当 `motion_style` 完全匹配时，权重 ×2.5；当 `motion_style` 不匹配且不是 ANY 时，权重 ×0.2。这实现了"精确匹配高优先，模糊匹配低优先，但绝不拒绝"的软约束机制。
   - **设计思路**：权重调整的核心是"鼓励精确匹配，但不强制"。旧系统中，不匹配的骨架会被直接过滤掉，导致"物理类兼容度次优"的骨架根本没有机会被选中。新系统通过权重倍率实现了"软约束"——精确匹配有 2.5 倍优势，但不匹配的骨架仍然有机会（只是概率低）。这增加了演出多样性，避免了"同一演出连续刷屏"的问题。

5. **YAML 配置文件的架构声明更新**
   - **逻辑变化**：在 `config/presentation_templates.yaml` 的头部注释中，将架构描述从"L3: Assembler → final_text (原子拼装 + SVI + DHL)"简化为"L3: Assembler → final_text (原子拼装)"。新增了"降级匹配锁链（文档6机制3）"的机制说明，明确了 T2_Perfect、T2.5_Decay、T3_Fallback 三层的职责。
   - **设计思路**：配置文件应该"自解释"。任何打开这个文件的人，应该在 10 秒内理解"这个文件做什么"、"怎么匹配模板"、"有哪些层级"。旧的注释过于详细（"SVI + DHL"这些实现细节不应该出现在配置文件中），新注释聚焦于"匹配机制"，更符合"配置即文档"的理念。

**技术要点**
- `MacroMotion` 枚举定义了 4 大类宏观动作，每个 `MotionStyle` 都映射到一个 `MacroMotion`（如 `SLASH_LIGHT` → `MELEE_CLASH`），用于 T2.5_Decay 层的模糊匹配
- `MOTION_STYLE_TO_MACRO` 映射表使用字典实现 O(1) 查找，避免在竞标时进行复杂的条件判断
- 硬编码兜底的文本使用字典结构存储（`result_texts = {"HIT": [...], "CRIT": [...]}`），确保扩展性——未来只需添加新的 `attack_result` 条目即可支持新判定类型
- T2.5_Decay 层的匹配条件是 `macro_motion == 匹配值 and damage_material == "GENERIC"`，这意味着通用模板（材质为 GENERIC）是 Decay 层的主力军
- `_weighted_select()` 方法的权重倍率（2.5 / 0.2）是经验值，基于"精确匹配应该有显著优势但不垄断"的原则调整

**后续计划**
1. 扩展 T2.5_Decay 层的通用模板库，为 4 大类 `MacroMotion` 各自提供丰富的 GENERIC 模板，提升 Decay 层的多样性
2. 统计 T3 硬编码兜底的触发频率，如果触发率过高（>10%），说明 T2/T2.5 层的模板覆盖不足，需要补充
3. 考虑将 `MacroMotion` 扩展为 5 或 6 大类，以更好地覆盖边缘武器类型（如声波武器、磁轨炮等）
4. 实现模板匹配的可视化工具，显示"每次攻击使用了哪个层级的模板"，用于验证降级匹配锁链的有效性

---

## 2026-02-27 演出系统架构彻底重构：从分层优先级到流水线解耦

> **项目快照**：代码文件 35 个（5992 行）| 设计文档 9 个（3559 行）

### 逻辑变化与核心思路

1. **五层流水线架构（L1-L4）取代 T-Hierarchy 分层系统**
   - **逻辑变化**：删除了旧有的 T0-T3 四层优先级系统（`selector.py` 127 行被删除），重构为严格的五层流水线：
     - **L0 适配层**（`event_builder.py`）：新增 `AttackEventBuilder` 作为战斗引擎与演出系统的适配层，将引擎的计算结果打包为 `RawAttackEvent`，彻底解耦引擎与表现层的数据契约
     - **L1 路由层**（`router.py`）：新增 `OutcomeRouter` 实现"结局前置路由"（Outcome-First Routing），根据战斗结局在第一毫秒就锁定演出频道（FATAL/EVADE/IMPACT/SPECIAL），杜绝逻辑穿帮
     - **L2 竞标层**（`bidder.py`）：新增 `DualBidder` 实现动反双轨独立竞标，Action 竞标匹配意图，Reaction 竞标匹配频道+物理类兼容
     - **L3 组装层**（`assembler.py`）：新增 `TextAssembler` 实现三段式拼装+DHL（动态受击部位映射）+SVI（语义化变量注入）
     - **L4 调度层**（`av_dispatcher.py`）：新增 `AVDispatcher` 实现影视级调色，规则树驱动的摄像机选择，语义化时间轴自适应
   - **设计思路**：旧系统的 T0-T3 是"大一统模板"，每个模板同时包含 Action 和 Phase 两段文本，导致组合爆炸（10 种攻击 × 10 种受击 = 100 种模板）。新架构采用"原子化骨架"（ActionBone + ReactionBone），攻守分离，10 + 10 = 20 个骨架即可组合出 100 种演出。同时，通过 L1 的结局前置路由，确保"致死打击"永远不会被误判为普通命中。

2. **演出模板的原子化重构（ActionBone + ReactionBone）**
   - **逻辑变化**：在 `template.py` 中新增 `ActionBone` 和 `ReactionBone` 数据类，取代旧的 `PresentationTemplate` 大一统结构。`ActionBone` 只描述攻击方的动作（意图、物理类、文本碎片），`ReactionBone` 只描述防御方的反应（频道、物理类、文本碎片）。两者通过 `physics_class`（Energy/Kinetic/Blade/Impact）做软约束——同类物理组合优先，异类组合降权。
   - **设计思路**：原子化是应对组合爆炸的唯一解。旧系统中，"光束军刀斩击命中"和"光束军刀斩击暴击"需要两个独立模板。新系统中，只需一个 `ActionBone`（光束军刀斩击）+ 两个 `ReactionBone`（命中反应、暴击反应）即可组合。这使模板库从 600+ 行缩减到 300+ 行，但覆盖的演出组合反而增加了 3 倍。

3. **动态受击部位映射（DHL）与损伤量级分级**
   - **逻辑变化**：在 `assembler.py` 中新增 `DhlMapper` 和 `DamageGrader`。DHL 根据攻击结果动态选择受击部位——FATAL 锁定关键节点（驾驶舱、动力炉），CRIT 锁定精密部位（摄像机、推进器），HIT 锁定外甲。DamageGrader 根据 `damage/defender_max_hp` 比例分级（<10% 骚扰级、10-30% 有效级、30-60% 重创级、>60% 毁灭级）。
   - **设计思路**：受击部位是演出"代入感"的核心细节。"光束击中驾驶舱"比"光束击中机体"更具冲击力。同时，损伤量级分级让文本反馈更精确——同样是 1000 点伤害，对 10000 HP 机体是"有效级"，对 1500 HP 机体是"毁灭级"，文本应该有所区分。

4. **语义化变量注入（SVI）与技能优先级策略**
   - **逻辑变化**：在 `assembler.py` 中新增 `SVI` 类，实现变量替换的优先级策略：精神指令（热血、魂）> 触发技能名 > 武器名。这解决了"当玩家使用热血时，文本应该显示热血而非武器名"的需求。
   - **设计思路**：机战中，玩家使用精神指令时最想看到的是"热血生效了"，而不是"光束步枪发射"。通过优先级映射，文本会显示"高达的魂爆发！光束步枪喷薄出毁灭性的粒子流！"，突出技能高光时刻。

5. **演出频道的 Outcome-First Routing**
   - **逻辑变化**：在 `router.py` 中实现严格有序的路由优先级表：
     1. `is_lethal` → FATAL（致死判定，最高优先级）
     2. `is_counter or is_support` → SPECIAL（特殊频道）
     3. `attack_result in (MISS, DODGE, PARRY)` → EVADE（闪避/未命中）
     4. 其余 → IMPACT（命中/格挡/暴击）
   - **设计思路**：传统系统是"意图优先"（先判断是什么攻击），但这会导致"致死打击被当作普通命中处理"的逻辑穿帮。新系统采用"结局优先"（先判断是什么结果），确保 FATAL 频道的演出永远不会被其他条件覆盖。

6. **双轨独立竞标机制**
   - **逻辑变化**：在 `bidder.py` 中实现 `DualBidder`，Action 竞标基于意图匹配+物理类软约束，Reaction 竞标基于频道匹配+物理类软约束。两次竞标完全独立，互不影响。
   - **设计思路**：旧系统中，Action 和 Phase 是"同生共死"的——要么都选中，要么都落选。这导致"完美的攻击描述"因为"缺少合适的受击描述"而被废弃。新系统中，ActionBone 和 ReactionBone 独立竞标，即使没有完美匹配的 ReactionBone，系统也会选择"物理类兼容度次优"的骨架，确保永远不会出现空文本。

7. **摄像机规则树与时间轴自适应**
   - **逻辑变化**：在 `av_dispatcher.py` 中实现摄像机选择规则树（优先级从高到低）：致死（dramatic_zoom）> 暴击（dramatic_zoom）> 近战闪避（close_combat_dodge）> 远距离（long_shot）> 近距离（close_up）> 闪避（tracking_evade）> 大伤害（shake_heavy）> 普通命中（shake_light）> 默认。
   - **设计思路**：摄像机是影视语言的核心。暴击时戏剧性缩放、远距离时远景、近战时特写，这些规则让文字演出具有"镜头感"。同时，时间轴根据攻击结果自适应调整——暴击增加 0.5s 戏剧停顿，光束武器持续 0.3s 飞行时间，致死增加 0.4s 冲击感。

8. **模板配置文件的格式精简**
   - **逻辑变化**：在 `config/presentation_templates.yaml` 中将模板格式从大一统结构精简为原子化骨架结构。旧格式需要同时定义 action_text 和 reaction_text，新格式只需定义 text_fragments 列表，由 L3 组装层随机选择。
   - **设计思路**：配置文件应该"简单到可以手工编辑"。旧格式中，添加一个新的"光束军刀斩击暴击"模板需要复制整个模板结构并修改多个字段。新格式中，只需添加一个 ActionBone（光束军刀斩击）和一个 ReactionBone（暴击反应），系统会自动组合。

9. **战斗文字模拟器的独立工具化**
   - **逻辑变化**：新增 `combat_simulator.py`（8196 字节），作为独立的演出系统演示工具。模拟器内置机体库、武器库和随机战斗生成器，可以快速生成 1v1 战斗的完整演出文本。
   - **设计思路**：演出系统的复杂度需要可视化工具来验证。模拟器让策划可以快速浏览"各种武器组合的演出效果"，无需运行完整的战斗引擎。同时，模拟器也是美术团队的"文字分镜参考"——根据文本描述设计动画、摄像机和特效。

10. **战斗引擎输出格式的可视化增强**
    - **逻辑变化**：在 `engine.py` 中优化 verbose 输出格式，使用符号+文字的双栏显示（✓ 命中、★ 暴击、✗ 未命中、▌ 格挡、↘ 躲闪、⚔ 招架），新增剩余 HP 显示，将气力变化单独分行显示。
    - **设计思路**：战斗日志应该"一眼看懂"。旧的 `print(f"✓ 命中! Roll点: 42.00 | 伤害: 1200")` 格式信息密度过高，玩家难以快速获取关键信息。新格式使用符号作为视觉锚点，伤害数值一目了然，剩余 HP 让玩家知道"还能撑几回合"。

**技术要点**
- `AttackEventBuilder` 使用 `_classify_physics()` 静态方法根据武器标签自动判断物理类（Energy/Kinetic/Blade/Impact），支持中英文标签混合识别
- `OutcomeRouter` 使用 lambda 函数链实现路由表，每个条件都是一个独立的 `lambda e: e.is_lethal`，便于快速调整优先级顺序
- `DualBidder` 的冷却跟踪使用 `bone_id -> 剩余回合` 的字典，每回合调用 `tick_cooldowns()` 递减，实现"避免同一演出连续刷屏"
- `TextAssembler` 的默认文本生成基于 VisualIntent 枚举，即使没有配置任何模板，系统也能生成合理的默认描述
- `AVDispatcher` 的摄像机规则树按 priority 降序排列，通过 `sorted(rules, key=lambda r: -r.priority)` 确保高优先级规则优先匹配
- `physics_class` 软约束使用权重倍率（匹配者 ×2.0，不匹配者 ×0.3/0.5），而非硬性过滤，确保"异类物理组合"也有机会出现（增加多样性）

**后续计划**
1. 完善 T0_LETHAL 模板库，为不同致死原因（驾驶舱中弹、动力炉过载、推进器连环爆炸）提供专属演出
2. 扩展 ActionBone/ReactionBone 骨架库，覆盖更多武器类型（如磁轨炮、钉刺、声波武器等）
3. 实现演出系统的 A/B 测试框架，自动统计"哪些模板被玩家跳过"（质量不足）和"哪些模板被玩家重复观看"（高光时刻）
4. 考虑将演出文本导出为脚本文件，支持多语言本地化（英语、日语）

---

## 2026-02-26 战斗统计系统与项目结构优化：从单体脚本到模块化架构

> **项目快照**：代码文件 30 个（4350 行）| 设计文档 7 个（2557 行）

### 逻辑变化与核心思路

1. **战斗统计收集器的独立封装**
   - **逻辑变化**：新增 `src/combat/statistics_collector.py`（282 行），将原本散落在 `sim_challenge_boss.py` 中的统计逻辑独立封装为 `StatisticsCollector` 类。实现了事件驱动的统计架构，通过 `on_attack_event()`、`on_en_consumed()`、`on_round_end()` 等接口接收战斗事件。
   - **设计思路**：旧的统计逻辑与 Boss 挑战模拟器深度耦合，导致无法在其他场景复用（如 PvP 对战、战役模式）。新的统计收集器遵循以下设计原则：
     - **事件驱动**：只订阅事件，不干预战斗流程，与 `BattleEngine` 完全解耦
     - **数据完整性**：从 `RawAttackEvent` 中提取攻击判定、伤害分布、技能触发等多维度统计
     - **可选详细记录**：通过 `enable_detailed_records` 参数控制是否记录完整的 `AttackRecord` 列表（内存敏感场景可关闭）
   - **核心数据结构**：
     - `AttackRecord`：单次攻击的完整记录，包含双方状态快照、Roll 值、触发技能等
     - `RoundSnapshot`：回合结束时的状态快照，用于战后回放和趋势分析
     - `BattleStatistics`：整场战斗的聚合统计，包含伤害极值、判定分布、技能触发率等

2. **项目目录结构重组**
   - **逻辑变化**：将 `main.py` 从根目录移至 `scripts/main.py`，删除废弃的 `scripts/battle_presentation_demo.py`。统一模拟器脚本入口到 `scripts/sim/` 目录。
   - **设计思路**：
     - **根目录清理**：根目录应该只保留项目级文件（README、配置、文档），可执行脚本统一归入 `scripts/`
     - **语义化组织**：`scripts/sim/` 专门存放数值模拟和测试工具，`scripts/` 存放主程序入口
     - **删除废弃代码**：`battle_presentation_demo.py` 的功能已被 `test_presentation_showcase.py` 和 `tests/test_presentation.py` 覆盖，保留只会增加维护负担

3. **战斗引擎的 Roll 值传递优化**
   - **逻辑变化**：在 `src/combat/engine.py` 的 `_execute_attack()` 方法中，将攻击判定的 `roll_value` 显式传递给统计收集器。新增 `set_roll_value()` 接口用于临时存储当前攻击的随机数。
   - **设计思路**：`RawAttackEvent` 设计为轻量级事件对象，不包含 `roll_value` 这类内部计算细节。但为了数值验证（验证圆桌判定概率分布是否符合预期），统计系统需要知道每次攻击的实际 Roll 值。通过"显式传递"而非"事件携带"的方式，保持了事件对象的简洁性，同时满足了统计需求。

4. **演出系统模型的兼容性调整**
   - **逻辑变化**：在 `src/presentation/models.py` 中调整了字段命名和结构，确保与统计收集器的无缝对接。统一使用 `weapon_type` 字段表示武器类型（与 `WeaponType` 枚举保持一致）。
   - **设计思路**：演出系统和统计系统都依赖 `RawAttackEvent`，但两者的关注维度不同——演出关心"如何描述这次攻击"，统计关心"这次攻击的结果数据"。通过统一字段命名和类型定义，避免数据转换层的重复代码。

5. **模拟器脚本的配置更新**
   - **逻辑变化**：更新 `scripts/sim/sim_challenge_boss.py` 和 `scripts/sim/sim_attack_table.py` 的导入路径，适配新的目录结构。优化了统计输出格式，与新的 `StatisticsCollector` 集成。
   - **设计思路**：模拟器是数值策划的核心工具，需要：
     - **一致的 API**：无论底层引擎如何变化，模拟器的命令行接口和输出格式保持稳定
     - **可复用组件**：通过复用 `StatisticsCollector`，模拟器代码从 1000+ 行缩减到约 500 行，统计逻辑不再重复实现

**技术要点**
- `StatisticsCollector` 使用 `dataclass` 定义所有数据结构，通过 `frozen=True` 确保事件对象不可变
- 伤害分布使用 `List[int]` 存储原始值，便于后续计算标准差、百分位数等统计指标
- 技能触发统计采用 `Dict[str, Dict[str, int]]` 结构，记录 `{skill_id: {attempts: N, success: M}}`
- 通过 `finalize()` 方法处理边界情况（如整场战斗未造成伤害时，`min_single_damage` 从 `inf` 归零）

**后续计划**
1. 基于 `StatisticsCollector` 实现"战斗录像回放"功能，支持从 `AttackRecord` 重建战斗过程
2. 扩展统计维度，增加"武器使用频率"、"技能组合效果"等深度分析指标
3. 编写 `sim_balance_analysis.py`，批量运行 1000+ 场战斗，验证数值平衡性
4. 考虑将统计数据导出为 CSV/JSON，支持数值策划在 Excel 中进一步分析

---

## 2026-02-19 演出系统落地与事件追踪优化：从架构设计到实战完善

> **项目快照**：代码文件 29 个（4250 行）| 设计文档 7 个（2557 行）

### 逻辑变化与核心思路

1. **演出模板系统的精细化匹配机制**
   - **逻辑变化**：在 `config/presentation_templates.yaml` 中为所有演出模板新增 `weapon_type` 条件字段（如 `MELEE`、`RIFLE`），实现了基于武器类型的精确匹配。大幅扩展 T2 战术模板库，新增近战轻斩/重斩的多种命中结果演出（HIT/MISS/DODGE/PARRY/BLOCK/CRIT），从基础模板扩展到 225+ 行的完整配置。
   - **设计思路**：之前的模板系统只区分"攻击意图"（INTENT_SLASH_LIGHT）和"判定结果"（HIT/MISS），但忽略了"武器类型"这一关键维度。光束军刀（MELEE）和光束步枪（RIFLE）即使都是"轻斩"意图，其物理表现截然不同——格斗武器强调接触、碰撞、烧蚀，射击武器强调弹道、爆炸、穿透。新增 `weapon_type` 条件后，演出系统可以：
     - **物理真实性**：光束被盾牌格挡时显示"光束在盾牌表面炸裂，电火花四溅"，而实弹被弹开时显示"弹头在装甲表面擦出一道火花后弹飞"
     - **武器差异化**：玩家能直观感受到"格斗机体"和"射击机体"的战斗风格差异，提升战斗的视觉多样性
   - **模板扩展**：新增大量近战演出模板，包括：
     - 轻斩（SLASH_LIGHT）：快速突刺、连击、招架
     - 重斩（SLASH_HEAVY）：破甲、巨冲击、双方武器碰撞
     - 每种意图都覆盖了 HIT/MISS/DODGE/PARRY/BLOCK/CRIT 六种判定结果

2. **武器标签系统的全面落地**
   - **逻辑变化**：在 `data/weapons.json` 中为所有武器新增 `weapon_tags` 字段（+99 行），定义了丰富的标签体系：
     - **能量武器**：`beam`（光束属性）
     - **格斗武器**：`slash_light`（轻型斩击）、`slash_heavy`（重型斩击）
     - **射击武器**：`rapid`（连射）、`projectile_single`（单发实弹）、`long_range`（远程）
   - **设计思路**：标签是连接"武器配置"与"演出匹配"的桥梁。相比传统的"武器类型枚举"（如 MELEE/RIFLE/SPECIAL），标签系统的优势在于：
     - **多态性**：同一武器可以拥有多个标签（如光束火箭炮 = `beam + massive + impact_massive`），支持复杂匹配（如"光束 + 重型"专属演出）
     - **可组合性**：未来可以通过标签组合实现"连锁攻击"演出（如先 `slash_light` 接 `slash_heavy`）
     - **向后兼容**：旧武器只需补充标签字段即可接入新系统，无需重构武器类型定义
   - **实际应用**：光束军刀（`beam + slash_light`）会触发"光束接触烧蚀"演出，而热能斧（`slash_heavy`）会触发"装甲撕裂、电火花飞溅"的重武器演出。

3. **事件管理器的单次攻击边界追踪（Bug Fix #1）**
   - **逻辑变化**：在 `src/skill_system/event_manager.py` 中新增 `begin_attack()` 和 `end_attack()` 配对方法，实现了单次攻击的事件边界追踪。在 `src/combat/engine.py` 的 `_execute_attack()` 中调用这两个方法，精确捕获本次攻击期间触发的技能事件。
   - **设计思路**：之前的事件系统使用 `get_current_round_events()` 获取整个回合的事件，这导致先攻方和后攻方的技能事件混在一起。例如先攻方触发"吸血鬼"技能，后攻方反击时也会看到这个事件，破坏了"每次攻击独立演出"的设计预期。
   - **新机制**：
     - `begin_attack()` 在攻击开始时调用，清空本次攻击的事件缓存
     - `end_attack()` 在攻击结束时调用，返回本次攻击期间触发的所有技能（过滤 `triggered=False` 的失败事件）
     - 事件同时存入"回合级缓存"（兼容旧接口）和"攻击级缓存"（新接口）
   - **解决的问题**：彻底避免先攻方与后攻方的事件混用，确保每次攻击的演出只包含本次攻击触发的技能。

4. **武器类型命名的统一化修正（Bug Fix #2-3）**
   - **逻辑变化**：在 `src/models.py` 中将 `WeaponType.RIFLE` 重命名为 `SHOOTING`，并在 `EquipmentConfig` 的类型映射中同步更新。保留 `"RIFLE": "SHOOTING"` 的向后兼容映射。
   - **设计思路**：`RIFLE`（步枪）这个词过于具体，无法涵盖所有射击武器（机枪、火箭炮、轨道炮等）。`SHOOTING` 更符合"射击类武器"的语义，与 `MELEE`（格斗）、`AWAKENING`（觉醒）形成清晰的三分类。
   - **影响范围**：`data/weapons.json` 中的 `weapon_type` 字段已全部使用 `"SHOOTING"`，旧配置文件中的 `"RIFLE"` 会被自动映射到 `"SHOOTING"`，确保向后兼容。

5. **演出选择器的 T0 层级职责明确（Bug Fix #4）**
   - **逻辑变化**：在 `src/presentation/selector.py` 中重构 `_gather_candidates()` 方法，明确 T0（剧情强制）层级由 `ScriptedPresentationManager` 独占处理，`TemplateSelector` 只处理 T1/T2/T3 层级。
   - **设计思路**：之前的设计中，T0 模板可以通过 `TemplateRegistry` 注册，也可以通过 `ScriptedPresentationManager` 注入，这导致"两个 T0 系统"的职责边界模糊，可能出现优先级冲突。
   - **新架构**：
     - **T0（剧情强制）**：完全由 `ScriptedPresentationManager` 在 `EventMapper.map_attack()` 之前处理，用于 Boss 战开场白、特定 HP 阈值触发等剧情节点
     - **T1/T2/T3**：由 `TemplateSelector` 在 `EventMapper.map_attack()` 中处理，遵循优先级竞标机制
   - **解决的问题**：避免两个 T0 系统竞争导致的优先级混乱，确保剧情演出拥有最高优先级且不会被通用模版覆盖。

6. **战斗引擎的健壮性改进（Bug Fix #5）**
   - **逻辑变化**：在 `src/combat/engine.py` 中无条件初始化 `self.presentation_timeline: list[PresentationRoundEvent] = []`，即使 `enable_presentation=False` 也会创建空列表。
   - **设计思路**：之前的设计中，`presentation_timeline` 只在 `enable_presentation=True` 时初始化，导致当演出系统禁用时，外部代码访问 `engine.presentation_timeline` 会抛出 `AttributeError`。这破坏了"引擎 API 的一致性"——外部代码需要判断 `if engine.enable_presentation and engine.presentation_timeline` 才能安全访问。
   - **新机制**：无条件初始化空列表，确保 `engine.presentation_timeline` 始终可用（即使为空）。这样外部代码可以安全地遍历 `timeline` 而无需判断演出是否启用。

7. **演出事件存储的时机优化**
   - **逻辑变化**：在 `src/combat/engine.py` 中将演出事件的存储逻辑从"仅在演出启用时执行"改为"始终创建 `PresentationRoundEvent` 和 `PresentationAttackSequence`"。
   - **设计思路**：即使 `enable_presentation=False`，时间线数据仍然有收集价值——用于战后回放、AI 训练数据、统计分析等。将"数据收集"与"文本渲染"解耦，确保时间线数据的完整性。
   - **实际应用**：未来可以基于 `presentation_timeline` 实现"战斗录像回放"功能，重播整场战斗的演出序列，即使演出系统在战斗时是禁用的。

**技术要点**
- 事件追踪使用类变量 `_in_attack: bool` 标记当前是否处于攻击追踪中，避免嵌套调用导致的时序错误
- `end_attack()` 返回的 `List[Any]` 是触发成功的技能事件列表（已过滤 `triggered=False`），可以直接传递给演出系统
- 武器类型重命名采用"双轨制"：新代码使用 `WeaponType.SHOOTING`，旧配置文件中的 `"RIFLE"` 会被映射到 `"SHOOTING"`，确保平滑迁移
- 演出选择器的 `HANDLED_TIERS = (T1, T2, T3)` 元组明确排除了 T0，通过注释说明"T0 由 ScriptedPresentationManager 独占"
- `presentation_timeline` 的无条件初始化符合"最小惊讶原则"（Principle of Least Astonishment），用户预期引擎始终有时间线，无论演出是否启用

**后续计划**
1. 扩展 T2 战术模板库，覆盖射击武器的多种命中结果演出（如"实弹被装甲弹开"、"光束被I力场格挡"等）
2. 实现基于"武器标签组合"的复合演出（如 `beam + massive` 触发"巨型光束炮"专属演出）
3. 编写演出系统的性能测试，验证 100 回合战斗的事件收集耗时（目标：<10ms）
4. 基于 `presentation_timeline` 实现"战斗录像回放"功能，支持导出为 JSON/视频

---

## 2026-02-17 演出系统彻底重构：从实现指南到优先级分层

> **项目快照**：代码文件 29 个（4200 行）| 设计文档 7 个（2557 行）

### 逻辑变化与核心思路

1. **演出系统架构的全面重设计**
   - **逻辑变化**：删除了旧的 `docs/presentation_implementation_guide.md`（1218 行）和 `docs/presentation_usage.md`（241 行），将核心设计整合到 `docs/6.combat_presentation.md`（643 行重构）。新增 `src/presentation/constants.py`、`intent_extractor.py`、`loader.py`、`registry.py`、`scripted_manager.py`、`selector.py`、`template.py` 等模块。
   - **设计思路**：旧系统存在三个核心问题：
     - **文档臃肿**：实现指南（1218 行）比实际代码还长，导致文档与代码脱节，更新维护成本极高
     - **职责混乱**：Mapper 既负责数据映射又负责文本渲染，违反单一职责原则，导致测试困难
     - **优先级缺失**：所有演出模版平级存在，无法解决"剧情台词 > 技能特效 > 通用描述"的优先级冲突
   - **新架构**：采用四层优先级系统（T0 剧情强制 > T1 高光时刻 > T2 战术细节 > T3 通用保底），通过 `Selector` 组件实现竞标机制（T1 内部加权竞标，T2 首次匹配）。

2. **T-Hierarchy 优先级系统的实施**
   - **逻辑变化**：在 `src/presentation/selector.py` 中实现了严格的优先级选择流程：
     - **T0（剧情强制）**：权重 1000，由关卡脚本注入，完全跳过 T1-T3 判定。用于 Boss 变身、暴走、强制撤退等剧情节点。
     - **T1（高光时刻）**：权重 100/80/50 分三级，包含 A 类扭转（必闪必中）、B 类爆发（热血魂）、C 类特质（性格机体）。T1 内部通过加权竞标解决冲突，同分随机。
     - **T2（战术细节）**：基于武器标签（beam、slash、impact）和判定结果的物理归因描述。例如"光束被盾牌格挡" vs "实弹被装甲弹开"。
     - **T3（通用保底）**：简单的"A 攻击了 B"描述，防止配置缺失导致空文本。
   - **设计思路**：建立清晰的"演出优先级链"，确保关键剧情不被通用描述淹没。同时通过降权机制（De-weighting）避免同一台词连续刷屏——若某 ID 本回合胜出，下回合权重 -30。

3. **武器标签系统的引入**
   - **逻辑变化**：在 `data/weapons.json` 中为所有武器新增 `weapon_tags` 字段：
     - **光束类**：`beam`（光束属性）、`long_range`（远程）
     - **格斗类**：`slash_light`（轻型斩击，如光束军刀）、`slash_heavy`（重型斩击，如热能斧）
     - **实弹类**：`rapid`（连射）、`projectile_single`（单发实弹）
     - **重武器类**：`massive`（巨型冲击）、`impact_massive`（巨冲击）
   - **设计思路**：标签是连接 Action（攻击意图）与 Reaction（防御响应）的握手协议。例如 T2 模版可以根据 `beam` 标签匹配"I 力场格挡"演出，而 `slash_heavy` 匹配"装甲烧蚀"演出。这比传统的"武器类型枚举"更灵活，支持多标签组合（如 `beam + massive` 匹配"巨型光束"专属演出）。

4. **意图提取器（IntentExtractor）的职责分离**
   - **逻辑变化**：新增 `src/presentation/intent_extractor.py`，专门负责从武器和攻击者提取"意图标签"。
   - **设计思路**：将"物理属性提取"从文本生成中剥离。意图提取器只回答"这是什么类型的攻击？"（光束/实弹/斩击/冲击），不涉及任何文本生成。这样测试时可以单独验证意图提取的正确性，而不需要依赖复杂的文本渲染。

5. **演出模版的注册表模式（TemplateRegistry）**
   - **逻辑变化**：新增 `src/presentation/registry.py`，采用"注册表 + 工厂"模式管理所有演出模版。模版不再硬编码在 Mapper 中，而是通过 `@register_template(action/reaction, priority, tags)` 装饰器注册。
   - **设计思路**：建立"模版即插件"的扩展机制。新增技能演出时，只需在技能模块中注册模版，无需修改核心代码。注册表支持动态加载，未来可以通过 JSON 配置或 DLC 方式扩展演出模版，而不触及战斗引擎。

6. **数据模型的精简与类型安全**
   - **逻辑变化**：在 `src/presentation/models.py` 中大幅简化数据结构：
     - **攻击意图（AttackIntent）**：从复杂的嵌套字典简化为 `@dataclass`，包含 `intent_tags`（标签列表）、`attack_result`（判定结果）、`display_tags`（UI 高亮标签）
     - **演出模版（PresentationTemplate）**：明确区分 `action_template`（主动阶段）和 `reaction_template`（被动阶段），移除了冗余的 `actor`/`target` 字段（改用上下文传递）
   - **设计思路**：通过 `@dataclass` 的类型提示和 `frozen=True` 不可变性，确保演出数据在传递过程中不会被意外修改。这解决了旧系统中"模版在渲染过程中被污染，导致下次渲染异常"的隐蔽 Bug。

7. **渲染器（Renderer）的纯函数化**
   - **逻辑变化**：将 `src/presentation/renderer.py` 从 357 行重构为纯函数集合。每个渲染函数只负责一种类型的文本生成（如 `render_action()`、`render_reaction()`），不再持有状态。
   - **设计思路**：渲染器应该是"无状态的字符串拼接器"，不涉及任何业务逻辑。所有的模版选择、竞标、降权都在 Selector 阶段完成，Renderer 只负责"将选定的模版填入数据"。这样做的好处是渲染器可以安全地并发调用（前端同时渲染多个战斗回放），无需担心状态污染。

8. **测试覆盖率的提升**
   - **逻辑变化**：`tests/test_presentation.py` 从基础测试扩展到 369 行，新增以下测试场景：
     - **意图提取测试**：验证不同武器标签组合是否提取出正确的意图
     - **优先级竞标测试**：验证 T1 内部加权竞标机制（如"暴击"权重高于"普通命中"）
     - **降权机制测试**：验证同一模版连续出现时权重是否正确下降
     - **注册表完整性测试**：验证所有已注册模版的必需字段（template_id、priority 等）
   - **设计思路**：演出系统是连接战斗逻辑和前端展示的桥梁，任何错误都会直接暴露给玩家。测试重点不是"文本是否优美"，而是"系统是否健壮"——优先级是否正确、竞标是否公平、注册表是否完整。

**技术要点**
- **防御机制概率分布**：通过模拟器验证，当前防御区间为 `DODGE: 36.0% [0.0-36.0]`、`PARRY: 45.0% [36.0-81.0]`、`BLOCK: 15.0% [81.0-96.0]`。相比旧设计（Miss 12% / Dodge 22% / Parry 15% / Block 20%），新设计大幅提升了招架占比，增强了"以守为攻"的战术路线。
- **降权公式**：`adjusted_score = base_score - (win_count * 30)`，防止同一演出连续出现超过 3 次（第 4 次权重为负，必被其他模版取代）。
- **武器标签的多态性**：同一武器可以拥有多个标签（如光束火箭炮 = `beam + massive + impact_massive`），匹配时采用"交集原则"（所有标签都满足才触发）。
- **意图提取的回退机制**：当武器无标签或标签无法匹配时，提取器返回 `GENERIC` 意图，触发 T3 通用保底模版，确保不会出现空文本。

**后续计划**
1. 扩充 T2 战术细节模版库，覆盖更多武器组合（如"光束格斗"、"实弹狙击"等）
2. 实现 T0 剧情强制演出，与剧情脚本系统集成（Boss 战开场白、特定 HP 阈值触发）
3. 编写演出系统的性能测试，验证 100 回合战斗的文本生成耗时（目标：<50ms）
4. 考虑引入"演出预加载"机制，提前缓存常用模版，减少运行时字符串拼接开销

---

## 2026-02-15 能量系统平衡性与模拟器重构：从资源耗竭到持久战

> **项目快照**：代码文件 17 个（3206 行）| 设计文档 7 个（2548 行）

### 逻辑变化与核心思路

1. **能量（EN）回能机制的全面实现**
   - **逻辑变化**：在 `src/models.py` 中新增 `init_en_regen_rate`（百分比回能）和 `init_en_regen_fixed`（固定值回能）两个核心字段，并在 `MechaConfig` 和 `MechaSnapshot` 中同步添加。在 `src/combat/engine.py` 中新增 `_apply_en_regeneration()` 方法，实现了每回合自动回能机制。
   - **设计思路**：之前的 EN 系统只消耗不回复，导致战斗变成了"资源管理游戏"——玩家必须精打细算每一发弹药，否则 20 回合后就会因 EN 耗尽而只能撞击。这偏离了机战核心玩法（热血对波、技能爆发）。新增回能机制后：
     - **百分比回能**：`final_max_en * (en_regen_rate / 100)`，适配不同体量的机体（高 EN 机体回能更多）
     - **固定值回能**：`en_regen_fixed`，为低 EN 机体提供保底回能
     - **双轨制设计**：例如高达的 `en_regen_rate=2.0`（2%）+ `en_regen_fixed=3`（固定 3 点），每回合可回复 `400 * 0.02 + 3 = 11` 点 EN
     - **回能时机**：在 `_execute_round()` 的回合结束阶段（气力变化后、效果结算前），确保"本回合消耗 → 回合结束回复 → 下回合可用"的自然节奏

2. **武器消耗与威力的全面重平衡**
   - **逻辑变化**：在 `data/weapons.json` 中对所有武器进行了数值重做：
     - **光束步枪**：威力 800 → 2000（+150%），消耗 20 → 5（-75%）
     - **光束军刀**：威力 1200 → 1500（+25%），消耗 15 → 4（-73%）
     - **120mm 机炮**：威力 700 → 1500（+114%），消耗 18 → 3（-83%）
     - **热能斧**：威力 1100 → 1800（+64%），消耗 20 → 5（-75%）
     - **光束火箭炮**：威力 1400 → 4000（+186%），消耗 35 → 8（-77%）
   - **设计思路**：旧的武器数值设计存在三个核心问题：
     - **消耗过高**：光束步枪消耗 20 EN，但高达初始 EN 只有 100，意味着 5 发就耗尽。这导致玩家被迫使用"撞击"（0 EN 但仅 50 威力），战斗变成了"谁先用完 EN 谁输"的惩罚游戏
     - **威力不足**：800 威力的光束步枪面对 Boss 的 500000 HP 和 1000 防御，单发仅造成约 200-300 伤害，需要 2500 发才能击杀。这在"只有 5 发"的设定下完全不可能
     - **不平衡性**：光束火箭炮作为重武器，消耗 35 EN 但威力仅 1400，相比光束步枪的"性价比"极低（1400/35=40 vs 800/20=40）
   - **新设计目标**：通过降低消耗（平均 -75%）和提升威力（平均 +100%），实现：
     - **持久战**：玩家可以持续使用主力武器战斗 50+ 回合，而非 5 回合就耗尽
     - **战术多样性**：不同武器的"威力/消耗比"拉开差距（光束火箭炮 4000/8=500 vs 光束步枪 2000/5=400），形成明确的"高消耗高爆发"vs"低消耗高续航"的战术选择
     - **Boss 挑战可行性**：光束步枪单发 2000 威力，在 50 回合内可造成约 100000 伤害，配合技能暴击等机制，挑战 500000 HP 的 Boss 成为可能

3. **装备与机体的回能属性补充**
   - **逻辑变化**：在 `data/equipments.json` 中为"动力发电机"和"超小型发电机"新增 `final_en_regen_rate: 1.0`；在 `data/mechas.json` 中为"高达 RX-78"和"扎古 II"新增 `init_en_regen_rate: 2.0` 和 `init_en_regen_fixed: 3`。
   - **设计思路**：建立"机体基础回能 → 装备额外回能"的层级体系。高达基础回能 2% + 3 点，安装动力发电机后 +1%，总回能 3% + 3 点。这为装备选择提供了更多策略维度——是选择"乔巴姆装甲"（防御）还是"动力发电机"（续航），取决于玩家是偏向"硬抗"还是"持久战"。

4. **工厂模式的回能参数集成**
   - **逻辑变化**：在 `src/factory.py` 的 `_apply_equipment_modifiers()` 方法中新增对 `en_regen_rate` 和 `en_regen_fixed` 的处理逻辑，并将这两个参数加入返回值元组。
   - **设计思路**：工厂模式的核心价值是"统一的数据转换流水线"。所有从配置到机体的属性修正，都应该通过 `_apply_equipment_modifiers()` 处理，避免在多个地方重复编写 `mecha.final_en_regen_rate = base + sum(equip.modifiers)` 的逻辑。
   - **类型修正**：注意到 `final_mobility` 的类型问题，从 `int` 修正为 `float`（因为机动性可能被装备修正为小数值，如 +5.5）。虽然本次未直接修改 mobility 相关逻辑，但为未来的精细化数值平衡扫清了障碍。

5. **Boss 挑战模拟器的深度重构（降低过度封装）**
   - **逻辑变化**：在 `sim/sim_challenge_boss.py` 中进行了大规模代码简化，从 1090 行压缩到约 498 行（删除 542 行，新增 498 行，净减少 221 行）。主要重构包括：
     - **统计模块化**：将 `print_statistics()` 拆分为 `print_damage_distribution()`、`print_survival_stats()` 和 `print_skill_statistics()` 三个独立函数，每个函数负责单一职责。
     - **配置扁平化**：移除 `BOSS_CONFIG` 和 `CHALLENGER_CONFIG` 中的详细注释和分组，改为紧凑的单层字典。原因是"配置修改需要深入注释块"反而增加了维护负担，简洁的键名已足够自解释（如 `weapon_power_percent` 明显是"武器威力占 Boss HP 的百分比"）。
     - **数据类精简**：在 `RoundStatistics` 和 `BattleStatistics` 中移除冗余的字段分组注释（如 `# 先手攻击统计`、`# 后手攻击统计`），改为通过字段命名自解释（`first_weapon` 明显是先手武器，无需注释）。
     - **移除过度封装**：删除 `get_maintain_skill()` 函数（直接在 `run_single_battle()` 中创建技能对象），删除 `get_skill_name()` 和 `get_skill_info()` 中的过度防御性编程（如空字典的默认值），改为直接访问 JSON 数据。
     - **统计收集优化**：在 `_execute_attack_with_stats()` 中移除不必要的中间变量（如 `is_challenger`、`is_boss`），直接通过对象引用判断。
   - **设计思路**：旧的模拟器代码存在"过度封装"的问题：
     - **过度注释**：每个配置项都有 4-5 行注释，导致 50 行的配置实际只有 10 行有效数据。注释反而阻碍了快速修改——数值策划需要滚动浏览大量注释才能找到要改的参数。
     - **过度抽象**：`get_skill_name()` 和 `get_skill_info()` 试图提供"统一接口"，但实际使用场景只有一处（打印统计），反而增加了调用链。
     - **防御性编程过度**：大量 `if key in dict` 检查和默认值返回，但数据来源是可控的 JSON 配置文件，这些检查在 99% 的情况下都是冗余的。
   - **重构原则**：**"代码即文档"**——通过清晰的变量命名和函数职责划分，让代码本身成为最好的文档，而不是依赖大量注释。例如 `print_damage_distribution(damages, "挑战者")` 比任何注释都更清晰地表达了"打印伤害分布统计"的意图。

6. **战斗引擎的 EN 回能与撞击威力调整**
   - **逻辑变化**：在 `src/combat/engine.py` 的 `_execute_round()` 方法中，在回合结束阶段调用 `_apply_en_regeneration()` 为双方机体回复 EN。同时将"撞击"武器（Fallback Weapon）的威力从 50 提升到 600。
   - **设计思路**：
     - **回能时机**：选择在 `modify_will(1)` 之后、`EffectManager.tick_effects()` 之前调用回能，确保：
       - 气力变化相关的技能（如"气力 ≥ X 时回 EN"）已经生效
       - 效果结算时（可能触发"回合结束回 EN"的效果）使用的是已经回能后的 EN 值
     - **撞击威力提升**：旧的撞击仅 50 威力，面对 Boss 的防御几乎不破防（1000 防御下仅造成 0-10 伤害）。提升到 600 后，即使玩家 EN 耗尽，依然可以通过撞击造成可观的伤害（约 100-200/次），避免了"耗尽后完全无力"的挫败感。

7. **数据加载器的简化**
   - **逻辑变化**：在 `src/loader.py` 中移除了部分兼容层代码（具体内容从 git diff 显示为 `8 -`），简化了加载逻辑。
   - **设计思路**：随着项目演进，某些早期为了"兼容旧格式"而添加的兼容层已经不再需要（例如处理多个版本的 JSON 结构）。移除这些冗余代码可以提升代码可读性，减少维护负担。

**技术要点**
- EN 回能公式 `total_regen = int(max_en * rate / 100) + fixed` 使用整数截断，避免浮点数累积误差（如 400 * 0.02 = 7.999999...）
- `min(mecha.final_max_en, mecha.current_en + total_regen)` 确保 EN 不超过上限，避免"无限堆叠回能"的 bug
- 模拟器重构遵循"单一职责原则"（Single Responsibility Principle），每个函数只做一件事（如 `print_damage_distribution` 只负责打印伤害分布，不涉及数据收集）
- 武器威力与消耗的"性价比"计算：`power / en_cost`，用于数值策划快速评估武器平衡性（如光束火箭炮 500 vs 光束步枪 400，差距 25%）
- Boss 的 `weapon_power_percent` 从 0.0008（0.08%）提升到 0.001（0.1%），配合 Boss 500000 HP，单发威力约为 500，与玩家光束步枪的 2000 相比约为 1:4，符合"Boss 攻击力弱但血厚"的设计预期

**后续计划**
1. 基于模拟器统计数据，进一步微调武器的"威力/消耗比"，确保不同武器都有其战术价值（避免"最优解"滥用）
2. 实现" EN 不足时自动切换到次优武器"的 AI 逻辑，避免玩家因 EN 管理失误而被迫撞击
3. 扩展装备系统，增加更多回能相关装备（如"高性能发电机"、"紧急供能装置"等），丰富战术选择
4. 编写数值平衡测试（如 `sim_balance_en_regen.py`），验证不同回能配置下的战斗时长分布（预期 30-50 回合）

---

## 2026-02-14 事件系统与技能扩容：从概率型到条件型

> **项目快照**：代码文件 16 个（3166 行）| 设计文档 7 个（2548 行）

### 逻辑变化与核心思路

1. **轻量级事件系统的完整实现**
   - **逻辑变化**：在 `src/skill_system/event_manager.py` 中新增 `EventManager` 类，实现了轻量级的发布/订阅系统。新增 `src/models.py` 中的 `TriggerEvent`（不可变数据类）和 `BuffState`（可变状态类）两个核心数据模型。
   - **设计思路**：为了支持"前端实时演出"和"技能触发统计分析"两个需求，建立了统一的事件总线。`EventManager` 的职责单一：
     - **统计收集**：自动记录每个技能的尝试次数（attempts）和成功次数（success），用于数值验证
     - **事件广播**：将触发成功的事件推送给前端（如 UI 图标闪烁、伤害数字弹出），失败事件仅统计不广播
     - **轻量设计**：使用类变量存储回调和统计数据，避免全局单例的复杂性。通过 `EventManager.clear_statistics()` 在每场战斗后清理，防止数据污染
   - **数据不可变性**：`TriggerEvent` 使用 `@dataclass(frozen=True)` 确保事件一旦发布就不可篡改，避免了"前端修改事件数据导致的统计错误"。
   - **生命周期管理**：`BuffState` 通过 `is_expired()` 和 `tick()` 实现了持续时间和次数的双重衰减机制。支持 `-1` 表示永久/无限，用于区分"精神指令（临时）"和"机体特性（永久）"。

2. **战斗引擎的事件化改造**
   - **逻辑变化**：在 `src/skill_system/processor.py` 中集成了完整的事件发布机制：
     - **概率失败事件**：当 `trigger_chance < 1.0` 且随机数未命中时，发布 `triggered=False` 的事件（仅统计，不广播）
     - **成功触发事件**：记录 `old_value` → `new_value` 的数值变化，包含完整上下文
     - **次数耗尽事件**：当 `charges` 减为 0 时，发布特殊标记事件，前端可据此播放"效果消失"动画
   - **设计思路**：将"透明化输出"（print 日志）升级为"结构化事件"（TriggerEvent）。原来的 `print(f"[Skill] {effect.name} 触发!")` 变成了 `EventManager.publish_event(TriggerEvent(...))`。这样做的好处：
     - **前端可用性**：前端可以直接订阅 `EventManager`，实时显示技能图标、伤害飘字、战斗日志
     - **数值可追溯**：每个事件都记录了 `old_value` 和 `new_value`，战后可以回放整个战斗过程
     - **测试可验证**：测试代码可以断言"某个技能被触发了N次"，而不是依赖字符串匹配日志
   - **副作用集成**：在 `src/skill_system/side_effects.py` 中也集成了事件发布，包括 EN 消耗、新效果施加等，实现了"技能的每一个作用都被记录"。

3. **概率型与条件型技能的批量生成**
   - **逻辑变化**：新增 `script/generate_probabilistic_skills.py` 生成脚本，自动生成 `data/skills_extended.json` 配置文件。扩容了 26 个新技能：
     - **概率型精神指令**（8 个）：暴击爆发（30%）、幸运闪避（25%）、绝地一击（40% HP<30%）、狂怒（20% 受伤后）、回光返照（35% HP<20%）、反击（30% 被攻击时）、精准打击（25%）、能量涌动（40% EN<30%）
     - **概率型机体特性**（8 个）：暴击大师（20% 暴击时回 EN）、闪避反射（25% 躲闪后反击）、最后手段（50% HP<10%）、肾上腺素（30% 致死伤害时保命）、吸血鬼（15% 伤害吸血）、幸运星（10% MISS 时返 EN）、法力护盾（20% 用 EN 抵伤害）、狂暴模式（40% HP<30% 时攻防翻倍）
     - **条件型技能**（10+ 个）：处决（对 HP<50% 敌人）、破防（对防御率>50% 敌人）、终结（对 HP<20% 敌人）、防御姿态/攻击姿态（HP 阈值切换）、生命守护（HP 越低防越高）、气势（连续命中增伤）、反击（被攻击时）、处刑者（对低血敌暴击率）、属性优势、死斗（HP 越低攻越高）、高效（EN>50% 减耗）、相位转移（回合阶段切换）、连击大师（连续命中后必暴）、适应性装甲（受伤后抗性）、怒气累积（受伤增暴击）
   - **设计思路**：建立"技能配置生成器"而非手工编写。通过 Python 字典定义技能模板，运行时自动合并到 `skills_extended.json`。这样做的好处：
     - **批量修改**：调整所有概率型技能的触发概率时，只需修改模板中的数值，重新生成即可
     - **分类统计**：生成脚本会自动输出"技能分类统计"表格，包括触发概率、条件类型等关键信息
     - **避免冲突**：生成时会检查"技能ID 是否已存在"，避免覆盖现有技能
   - **概率型 vs 条件型**：明确了两个维度的技能设计：
     - **概率型**：`trigger_chance < 1.0`，即使条件满足也需要摇骰子，增加随机性（如"吸血鬼"不是每次伤害都吸血）
     - **条件型**：`conditions` 字段定义触发前提（如 HP 阈值、目标类型），满足条件后 100% 触发，用于策略性选择（如"处决"对低血敌必增伤）

4. **Boss 挑战模拟器的统计系统升级**
   - **逻辑变化**：在 `sim/sim_challenge_boss.py` 中重构了技能统计逻辑：
     - **旧设计**：`skills_triggered`（Counter）记录"技能被应用的总次数"，无法区分"触发成功"和"触发失败"
     - **新设计**：`skill_trigger_stats`（Dict）记录 `{attempts, success}`，可以从 `EventManager.get_statistics()` 直接获取
     - **统计输出优化**：新增"理论触发率"和"实际触发率"的对比。例如"吸血鬼"配置为 15%，实测可能在 13%-17% 波动，用于验证概率系统的正确性
     - **每场清理**：在每场战斗前调用 `EventManager.clear_statistics()`，防止多场战斗的数据混淆
   - **设计思路**：模拟器的核心价值不是"运行战斗"，而是"验证数值平衡性"。通过 100+ 场自动模拟，统计：
     - **出现率**：技能被随机抽取并应用的概率（如"吸血鬼"出现在 80% 的场次数）
     - **实际触发率**：技能在战斗中的实际触发次数 / 触发机会次数（如"吸血鬼" 15% 概率，实测 14.8%）
     - **场均次数**：每场战斗平均触发次数（如"暴击大师"场均 0.3 次）
     - **理论 vs 实际**：如果"幸运闪避"配置 25%，但实测只有 5%，说明要么触发条件苛刻，要么概率计算有 Bug

5. **测试覆盖事件系统**
   - **逻辑变化**：新增 `tests/test_skill_event_system.py`（211 行），全面测试了事件系统的核心功能：
     - **事件不可变性**：通过 `pytest.raises(Exception)` 验证 `frozen` dataclass 确实不可修改
     - **BuffState 生命周期**：测试 `is_expired()` 在 `duration=0`、`charges=0` 时的正确性，测试 `tick()` 对持续时间和次数的衰减
     - **永久 Buff 特殊处理**：测试 `duration=-1`、`charges=-1` 时 `tick()` 不减少值
     - **EventManager 统计**：测试多个技能的独立统计，验证 `{attempts, success}` 的正确累加
     - **失败事件不广播**：测试 `triggered=False` 时回调函数不被调用，但统计数据仍被记录
   - **设计思路**：事件系统是连接"战斗引擎"和"前端演出"的桥梁，必须 100% 可靠。测试覆盖了：
     - **数据正确性**：统计数字准确无误（attempts 和 success 独立计数）
     - **边界条件**：永久 buff、过期 buff、次数耗尽的正确处理
     - **隔离性**：多场战斗的统计不相互污染

6. **文档结构的重组**
   - **逻辑变化**：删除了 `doc/` 目录下的所有设计文档（0.start.md、1.battle_design_doc.md 等），新建了 `docs/` 目录（当前为空或包含新文档）。
   - **设计思路**：从代码审计角度出发，旧的 `doc/` 文档可能存在以下问题：
     - **与代码脱节**：设计文档可能还是"初始构想"，但代码已经多次重构
     - **冗余信息**：包含大量"设计历程"和"废弃方案"，混淆当前逻辑
     - **命名不统一**：`doc` vs `docs`，应统一为标准命名
   - **后续行动**：需要基于当前代码状态，重新编写精简的"技术文档"（而非"设计文档"），包括：
     - **架构文档**：事件系统、技能系统的当前实现逻辑
     - **API 文档**：`EventManager`、`TriggerEvent` 的使用方法
     - **数据契约**：`skills.json` 的配置字段说明

**技术要点**
- `EventManager` 使用类变量而非实例变量，避免了全局单例的传递复杂性，但牺牲了"多个独立事件总线"的能力（当前场景够用）
- `TriggerEvent` 的 `frozen` 确保了事件不可变，但 `owner: Any` 存储的是 `Mecha` 对象引用，需注意内存管理（前端不应长期持有事件引用）
- 概率型技能的 `trigger_chance` 判定在 `EffectProcessor.process_effects()` 中，早于 `ConditionChecker.check()`，这意味着"条件满足但概率未命中"不会计入 attempts（符合预期）
- `BuffState` 的 `duration` 和 `charges` 是独立的，只要有一个归零就过期（逻辑 `or`），这导致"持续 3 回合或使用 5 次"的技能可能在第 2 回合就耗尽次数

**后续计划**
1. 完善 `docs/` 目录，编写基于当前代码的技术文档（架构图、API 文档、配置指南）
2. 扩展 `EventManager`，支持"按订阅者过滤事件"（如前端只订阅视觉相关事件，测试只订阅统计事件）
3. 基于模拟器统计数据，调整概率型技能的触发概率（如"吸血鬼"15% 可能过低，考虑提升至 20-25%）
4. 实现"前端事件回调"的完整示例（如 WebSockets 推送、React 状态更新）

---

## 2026-02-12 技能库扩充与测试覆盖率完善

> **项目快照**：代码文件 14 个（3043 行）| 设计文档 6 个（1956 行）

### 逻辑变化与核心思路

1. **精神指令体系的全面扩展**
   - **逻辑变化**：在 `src/skills.py` 中新增了 12 个精神指令方法（梦境、威压、搅乱、奇迹、本能、激怒、气魄、努力、拖延、执念、再动），并在 `data/skills.json` 中配置了完整的 JSON 数据（+467 行）。
   - **设计思路**：补充机战经典的精神指令系统。核心区分三类指令：
     - **先手类**（梦境、威压）：通过 `HOOK_INITIATIVE_CHECK` 强制先手，支持优先级控制（梦境优先级 95 > 威压 90）
     - **状态修正类**（搅乱、奇迹、本能、激怒）：修正命中/回避/暴击等核心判定参数
     - **特殊机制类**（气魄、努力、拖延、执念、再动）：通过回调函数实现复杂逻辑（如气魄在造成伤害时 +3 气力）
   - **数据驱动原则**：所有精神指令都是 JSON 配置 + 代码回调的组合，避免了硬编码。例如"奇迹"通过 `operation="callback"` 调用 `cb_miracle_hit`，将 MISS 强制转为 HIT。

2. **机体特性（Traits）的丰富化**
   - **逻辑变化**：新增 14 个机体特性回调函数，包括：
     - **防御型**：自动修复（回复 20% 受到伤害）、烧蚀装甲（光束伤害 -200）、再生（每回合 +5% HP）
     - **资源管理型**：快速装填（攻击结束 +15 EN）、省能源（每回合 +5 EN）、士气（战斗结束 +30 EN）
     - **进攻型**：吸血（回复 10% 伤害）、气魄（造成伤害时 +3 气力）、看破（暴击率 +25%）
     - **条件触发型**：本能（30% 概率 HIT→DODGE）、超反应（气力 ≥ 120 时招架率 +15%）
   - **设计思路**：建立"固有特性"与"精神指令"的清晰界限。特性是永久或长期生效的机体性能（如"GN炉回复"），而精神指令是临时爆发。这为机体差异化提供了基础——同样装备下，不同机体的战斗风格截然不同。

3. **木桩模拟器的数值验证工具化**
   - **逻辑变化**：将 `sim/sim_challenge_boss.py` 从简单的 Boss 挑战工具重构为完整的数值验证系统。新增 `BattleStatsCollector` 数据类，收集回合数分布、判定结果分布、伤害分布、精神指令使用频率等 8 项统计数据。
   - **设计思路**：模拟器不同于测试——测试验证"代码是否正确"，模拟器探索"数值是否合理"。通过 10+ 轮自动模拟，统计以下关键指标：
     - **平均战斗时长**：验证 Boss HP 与玩家 DPS 的平衡性（预期 20-30 回合结束）
     - **判定结果分布**：验证圆桌判定的概率是否预期（如暴击率应该接近 20%）
     - **精神指令使用率**：分析哪些指令被高频使用，是否存在"最优解"滥用
   - **配置集中化**：将 Boss 和挑战者的参数集中在文件顶部的配置字典中，方便数值策划快速调整（如将 Boss HP 从 500000 改为 1000000）而无需深入代码。

4. **测试覆盖率的深度补全**
   - **逻辑变化**：在 `tests/test_integration_complex.py` 中新增 5 个覆盖率测试，覆盖 `engine.py` 中之前未测试的代码路径：
     - `test_initiative_forced_switch`：测试连续获胜达到阈值后的强制换手机制（Consecutive Wins Threshold）
     - `test_initiative_hook_forces_first_attacker`：测试钩子干预先手判定的边缘场景
     - `test_determine_initiative_reason_will_diff`：测试气力差异 ≥ 20 时的先手原因判定
     - `test_weapon_selector_filters_out_of_range`：测试武器选择过滤超出射程的逻辑
     - 多个武器优先级和可用性测试
   - **设计思路**：通过 `pytest-cov` 工具发现覆盖盲区，然后针对性补全。先手判定、武器选择是战斗系统的核心入口，必须 100% 覆盖。同时，这些测试也验证了钩子系统是否真正生效（如"梦境"能否强制先手）。

5. **测试代码的现代化适配**
   - **逻辑变化**：
     - `tests/test_loader.py`：适配 Pydantic v2 的字段结构（`stats.shooting` → `stat_shooting`），从 433 行精简到更清晰的测试数据结构。
     - `tests/test_resolver_coverage.py`：标注了 TODO，标记熟练度相关测试为待完善，确保熟练度计算在圆桌判定中正确生效。
   - **设计思路**：测试代码与业务代码同步重构。当模型字段变更时，测试数据必须立即适配，否则测试会变成"虚假的通过"（在测试旧逻辑）。同时，明确标注哪些功能已废弃或待实现，避免后续维护者困惑。

6. **文档的同步更新**
   - **逻辑变化**：`doc/2.skill_system_design.md` 和 `doc/4.stat_equip_design.md` 有小幅更新，补充了新增精神指令和特性的说明。
   - **设计思路**：代码变更必须同步到设计文档，否则文档会变成"历史遗迹"。特别是技能系统设计文档，是 AI 和人类开发者理解技能配置的权威参考，必须保持最新。

**技术要点**
- 回调函数通过 `@SkillRegistry.register_callback` 装饰器注册，支持任意复杂的逻辑（如状态查询、概率判定、资源修改）
- 精神指令的 JSON 配置支持优先级（priority）和持续时间（duration），实现了"临时爆发"与"持续生效"的区分
- 统计分析使用 `collections.Counter` 和 `defaultdict` 高效收集战斗数据，避免手动维护复杂的统计变量
- 测试覆盖率通过 `pytest-cov --cov=src/combat/engine --cov-report=term-missing` 生成缺失行报告

**后续计划**
1. 在战斗系统中正确使用 `calculator.py` 中的熟练度计算函数（`calculate_proficiency_miss_penalty`、`calculate_proficiency_defense_ratio`）
2. 编写更多技能组合的集成测试（如"热血 + 气魄 + 看破"的极限伤害场景）
3. 将木桩模拟器的统计结果导出为 CSV/JSON，支持数值策划的批量分析

---

## 2025-02-10 测试框架现代化：从 unittest 迁移到 pytest

> **项目快照**：代码文件 13 个（2607 行）| 设计文档 4 个（1670 行）

### 逻辑变化与核心思路

1. **测试基础设施的全面重构**
   - **逻辑变化**：从标准库的 unittest 迁移到 pytest 框架，删除了8个旧的 unittest 测试文件，新增了11个 pytest 测试文件（共5475行）。新增 `pytest.ini` 配置文件和 722 行的 `conftest.py` 共享配置。
   - **设计思路**：unittest 在实际使用中暴露了三个核心痛点：（1）测试数据重复编写，每个测试都要手动创建 `Mecha`、`Pilot` 等对象；（2）随机数（RNG）难以控制，导致测试结果不稳定；（3）缺少测试标记，无法针对性地运行某类测试。pytest 的 fixture 机制和参数化测试能力更契合回合制游戏的测试需求。

2. **测试数据的标准化复用（Fixture体系）**
   - **逻辑变化**：在 `conftest.py` 中定义了大量可复用的 Fixtures，覆盖了游戏中的各种场景：
     - 基础对象：`basic_pilot`、`basic_mecha`、`basic_weapon`
     - 特殊机体：`low_hp_mecha`（30% HP，测试底力技能）、`high_will_mecha`（气力150，测试大招）、`high_hit_mecha`（命中率80%）、`high_dodge_mecha`（躲闪率50%）
     - 边界条件：`zero_hp_mecha`、`zero_en_mecha`、`max_will_mecha`
     - 效果对象：`effect_add_hit`、`effect_mul_damage`、`effect_set_hit`、`effect_conditional_low_hp` 等
     - 完整机体：`gundam_rx78`（带王牌驾驶员和完整武器配置）、`zaku_ii`（平衡型机体）
   - **设计思路**：建立测试数据标准库，避免每个测试都瞎编数据。通过 Fixture 的依赖注入机制（如 `basic_mecha(basic_pilot)`），实现测试数据的组合和复用。例如 `low_hp_mecha` 可以直接继承 `basic_pilot`，无需重复定义驾驶员属性。

3. **随机数的严格 Mock 机制**
   - **逻辑变化**：所有涉及随机性的测试都使用 `@patch('random.uniform', return_value=0.5)` 强制固定随机结果。例如 `test_miss_result` 中，通过 `mock_uniform.return_value = 0.5` 确保攻击落在 Miss 区间。
   - **设计思路**：回合制游戏充满随机（命中率80%、暴击率25%），测试不能随机。必须 Mock 掉所有 RNG，确保测试结果100%可复现。这样当测试 Fail 时，我们能确定是代码逻辑出错了，而不是运气不好。这是 CI/CD 自动化的前提条件。

4. **测试分层的清晰化**
   - **逻辑变化**：测试文件按职责划分为：
     - `test_unit_models.py`：数据结构单元测试（Pilot、Mecha、Weapon 的字段验证）
     - `test_combat_resolver.py`：圆桌判定逻辑测试（Miss/Dodge/Parry/Block/Crit/Hit 六种结果）
     - `test_resolver_coverage.py`：熟练度/地形/武器类型覆盖测试
     - `test_side_effects.py`：副作用测试（HP/EN/Will 变化）
     - `test_complex_scenarios.py`：复杂场景集成测试（RX-78 vs 扎古，多回合完整战斗）
     - `test_integration_complex.py`：多技能组合测试
   - **设计思路**：不追求100%覆盖率，只测核心的战斗逻辑和技能数值。UI显示、配置加载、日志记录等辅助功能完全不用测，避免过度设计。测试是为了保证"改动代码时游戏别崩"，而不是为了刷覆盖率。

5. **自动化清理与隔离性保障**
   - **逻辑变化**：在 `conftest.py` 中定义了 `@pytest.fixture(autouse=True)` 的 `reset_skill_registry()`，在每个测试结束后自动清理 `SkillRegistry._hooks` 和 `SkillRegistry._callbacks`。
   - **设计思路**：防止测试之间的相互污染。例如测试A注册了一个"底力"技能的回调，如果测试B执行时没有清理，可能会意外触发测试A的回调，导致测试B失败。自动清理机制确保每个测试都在干净的环境中运行。

6. **新增 pytest_framework_plan.md 测试指南**
   - **逻辑变化**：新增测试指南文档（4154字节），定义了测试的目录结构、命名规范、核心策略。
   - **设计思路**：为 AI 和人类开发者提供统一的测试编写规范。核心原则是"不做过度设计"，强调三个关键点：
     - 必须 Mock 随机性（RNG）
     - 复用 Fixtures，禁止硬编码测试数据
     - 关注"数值变化"和"状态流转"，而非代码语法
   - 提供了测试分层路线图：阶段一（核心算子：伤害公式、命中公式）→阶段二（技能效果：几百个技能的生效验证）→阶段三（游戏循环：完整回合的集成测试）

7. **新增 sim/ 模拟器目录**
   - **逻辑变化**：新增 `sim_attack_table.py`（14615字节）和 `sim_challenge_boss.py`（9723字节）。
   - **设计思路**：模拟器与测试不同，测试是为了验证正确性，模拟器是为了探索数值分布。`sim_attack_table.py` 运行 5000+ 次迭代统计，验证攻击判定表在不同数值分布下的表现是否符合概率预期（标准场景、高命中、高闪避、极端压制）。这是数值策划的工具，不属于自动化测试范畴。

8. **测试标记系统与分组执行**
   - **逻辑变化**：在 `pytest.ini` 中定义了测试标记（unit、integration、combat、skill、stress、slow），支持通过 `pytest -m combat` 只运行战斗相关测试。
   - **设计思路**：提高开发效率。在开发战斗系统时，只运行 combat 标记的测试，避免被集成测试拖慢速度。在提交前运行完整测试套件，确保没有破坏现有功能。

**技术要点**
- pytest 的 fixture 机制比 unittest 的 setUp/tearDown 更灵活，支持依赖注入和作用域控制
- 使用 `@pytest.mark.parametrize` 支持参数化测试，例如一次性测试所有地形的修正效果
- 通过 `autouse=True` 实现自动清理，无需在每个测试中手动调用 tearDown
- 测试命名更加清晰：`test_<行为>_<预期结果>`（如 `test_attack_hit_should_reduce_hp`），通过命名就能理解测试意图

**后续计划**
根据 `pytest_framework_plan.md` 的路线图：
1. 阶段一：核心算子测试（伤害公式、命中公式、距离修正）
2. 阶段二：技能效果测试（几百个技能的生效验证，如"底力L9且HP<10%时防御力x1.5"）
3. 阶段三：游戏循环测试（完整回合的集成测试，验证双方最终HP/EN变化）

---

## 2026-02-10 技能系统全面落成与数据驱动重构

> **项目快照**：代码文件 24 个（3847 行）| 设计文档 5 个（1335 行）

### 逻辑变化与核心思路

1. **技能系统全链路实现与极端压力验证**
   - **逻辑变化**：完成了 `EffectProcessor`（优先级流水线）、`ConditionChecker`（上下文感知逻辑）、`SideEffectExecutor`（链式副作用）和 `EffectFactory`（数据驱动工厂）的闭环实现。
   - **设计思路**：通过一个包含 8 个并发异构技能（包括"不屈"、"预判"、"热血"、"节能"等）的极端压力测试，验证了系统对优先级冲突、跨阶段 Hook 引用及生命周期管理的支撑能力。系统成功从"能够运行"进化为"工业级鲁棒"。
   - **Bug 修复**：在自残测试场景中发现了效果重复收集的隔离性问题。通过在收集阶段引入 `id()` 过滤机制，确保了同一机体在同一 Hook 计算中无论扮演何种角色，其产生的 Effects 只会被计算一次，保证了幂等性。

2. **从硬编码向 JSON 数据驱动转型**
   - **逻辑变化**：彻底重构 `EffectFactory`，使其支持从 `data/skills.json` 动态加载数据。`TraitManager` 也不再包含具体数值，而是作为从 JSON 数据到 Effect 实例的桥梁。
   - **设计思路**：实现了游戏平衡与逻辑引擎的彻底解耦。数值策划现在可以通过修改 JSON 配置文件直接添加新技能、调整倍率或修改触发条件（如将"底力"的 HP 阈值从 0.3 改为 0.5），而无需触碰任何 Python 核心代码。

3. **战斗流程控制权的"Hook 化"**
   - **逻辑变化**：在 `engine.py` 中引入了 `HOOK_MAX_ROUNDS` 和 `HOOK_CHECK_MAINTAIN_BATTLE`，并在 `_execute_attack` 中集成了 `HOOK_PRE_EN_COST_MULT`。
   - **设计思路**：将战斗的"生死大权"也交给技能系统。这使得实现"死斗"（不限回合）、"剧情强制脱离"或"节能型机体特性"变得极其简单，只需挂载相应的 Hook 即可，无需在 Engine 类中编写冗长的 `if-else`。

4. **圆桌判定算法的精确化重构**
   - **逻辑变化**：将 `AttackTableResolver` 中的随机数从 `randint` 升级为 `uniform(0, 100)`，并重写了判定切片（Slices）逻辑。
   - **设计思路**：解决了整数随机带来的"101个整数导致的1%偏移"问题。新的"绝对宽度切片"算法不再依赖剩余百分比缩放，而是基于绝对数值宽度进行区间划分。这使得"必中"、"分身"等边界技能在面对高精准、高暴击时表现得更加符合概率预期，计算逻辑也更直观。

5. **动态逻辑的回调扩展 (Callback System)**
   - **逻辑变化**：实现了 `operation="callback"` 机制，并通过装饰器注册了"底力"、"学习电脑"和"GN炉"等复杂逻辑函数。
   - **设计思路**：虽然 JSON 能够覆盖 90% 的数值修正，但总有 10% 的奇葩技能（如按比例回能、指数级属性成长）需要代码介入。回调系统作为"逃生门"，确保了系统在保持数据驱动的同时，不丧失处理极端复杂机制的灵活性。

---

## 2026-02-09 技能系统架构设计与文字演出精简

> **项目快照**：代码文件 12 个（1887 行）| 设计文档 3 个（2312 行）

### 逻辑变化与核心思路

1. **技能系统的完整设计蓝图**
   - **逻辑变化**：新增 [skill_system_design.md](doc/skill_system_design.md)（766行），定义了基于 Pipeline 架构的完整技能系统。设计了 30 个钩子点，覆盖从先手判定到伤害结算的全流程。
   - **设计思路**：贯彻"逻辑与数值分离"的核心理念。战斗主循环只负责流程控制和"埋点"（Hooks），所有的数值修正、机制判定均通过技能效果（Effects）挂载到钩子点上实现。这四大类技能效果：临时增加数值、概率增加数值、临时确定判定、概率确定判定，覆盖了从"集中"（永久加成）到"分身"（概率触发）的所有经典机战技能需求。
   - **关键创新**：跨钩子点引用机制——允许技能引用其他钩子点的计算结果。例如"见切"可以引用对方的命中率（来自 `HOOK_PRE_HIT_RATE`），在对方命中率低于30%时才触发招架率加成。通过 `cached_results` 缓存 + 递归死锁防护解决了循环依赖问题。

2. **状态生命周期管理体系**
   - **逻辑变化**：设计了四种状态生命周期（ATTACK_BASED / TURN_BASED / BATTLE_BASED / GLOBAL），明确了何时清理临时状态。
   - **设计思路**：解决"精神指令何时失效"的棘手问题。例如"热血"是仅限本次攻击有效（ATTACK_BASED），"集中"是持续1回合（TURN_BASED），而"学习电脑层数"则是整场战斗有效（BATTLE_BASED）。通过在特定钩子点（如 `HOOK_ON_ATTACK_END`）触发清理，实现了精确的状态管理，避免内存泄漏和逻辑错误。

3. **文字演出的精简优化**
   - **逻辑变化**：简化了 [combat_presentation.md](doc/combat_presentation.md) 中的环境描述模板，去除冗余的修饰词（如"猛然开启"、"深深的"），使文本更直接有力。
   - **设计思路**：之前的模板过于华丽，导致单回合文本过长（约150字），影响阅读节奏。优化后的模板控制在80-100字内，保留核心信息（距离、先手原因、武器效果），去除多余的形容词堆砌。例如将"米诺夫斯基粒子在5200m外形成淡淡的干扰波纹"简化为"凭借卓越的机体性能在5200m处率先完成瞄准"——省去物理设定，聚焦战术动作本身。

---

## 2026-02-09 战斗叙事与术语体系完善

> **项目快照**：代码文件 12 个（2045 行）| 设计文档 2 个（781 行）

### 逻辑变化与核心思路

1. **战斗核心概念重构：从"优势值"到"气力系统"**
   - **逻辑变化**：将原本模糊的"优势值"概念替换为更具体的"气力"系统，这个改动贯穿整个战斗设计。
   - **设计思路**："气力"作为驾驶员战意与机体性能发挥的结合点，不仅在数值上影响伤害/防御修正，还直接决定先攻权判定。相比抽象的"优势"，气力能通过攻击命中、招架、格挡等具体动作实时增减，让战意积累的过程可视化、可预测。

2. **资源限制机制的引入：EN消耗与战术脱离**
   - **逻辑变化**：新增EN检查环节，在攻击判定前先确认"当前EN >= 武器消耗"，不满足则无法攻击。同时新增"战术脱离"结局——EN不足但成功防御可强制中止战斗。
   - **设计思路**：这是对传统机战游戏的致敬。武器不再是无限使用的，玩家必须管理机体能量。更关键的是，"战术脱离"给劣势方留出了体面退出的通道——即使打不过，通过精明的防御也能保住机体撤退，这比单纯的"战败"更有策略深度。

3. **圆桌判定系统的气力反馈闭环**
   - **逻辑变化**：防御类判定（躲闪/招架/格挡）现在会为防御方提供气力奖励（躲闪+5、招架+15、格挡+5），而不仅仅是"未受伤"。
   - **设计思路**：建立"防御得利"的反馈循环。弱势方即使无法反击，通过连续招架/格挡也能快速积累气力，在后续回合通过高气力反超先攻权，实现"以守为攻"的战术路线。

4. **叙事视角的动态切换机制**
   - **逻辑变化**：文字演出不再是固定的"攻击方视角"，而是根据圆桌判定结果动态选择——命中类（Miss/Hit/Crit）从攻击方描述武器威力，防御类（Dodge/Parry/Block）从防御方描述机体机动性。
   - **设计思路**：这样能最大化每个回合的信息密度。当判定为"招架"时，读者更想看到的是"防御方如何巧妙化解攻击"，而不是"攻击方打空了"。视角切换让每种判定结果都有其独特的叙事张力。

5. **术语风格的统一化与沉浸感提升**
   - **逻辑变化**：新增完整的"属性展示名称映射表"，将所有内部代码（hp、en、will等）映射为机器人动画风格的术语（机体耐久、能量出力、气力），并标注术语来源（高达UC、Franxx、机动警察等）。
   - **设计思路**：前端显示的"能量出力：45/80"比"EN：45/80"更有代入感。更关键的是，统一术语风格能让玩家快速建立认知框架——看到"NT等级"就知道是新人类相关，看到"I力场格挡"就能联想到高达的技术设定。这种细节打磨在长期游玩中会形成强烈的世界观沉浸感。

---

## 2026-02-09 战斗系统底层架构重构

> **项目快照**：代码文件 12 个（1769 行）| 设计文档 2 个（781 行）

### 逻辑变化与核心思路

1. **架构进化：从"静态属性修正"转向"流水线钩子系统"**
   - **逻辑变化**：重构了战斗计算流程。不再在初始化时将加成固定在属性上，而是引入了 `SkillRegistry` 钩子系统。命中判定、伤害计算、减伤判定等每一个核心数值环节都变成了可干预的"管道"。
   - **设计思路**：为了后续支持无限扩展的技能（如 SRW 中的"必中"、"热血"、"底力"等），必须让战斗引擎与具体的技能逻辑解耦。现在引擎不再关心有哪些技能，只需在计算时向注册表"询问"是否存在修改者。

2. **状态系统的生命周期化 (Effect & Tick Mechanism)**
   - **逻辑变化**：引入了 `EffectManager` 和有时效性的 `Effect` 模型。精神指令（Spirit Commands）现在作为带持续回合的状态存在，并在回合结束时通过 `tick_effects` 自动衰减。
   - **设计思路**：为了精确复刻机战中"仅限本回合有效"或"仅限下次攻击有效"的策略感。将"临时状态"从"机体基础性能"中彻底分离。

3. **机体特性的标准化注入 (TraitManager)**
   - **逻辑变化**：新增 `TraitManager`，专门负责机体固有特性（如"学习型计算机"、"强化装甲"）的统一点火。
   - **设计思路**：建立清晰的属性修正层级：机体基础值 -> 固有特性修正 -> 战场临时状态加成。这为未来的"二周目继承"或"机体改造"预留了干净的接口。

4. **战场上下文 (BattleContext) 的角色升级**
   - **逻辑变化**：`BattleContext` 增加了对地形（Terrain）和事件标记（Event Flags）的支持，并成为所有钩子函数的必传参数。
   - **设计思路**：逻辑不再是孤岛。通过上下文，技能可以感知当前是"我方回合"还是"敌方反击"，以及当前处于"宇宙"还是"基地"，从而实现复杂的地形相关技能或反击专用技能。

---

## 项目起始阶段小结 (2026-01-XX 至 2026-02-07)

> **项目快照**（2026-02-07 纯设计阶段）：代码文件 0 个（0 行）| 设计文档 2 个（54 行）

### 设计定型：核心战斗框架与叙事体系的建立

在2月8日进入代码实现阶段之前，项目经历了完整的设计定型期。这一阶段的核心成果是将抽象的机器人战斗概念转化为可落地的设计规范。

#### 1. 战斗核心机制的设计确立

**圆桌判定系统的提出**
- 从传统RPG的"命中/未命中"二元判定，转向更复杂的"单一随机数圆桌系统"。将Miss（12%）、Dodge（22%）、Parry（15%）、Block（20%）、Crit（25%）、Hit（剩余）按照优先级排列，让每个判定结果都有其战术价值。
- 设计思路：避免"概率堆砌"的数值膨胀，通过"精准"属性削减敌方防御区间，建立攻击与防御的博弈空间。

**动态距离机制的引入**
- 打破传统回合制战斗的"立桩对射"，设计了从3000-7000m开始、每回合缩进1500m的动态距离系统。强制玩家同时装备格斗、射击、狙击三类武器。
- 设计思路：体现真实系机器人的战场感，距离不再是一个静态标签，而是每回合随机抽取的具体数值，带来武器可用性的不确定性。

**优势值（后改为气力）系统的概念化**
- 最初提出"优势值"作为核心资源，通过攻击命中、招架格挡等动作积累，影响先攻权判定。防御方可以通过完美防守获得大量优势，实现"以守为攻"的反超路线。
- 设计思路：建立动态平衡机制，防止强势方无脑滚雪球，给弱势方留出翻盘通道。

#### 2. 叙事视角的结构化

**标准四段式演出模板**
- 提出战场环境、先手攻击、后手反击、回合总结的四段式结构，单回合字数控制在100-150字。
- 关键创新：根据圆桌判定结果动态切换叙事视角——命中类从攻击方描述武器威力，防御类从防御方描述机体机动性。最大化每回合的信息密度。

**示例驱动的文档风格**
- 通过完整的4回合战斗示例（高达VS扎古），展示从雷达接触到最终决战的全过程。让开发者能直观理解"初动-接敌-死斗-决战"的节奏变化。

#### 3. 从设计到实现的准备

这一阶段虽然没有代码，但设计文档已经明确规定了：
- 数据模型所需的字段（机体、驾驶员、武器三大类属性）
- 圆桌判定的优先级公式
- 先手权的分层判定逻辑（绝对优先权→综合优势判定）
- 文本演出的API接口格式（Environment、Action、Summary三类模板）

这些设计规范直接指导了后续的代码架构（如SkillRegistry钩子系统、BattleContext上下文对象）的设计方向。

#### 4. 设计文档的演进

从git历史可以看到，设计文档经历了三轮迭代：
- f31e6c1（战斗文档设定更新）：初步建立战斗框架
- d7f33fe（优化战斗设计和文字演出细节）：完善圆桌判定和距离机制
- afc57f2（进一步优化文字演出设计）：定型四段式叙事和视角切换逻辑

每一次迭代都在细节上打磨，为2月9日的代码实现阶段扫清了概念障碍。

---
