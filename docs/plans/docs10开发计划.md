# PVE 讨伐战系统 — 代码实现规划

## 0. 背景与现状差距分析

### 文档 10 要求的三级架构 vs 现有代码实现

| 层级 | 文档要求 | 现有代码状态 | 差距 |
|:---|:---|:---|:---|
| **L1 战略层** (Region) | 大区域准入校验、进度解锁 | `RegionConfig` 模型存在但仅有 3 字段；无 `user_pve_progress` 表 | 🔴 缺 DB 进度表、缺准入拦截 |
| **L2 战术层** (Zone) | 子区域解锁链、隐藏节点概率刷新 | **完全缺失** — 没有 Zone 概念 | 🔴 从零开始 |
| **L3 执行层** (Sequence) | 事件序列生成与推进 | ✅ 已有基础实现 | 🟡 需补全幂等校验、脱敏逻辑 |
| 三层快照 | Layer 1/2/3 完整数据流 | ✅ 已有基础实现 | 🟡 恢复计算通路可用，需整理 |
| 收益结算 | 幂等防重、临时背包、税率折损 | ✅ 已有基础实现 | 🟢 基本完整 |
| 断线即失败 | 心跳监控、内存销毁 | ⚠️ `last_heartbeat` 字段存在但无监控逻辑 | 🔴 无心跳守护 |
| 幂等推进 | `expected_index` 版本号校验 | ⚠️ `/advance` 无校验 | 🔴 核心安全缺陷 |

### 现有代码的遗留问题

