# 演出系统使用指南

## 概述

演出系统（Presentation System）是一个事件驱动的战斗叙事系统，负责将战斗引擎生成的原始数据转换为生动的文本描述和视觉演出信息。

## 系统架构

```
┌─────────────────┐
│ 战斗引擎        │ Logic Layer
│ (Combat Engine) │ - 生成原始事件
└────────┬────────┘
         │ RawAttackEvent
         ↓
┌─────────────────┐
│ 事件转换器      │ Mapping Layer
│ (EventMapper)   │ - 填充模板
└────────┬────────┘ - 映射资源
         │ PresentationAttackEvent
         ↓
┌─────────────────┐
│ 渲染器          │ Rendering Layer
│ (Renderer)      │ - 输出文本/JSON
└─────────────────┘
```

## 文件结构

```
src/presentation/
├── __init__.py      # 模块导出
├── models.py        # 数据模型定义
├── mapper.py        # 事件转换器
└── renderer.py      # 文本和JSON渲染器

config/
└── presentation.yaml  # 演出配置文件
```

## 使用方式

### 1. 在战斗引擎中启用演出系统

```python
from src.combat.engine import BattleSimulator

# 创建战斗模拟器并启用演出系统
sim = BattleSimulator(mecha_a, mecha_b, enable_presentation=True)

# 运行战斗（会自动生成演出文本）
sim.run_battle()
```

### 2. 手动使用事件转换器

```python
from src.presentation import EventMapper, TextRenderer
from src.presentation.models import RawAttackEvent

# 创建转换器
mapper = EventMapper()
renderer = TextRenderer()

# 创建原始事件
raw_event = RawAttackEvent(
    round_number=1,
    attacker_id="mecha_001",
    defender_id="mecha_002",
    attacker_name="RX-78-2 高达",
    defender_name="MS-06S 扎古",
    weapon_id="weapon_beam_saber",
    weapon_name="光束军刀",
    weapon_type="MELEE",
    attack_result="HIT",
    damage=1200,
    distance=800,
    attacker_will_delta=2,
    defender_will_delta=0,
    initiative_holder="mecha_001",
    initiative_reason="PERFORMANCE",
    triggered_skills=[],
    is_first_attack=True
)

# 转换为演出事件
pres_event = mapper.map_attack(raw_event)

# 渲染为文本
text = renderer.render_attack(pres_event)
print(text)
```

### 3. 生成JSON输出（用于前端）

```python
from src.presentation import JSONRenderer

# 创建JSON渲染器
json_renderer = JSONRenderer()

# 渲染为字典
data = json_renderer.render_attack(pres_event)

# 或渲染为JSON字符串
json_str = json_renderer.render_round_json(round_event)
```

## 配置文件说明

`config/presentation.yaml` 包含两个主要部分：

### 1. 文本模板 (templates)

定义了各种武器类型和攻击结果的文本模板：

```yaml
templates:
  attack:
    MELEE:
      HIT:
        - "{attacker} 的 {weapon} 精准刺向 {defender} 的 {location}。（命中！伤害 {damage}）"
      CRIT:
        - "要害暴击！{attacker} 的 {weapon} 以惊人的力量劈开 {defender} 的 {location}！（暴击！伤害 {damage}）"
```

可用的占位符：
- `{attacker}` - 攻击方名称
- `{defender}` - 防御方名称
- `{weapon}` - 武器名称
- `{damage}` - 伤害值
- `{location}` - 命中部位
- `{distance}` - 交战距离
- `{range_tag}` - 距离区间标签

### 2. 视觉映射 (mappings)

定义了动画、特效、音效的资源ID：

```yaml
mappings:
  animations:
    saber:
      default: "anim_saber_slash_01"
      crit: "anim_saber_critical_slash"

  effects:
    CRIT: ["vfx_screen_shake_heavy", "vfx_flash_red"]
    HIT: ["vfx_screen_shake_light"]
```

## 自定义演出风格

### 修改文本模板

直接编辑 `config/presentation.yaml` 中的 `templates` 部分：

```yaml
templates:
  attack:
    MELEE:
      HIT:
        - "你的自定义文本模板，{attacker} 攻击 {defender}"
```

### 添加新的命中部位

编辑 `src/presentation/mapper.py` 中的 `HIT_LOCATIONS` 和 `CRIT_LOCATIONS`：

```python
class EventMapper:
    HIT_LOCATIONS = [
        "装甲连接部", "驾驶舱外壁",
        # 添加你的自定义部位
        "左臂", "右腿"
    ]
```

### 修改视觉资源映射

编辑 `config/presentation.yaml` 中的 `mappings` 部分，添加你的资源ID：

```yaml
mappings:
  animations:
    your_weapon:
      default: "anim_your_weapon_01"
      crit: "anim_your_weapon_crit"
```

## 测试演出系统

运行测试脚本：

```bash
python tests/test_presentation.py
```

该脚本会测试：
- 事件转换器功能
- 文本渲染器功能
- 不同武器类型和攻击结果的演出效果

## 注意事项

1. **不要过度封装** - 代码保持简洁，逻辑清晰
2. **使用Google风格docstring** - 便于调试和维护
3. **配置驱动** - 修改演出风格优先修改配置文件
4. **类型注解** - 使用Optional等类型提示，提高代码可读性

## 扩展建议

未来可以扩展的方向：
1. 添加更多武器类型的模板
2. 支持多语言文本模板
3. 添加环境效果（雨天、宇宙等）
4. 集成WebSocket实时推送演出事件到前端
5. 添加技能触发的特殊演出效果