1. [pve_tiles.json](file:///Users/dupidupi/ebsp/data/pve_tiles.json) — 旧 Tile 地图数据残留，应删除
2. [services.py](file:///Users/dupidupi/ebsp/src/pve/services.py) 中的 `get_max_movement_points()` — 旧地图 API 残留
3. [regions.json](file:///Users/dupidupi/ebsp/data/regions.json) — 仅定义了 Region 层，缺少 Zone 嵌套配置
4. [session_manager.py](file:///Users/dupidupi/ebsp/src/pve/session_manager.py) — 类变量 `_sessions` 做全局内存池不够健壮，且无并发保护

---

## 1. 实施策略总纲

### 方法论：由内向外、逐层补全

```
Phase 1: 数据层 — 配置重构 + DB 表
Phase 2: L1 战略层 — 区域准入
Phase 3: L2 战术层 — 子区域解锁链
Phase 4: L3 执行层加固 — 幂等 + 脱敏
Phase 5: 基础设施 — 心跳守护 + 清理遗留
```

设计原则（来自 Doc 0）：
- **Pydantic v2** 做数据验证，**SQLAlchemy 2.0 异步**做持久化
- 战斗层只消费快照，不感知 PVE 上下文
- 静态配置 JSON + 用户进度 DB + 运行时内存 的三层分离

---

## 2. Phase 1: 数据层重构

### 目标
将 `regions.json` 从平铺区域列表重构为「Region → Zone」二级嵌套结构，并新建 `user_pve_progress` DB 表。

### 2.1 配置文件重构：`data/regions.json`

**做什么**：将现有扁平结构改为文档 10 第 3.3 节要求的嵌套结构。

**为什么**：当前 `regions.json` 只有 Region 级别信息（id/name/min_region_level/base_ilvl），没有 Zone（子区域）定义。文档要求每个 Zone 拥有独立的事件权重、怪物池、Boss 模板，且 Zone 之间存在前置解锁链。

**关键设计决策**：
- Zone 作为 Region 的子文档嵌套，而非独立文件 — 因为 Zone 的怪物池/权重在不同 Region 间大量变化，聚合在一起便于大区域级别管控
- `unlock_requires: null` 表示首发节点（无前置），一个 Region 至少一个首发 Zone

**目标数据结构示例**：
```json
{
  "id": "abandoned_station",
  "name": "废弃空间站",
  "min_region_level": 1,
  "base_ilvl": 10,
  "zones": [
    {
      "zone_id": "dock",
      "name": "空间站码头",
      "unlock_requires": null,
      "event_count_range": [8, 10],
      "event_weights": { "COMBAT": 45, "ELITE_COMBAT": 10, "LOOT": 25, "EVENT": 20 },
      "normal_pool": ["zaku2", "gouf"],
      "elite_pool": ["dom", "gelgoog"],
      "boss_template": "zeong",
      "is_hidden": false
    },
    {
      "zone_id": "command_post",
      "name": "空间站指挥所",
      "unlock_requires": "dock",
      "event_count_range": [9, 12],
      "event_weights": { "COMBAT": 40, "ELITE_COMBAT": 20, "LOOT": 20, "EVENT": 20 },
      "normal_pool": ["gelgoog", "rick_dom"],
      "elite_pool": ["kampfer", "char_zaku"],
      "boss_template": "big_zam",
      "is_hidden": false
    },
    {
      "zone_id": "warehouse",
      "name": "空间站仓库",
      "unlock_requires": "dock",
      "spawn_chance": 0.15,
      "event_count_range": [5, 7],
      "event_weights": { "COMBAT": 15, "LOOT": 60, "EVENT": 25 },
      "normal_pool": ["worker_zaku"],
      "elite_pool": [],
      "boss_template": null,
      "is_hidden": true
    }
  ]
}
```

### 2.2 Pydantic 配置模型补全

**做什么**：在 [src/models.py](file:///Users/dupidupi/ebsp/src/models.py) 中新增 `ZoneConfig` 模型，修改 `RegionConfig` 使其包含 `zones` 列表。

**方法**：
```python
class ZoneConfig(BaseModel):
    """L2 子区域静态配置"""
    zone_id: str
    name: str
    unlock_requires: Optional[str] = None  # 前置 zone_id，null 为首发
    event_count_range: tuple[int, int] = (8, 12)
    event_weights: Dict[str, int] = {}
    normal_pool: List[str] = []
    elite_pool: List[str] = []
    boss_template: Optional[str] = None
    is_hidden: bool = False
    spawn_chance: Optional[float] = None  # 仅隐藏节点

class RegionConfig(BaseModel):
    """L1 大区域配置 — 增加 zones 子项"""
    id: str
    name: str
    min_region_level: int
    base_ilvl: int
    description: str = ""
    zones: List[ZoneConfig] = []       # 新增
```

### 2.3 新增 `UserPveProgress` DB 表

**做什么**：在 [src/database/models.py](file:///Users/dupidupi/ebsp/src/database/models.py) 中新增用户 PVE 进度表。

**为什么**：文档要求 `user_pve_progress` 记录每个大区域下各节点的 cleared/locked/hidden_available 状态，并且隐藏节点的刷新结果需持久化防刷。

**设计决策**：
- 采用 **JSONB** 存储进度字典（与 Doc 7 混合架构一致）
- 每用户一行，`progress_data` 字段按 Region → Zone 嵌套记录

**模型草案**：
```python
class UserPveProgress(Base, TimestampMixin):
    """用户 PVE 探索进度表"""
    __tablename__ = "user_pve_progress"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), unique=True, index=True
    )
    # 结构: {"abandoned_station": {"dock": "cleared", "command_post": "locked", ...}}
    progress_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    # 隐藏节点当日刷新记录 (防止退出重进刷隐藏)
    hidden_refresh_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
```

### 2.4 DataLoader 改造

**做什么**：修改 [src/loader.py](file:///Users/dupidupi/ebsp/src/loader.py) 的 `get_region_config()` 方法，使其返回包含 zones 的完整 `RegionConfig`。新增 `get_zone_config(region_id, zone_id)` 便利方法。

---

## 3. Phase 2: L1 战略层 — 区域准入与进度

### 目标
实装大区域准入校验和进度记录。

### 3.1 PveProgressService（新建）

**做什么**：新建 `src/pve/progress_service.py`，封装进度查询/写入逻辑。

**核心方法**：
| 方法 | 职责 |
|:---|:---|
| `get_region_status(user_id, region_id)` | 返回该大区域下所有 Zone 的解锁状态 |
| `unlock_zone(user_id, region_id, zone_id)` | 将指定 Zone 标记为已解锁 |
| `mark_zone_cleared(user_id, region_id, zone_id)` | 通关后标记 cleared + 触发后续 Zone 解锁链 |
| `roll_hidden_zone(user_id, region_id)` | 概率刷新隐藏节点并持久化结果 |
| `initialize_progress(user_id, region_id)` | 首次进入大区域时初始化进度（开放首发节点） |

**设计要点**：
- 解锁链通过配置中的 `unlock_requires` 驱动，`mark_zone_cleared` 完成后自动遍历所有子 Zone，将 `unlock_requires == 当前 zone_id` 的节点标记为 unlocked
- 隐藏节点刷新结果写入 `hidden_refresh_data`，按日期 key 存储，防止退出重进反复刷新

### 3.2 修改 PveEntryService

**做什么**：在 [services.py](file:///Users/dupidupi/ebsp/src/pve/services.py) 的 `PveEntryService.enter_region()` 流程开头插入准入校验。

**校验逻辑**：
```
1. 检查母舰 region_level ≥ RegionConfig.min_region_level （已有）
2. 检查 user_pve_progress 中该 region 是否已初始化 （新增）
3. 若未初始化 → 调用 initialize_progress() 建立首发节点 （新增）
```

### 3.3 新增 Zone 选择 API

**做什么**：在 `/pve/enter-region` 流程与 L3 序列生成之间插入 Zone 选择步骤。

**方案**：
- 新增端点 `GET /pve/regions/{region_id}/zones` — 返回该区域所有 Zone 的解锁状态供前端展示战术地图
- 修改 `POST /pve/enter-region` — 请求体新增 `zone_id` 字段，服务端校验该 Zone 已解锁后才生成事件序列

> [!IMPORTANT]
> 这意味着 `PveSessionData` 需要新增一个 `zone_id` 字段来记录当前进行的子区域节点。

---

## 4. Phase 3: L2 战术层 — 子区域解锁链

### 目标
实装文档 3.1-3.2 节的线性梯次解锁和概率隐藏节点。

### 4.1 通关后的解锁链触发

**做什么**：在结算成功路径（Boss Clear）中调用 `PveProgressService.mark_zone_cleared()`。

**触发点**：在 [reward_controller.py](file:///Users/dupidupi/ebsp/src/pve/reward_controller.py) 的 `finalize()` 方法中，当 `exit_method == BOSS_CLEAR` 时，在入库后追加进度更新逻辑。

**流程**：
```
Boss Clear → finalize() 入库 
  → mark_zone_cleared(user_id, region_id, zone_id)
    → 自动遍历 RegionConfig.zones
    → unlock_requires == zone_id 的节点 → 标记 unlocked
  → 返回解锁的新节点列表给前端展示「新区域开放」
```

### 4.2 隐藏节点方案

**做什么**：实装 Zone 列表查询时的概率刷新。

**方法**：
- 在 `GET /pve/regions/{region_id}/zones` API 处理中，遍历 `is_hidden=True` 的 Zone
- 检查 `hidden_refresh_data[today_key]` 是否已有该 Zone 的刷新结果
  - 有 → 直接用缓存结果
  - 无 → 按 `spawn_chance` 骰一次，结果写入 DB 持久化
- 若刷新命中 → 在返回列表中标记该隐藏 Zone 为 `available`

**设计决策**：隐藏节点的刷新颗粒度为「每日每 Region 一次」，重启服务不影响当日已刷新的结果。

---

## 5. Phase 4: L3 执行层安全加固

### 目标
补全文档 4.4 节要求的幂等校验和数据脱敏。

### 5.1 幂等推进 — `expected_index` 版本号

**做什么**：修改 [schemas.py](file:///Users/dupidupi/ebsp/src/pve/schemas.py) 的 `AdvanceRequest` 和 [pve_api.py](file:///Users/dupidupi/ebsp/src/api/pve_api.py) 的 `/advance` 端点。

**方法**：
```python
class AdvanceRequest(BaseModel):
    expected_index: int  # 客户端认为的当前索引，必须与服务端一致

# API 端点中:
if req.expected_index != session.event_sequence.current_index:
    # 重试或过期请求 → 拦截并返回当前同步状态
    return AdvanceResponse(
        new_event_index=session.event_sequence.current_index,
        current_event=current_event_info,
        sequence_complete=session.event_sequence.is_complete(),
        sync_correction=True  # 告知前端发生了同步修正
    )
```

同理，`EngageRequest` 的 `event_index` 校验已有但需加强 — 不仅检查范围，还要确保 `event_index == current_index`。

### 5.2 数据脱敏 — 单步暴露

**做什么**：修改 `PveSessionResponse` 的 `sequence` 返回逻辑，改为仅暴露当前事件和已完成事件。

**当前问题**：[schemas.py](file:///Users/dupidupi/ebsp/src/pve/schemas.py) 的 `PveEventSequenceResponse` 返回了全量 `events` 列表，玩家抓包即可看到后续所有事件类型。

**方法**：
```python
class PveEventSequenceResponse(BaseModel):
    total_events: int
    current_index: int
    visible_events: List[EventInfo]  # 仅包含 index <= current_index 的事件

# 构建时过滤:
visible = [e for e in events if e.index <= current_index]
```

### 5.3 战斗接战的 `/engage` 加固

**做什么**：
1. 校验 `event_index == current_index`（防止跳格攻击）
2. 校验当前事件类型为战斗类（COMBAT/ELITE/BOSS），非战斗事件不允许 engage
3. 校验当前事件未 cleared（防止重复打同一格）

---

## 6. Phase 5: 基础设施 — 心跳守护 + 清理

### 目标
实装「断线即失败」架构 + 清理遗留代码。

### 6.1 心跳守护机制

**做什么**：新建 `src/pve/heartbeat.py`，实现后台定时任务扫描过期会话。

**方法**：
```python
class HeartbeatGuard:
    TIMEOUT_SECONDS = 120  # 2 分钟无心跳即判定断线
    SCAN_INTERVAL = 30     # 每 30 秒扫描一次
    
    @classmethod
    async def scan_and_destroy(cls):
        """定时任务：扫描并销毁超时会话"""
        now = time.time()
        expired_ids = [
            sid for sid, session in PveSessionManager._sessions.items()
            if now - session.last_heartbeat > cls.TIMEOUT_SECONDS
        ]
        for sid in expired_ids:
            PveSessionManager.destroy_session(sid)
```

**集成方式**：
- 在 FastAPI `lifespan` 钩子中启动 `asyncio.create_task` 轮询
- 新增 `POST /pve/sessions/{session_id}/heartbeat` API，前端定期调用更新 `last_heartbeat`

### 6.2 SessionManager 加固

**做什么**：
1. 给 `_sessions` 加 `asyncio.Lock` 保护并发安全
2. 新增 `get_session_by_user(user_id)` 方法 — 防止同一用户创建多个活跃会话
3. 在 `create_session` 前检查是否已有活跃会话 → 有则拒绝

### 6.3 遗留清理

| 文件 | 操作 | 原因 |
|:---|:---|:---|
| `data/pve_tiles.json` | **删除** | 旧 Tile 地图系统残留 |
| `services.py` → `get_max_movement_points()` | **删除** | 旧地图步数计算 |
| `PveSessionData.current_layer` | **删除** | 旧多层副本概念，已被 Zone 替代 |
| `session_manager.py` — 类变量 `_next_id` | **改为 UUID** | 自增 int 在多进程下不安全 |

---

## 7. 文件变更汇总

### 新增文件
| 文件 | 职责 |
|:---|:---|
| `src/pve/progress_service.py` | L1/L2 进度查询、解锁链、隐藏节点管理 |
| `src/pve/heartbeat.py` | 心跳守护定时任务 |

### 修改文件
| 文件 | 变更内容 |
|:---|:---|
| `data/regions.json` | 重构为 Region → Zone 嵌套结构 |
| `src/models.py` | 新增 `ZoneConfig`，修改 `RegionConfig` |
| `src/database/models.py` | 新增 `UserPveProgress` 表 |
| `src/loader.py` | 新增 `get_zone_config()` |
| `src/pve/models.py` | `PveSessionData` 新增 `zone_id`，删除 `current_layer` |
| `src/pve/schemas.py` | `AdvanceRequest` 加 `expected_index`；脱敏响应 |
| `src/pve/services.py` | 删除 `get_max_movement_points()`；`enter_region` 增加准入校验 |
| `src/pve/session_manager.py` | 加锁、UUID、用户唯一会话约束 |
| `src/pve/event_generator.py` | `generate()` 接收 `ZoneConfig` 而非 `RegionConfig` |
| `src/pve/reward_controller.py` | Boss Clear 路径追加进度更新 |
| `src/api/pve_api.py` | 新增 Zone 列表 API、幂等校验、心跳 API |

### 删除文件
| 文件 | 原因 |
|:---|:---|
| `data/pve_tiles.json` | 旧 Tile 地图残留 |

---

## 8. 验证计划

### 自动化测试
- 扩展 [test_pve_core.py](file:///Users/dupidupi/ebsp/tests/test_pve_core.py) — 新增 Zone 解锁链单元测试
- 扩展 [test_pve_session_manager.py](file:///Users/dupidupi/ebsp/tests/test_pve_session_manager.py) — 并发保护、用户唯一会话
- 新增 `test_pve_progress.py` — 进度初始化、通关解锁、隐藏节点概率持久化
- 新增 `test_pve_idempotency.py` — `expected_index` 重试拦截测试
- 新增 `test_heartbeat.py` — 超时销毁测试

### 手动验证
- 通过 API 集成测试走通完整流程：进入区域 → 选择 Zone → 推进序列 → 战斗 → 通关解锁新 Zone
- 验证抓包无法看到后续事件类型（脱敏有效性）
- 模拟断线 2 分钟后确认会话被自动销毁

---

## 9. 开放问题

> [!IMPORTANT]
> **Zone 配置的怪物池引用**：当前 `mechas.json` 中只有 `rx78`/`zaku2` 等少量机体。Zone 配置中引用的 `gouf`、`dom`、`gelgoog` 等模板 ID 尚不存在。是否需要在此次实现中同步补充这些敌方机体配置？还是先在代码中做 fallback 处理（找不到配置就默认 `zaku2`）？

> [!IMPORTANT]
> **`user_pve_progress` 的隔离策略**：文档中提到隐藏节点的刷新在「本次会话期间强制持久化」。这里的「会话」指的是单次 PVE 探索会话（进入-退出节点期间），还是玩家的登录会话（一天内），还是自然日？这会影响 `hidden_refresh_data` 的 key 粒度设计。上方方案暂时使用「每日一次」。

> [!WARNING]
> **PveSession 的 session_id 类型变更**：当前 `session_id: int` 为自增整数，改为 UUID 会影响已有的全部测试和 API 签名。考虑是否在此次一并改造，还是先用 `int` 完成功能、后续再迁移？
