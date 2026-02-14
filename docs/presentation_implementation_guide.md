# 演出系统实现指南

> **配套文档**：本文档是 `combat_presentation.md` 的技术实现参考手册，提供了 FastAPI 和 WebSocket 的具体代码实现。

---

## 1. 快速开始：最小可行原型（MVP）

### 1.1 核心数据结构（代码实现）

创建 `src/presentation/models.py`：

```python
"""
演出系统数据模型
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
import time

class PresentationEventType(str, Enum):
    """演出事件类型"""
    ROUND_START = "round_start"
    INITIATIVE = "initiative"
    ATTACK = "attack"
    SKILL_TRIGGER = "skill_trigger"
    DAMAGE_APPLY = "damage_apply"
    ROUND_END = "round_end"
    BATTLE_END = "battle_end"

@dataclass
class RawAttackEvent:
    """原始攻击事件（战斗引擎生成）"""
    round_number: int
    attacker_id: str
    defender_id: str
    weapon_id: str
    weapon_type: str  # "MELEE"/"RIFLE"/"AWAKENING"
    attack_result: str  # "HIT"/"MISS"/"CRIT"/"DODGE"/"PARRY"/"BLOCK"
    damage: int
    roll: float
    distance: int
    will_delta_attacker: int
    will_delta_defender: int
    triggered_skills: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

@dataclass
class PresentationEvent:
    """演出事件基类"""
    event_type: PresentationEventType
    timestamp: float
    priority: int = 50
    duration: float = 1.0  # 预计播放时长（秒）

@dataclass
class PresentationAttackEvent(PresentationEvent):
    """攻击演出事件"""
    # 原始数据
    raw_data: RawAttackEvent

    # 表现数据
    text_template: str = ""
    hit_location: str = ""
    camera_angle: str = "default"
    animation_id: str = "default"
    animation_speed: float = 1.0
    screen_effects: List[str] = field(default_factory=list)
    sound_effects: List[str] = field(default_factory=list)
    voice_lines: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self.event_type = PresentationEventType.ATTACK

@dataclass
class RoundTimeline:
    """回合演出时间轴"""
    round_number: int
    events: List[PresentationEvent] = field(default_factory=list)

    def add_event(self, event: PresentationEvent):
        """添加事件并按优先级排序"""
        self.events.append(event)
        self.events.sort(key=lambda e: e.priority, reverse=True)

    def get_total_duration(self) -> float:
        """计算总时长"""
        return sum(e.duration for e in self.events)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化到前端）"""
        return {
            "round_number": self.round_number,
            "events": [self._event_to_dict(e) for e in self.events],
            "total_duration": self.get_total_duration()
        }

    def _event_to_dict(self, event: PresentationEvent) -> Dict[str, Any]:
        """事件转字典"""
        if isinstance(event, PresentationAttackEvent):
            return {
                "type": event.event_type.value,
                "timestamp": event.timestamp,
                "priority": event.priority,
                "duration": event.duration,
                "attacker": event.raw_data.attacker_id,
                "defender": event.raw_data.defender_id,
                "weapon": event.raw_data.weapon_id,
                "result": event.raw_data.attack_result,
                "damage": event.raw_data.damage,
                "text": event.text_template,
                "location": event.hit_location,
                "camera": event.camera_angle,
                "animation": event.animation_id,
                "effects": event.screen_effects,
                "sounds": event.sound_effects
            }
        return {
            "type": event.event_type.value,
            "timestamp": event.timestamp,
            "duration": event.duration
        }
```

### 1.2 事件转换器（代码实现）

创建 `src/presentation/mapper.py`：

```python
"""
事件转换器
"""
import random
from typing import Dict, Any
from .models import RawAttackEvent, PresentationAttackEvent

class EventMapper:
    """事件转换器"""

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: 从YAML加载的配置字典
        """
        self.config = config
        self.hit_locations = config.get("hit_locations", [
            "头部传感器", "胸部驾驶舱", "肩部装甲", "手臂关节", "腿部推进器"
        ])

    def map_attack_event(self, raw_event: RawAttackEvent) -> PresentationAttackEvent:
        """将原始攻击事件转换为演出事件"""
        # 1. 选择文字模板
        text_template = self._select_text_template(raw_event)

        # 2. 计算命中部位（仅命中/暴击时）
        hit_location = ""
        if raw_event.attack_result in ["HIT", "CRIT"]:
            hit_location = random.choice(self.hit_locations)

        # 3. 确定动画ID
        animation_id = self._get_animation_id(raw_event)

        # 4. 确定镜头角度
        camera_angle = self._get_camera_angle(raw_event)

        # 5. 获取特效
        screen_effects = self._get_screen_effects(raw_event)

        # 6. 获取音效
        sound_effects = self._get_sound_effects(raw_event)

        # 7. 计算优先级
        priority = self._get_priority(raw_event)

        # 8. 估算时长
        duration = self._estimate_duration(raw_event)

        return PresentationAttackEvent(
            raw_data=raw_event,
            text_template=text_template,
            hit_location=hit_location,
            camera_angle=camera_angle,
            animation_id=animation_id,
            screen_effects=screen_effects,
            sound_effects=sound_effects,
            priority=priority,
            duration=duration
        )

    def _select_text_template(self, event: RawAttackEvent) -> str:
        """选择文字模板"""
        templates = self.config.get("text_templates", {}).get("attack", {})
        result_templates = templates.get(event.attack_result.lower(), [])

        if not result_templates:
            # 默认模板
            return f"{event.attacker_id}使用{event.weapon_id}发起了攻击！"

        # 随机选择一个模板
        template = random.choice(result_templates)

        # 填充模板占位符
        return template.format(
            attacker=event.attacker_id,
            defender=event.defender_id,
            weapon=event.weapon_id,
            location="{location}",  # 占位符，后续填充
            damage=event.damage
        )

    def _get_animation_id(self, event: RawAttackEvent) -> str:
        """获取动画ID"""
        weapon_anim = self.config.get("animation_mapping", {}).get("weapons", {})
        weapon_cfg = weapon_anim.get(event.weapon_type.lower(), {})

        # 根据攻击结果返回不同动画
        if event.attack_result == "CRIT" and "critical" in weapon_cfg:
            return weapon_cfg["critical"]
        elif event.attack_result == "MISS" and "miss" in weapon_cfg:
            return weapon_cfg["miss"]
        elif "attack" in weapon_cfg:
            return weapon_cfg["attack"]

        return "default_attack"

    def _get_camera_angle(self, event: RawAttackEvent) -> str:
        """获取镜头角度"""
        camera_cfg = self.config.get("animation_mapping", {}).get("camera_angles", {})

        if event.weapon_type == "MELEE":
            return camera_cfg.get("melee", "close_up")
        elif event.weapon_type == "RIFLE":
            return camera_cfg.get("ranged", "side_view")
        else:
            return camera_cfg.get("sniper", "first_person")

    def _get_screen_effects(self, event: RawAttackEvent) -> list:
        """获取屏幕特效"""
        effects_cfg = self.config.get("effects", {}).get("attack", {})

        if event.attack_result == "CRIT":
            return effects_cfg.get("crit", ["flash", "shake"])
        elif event.attack_result == "HIT":
            return effects_cfg.get("hit", ["flash"])
        elif event.attack_result == "DODGE":
            return effects_cfg.get("dodge", ["speed_lines"])
        else:
            return []

    def _get_sound_effects(self, event: RawAttackEvent) -> list:
        """获取音效"""
        sounds_cfg = self.config.get("sound_effects", {})
        weapon_sounds = sounds_cfg.get("weapons", {})
        impact_sounds = sounds_cfg.get("impacts", {})

        sounds = []

        # 武器音效
        weapon_sound = weapon_sounds.get(event.weapon_type.lower())
        if weapon_sound:
            sounds.append(weapon_sound)

        # 命中音效
        if event.attack_result in ["HIT", "CRIT"]:
            impact_sound = impact_sounds.get("hit" if event.attack_result == "HIT" else "crit")
            if impact_sound:
                sounds.append(impact_sound)

        return sounds

    def _get_priority(self, event: RawAttackEvent) -> int:
        """获取播放优先级"""
        priorities = self.config.get("priorities", {})

        if event.attack_result == "CRIT":
            return priorities.get("critical_attack", 100)
        elif event.attack_result == "DODGE":
            return priorities.get("dodge", 70)
        else:
            return priorities.get("normal_attack", 50)

    def _estimate_duration(self, event: RawAttackEvent) -> float:
        """估算播放时长"""
        durations = self.config.get("durations", {})

        if event.weapon_type == "MELEE":
            return durations.get("attack_melee", 2.0)
        else:
            return durations.get("attack_ranged", 1.5)
```

### 1.3 文本渲染器（代码实现）

创建 `src/presentation/renderers.py`：

```python
"""
演出渲染器
"""
from abc import ABC, abstractmethod
from typing import List
from .models import PresentationEvent, PresentationAttackEvent, RoundTimeline

class PresentationRenderer(ABC):
    """演出渲染器基类"""

    @abstractmethod
    def render_round(self, timeline: RoundTimeline) -> None:
        """渲染一个回合"""
        pass

    @abstractmethod
    def render_event(self, event: PresentationEvent) -> None:
        """渲染单个事件"""
        pass

class TextRenderer(PresentationRenderer):
    """文本渲染器（兼容现有print输出）"""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def render_round(self, timeline: RoundTimeline) -> None:
        """渲染回合为文本"""
        if not self.verbose:
            return

        print(f"\n{'=' * 80}")
        print(f"ROUND {timeline.round_number}")
        print(f"{'=' * 80}\n")

        for event in timeline.events:
            self.render_event(event)

    def render_event(self, event: PresentationEvent) -> None:
        """渲染单个事件"""
        if isinstance(event, PresentationAttackEvent):
            self._render_attack(event)
        else:
            # 其他事件类型
            pass

    def _render_attack(self, event: PresentationAttackEvent) -> None:
        """渲染攻击事件"""
        raw = event.raw_data

        # 替换文本中的 {location} 占位符
        text = event.text_template.replace("{location}", event.hit_location)

        # 获取结果emoji
        emoji_map = {
            "MISS": "❌",
            "DODGE": "💨",
            "PARRY": "🛡️",
            "BLOCK": "🔰",
            "HIT": "💥",
            "CRIT": "⚡"
        }
        emoji = emoji_map.get(raw.attack_result, "•")

        # 打印输出
        print(f"  {emoji} {text}")

        # 打印伤害信息
        if raw.damage > 0:
            print(f"     伤害: {raw.damage} | 气力: {raw.attacker_id}({raw.will_delta_attacker:+d}) {raw.defender_id}({raw.will_delta_defender:+d})")

        # 打印技能触发
        if raw.triggered_skills:
            for skill_id in raw.triggered_skills:
                print(f"     ✨ 技能【{skill_id}】触发！")
```

### 1.4 配置文件示例

创建 `config/presentation_config.yaml`：

```yaml
# 文字模板配置
text_templates:
  attack:
    miss:
      - "{attacker}的{weapon}在米诺夫斯基粒子的干扰下偏离了轨道。"
      - "{weapon}的攻击角度被完全破解，炮火在宇宙中画出徒劳的弧线。"

    hit:
      - "{attacker}的{weapon}准确命中{defender}的{location}，炸开一团火光。"
      - "{weapon}的攻击撕破了装甲，{location}处引发剧烈爆炸，碎片四溅。"

    crit:
      - "致命一击！{attacker}的{weapon}以刁钻的角度贯入{defender}的{location}！"
      - "{weapon}精准命中要害！{location}瞬间被光束洞穿，机体剧烈震颤。"

    dodge:
      - "{defender}推进器全开，在千钧一发之际灵巧避开了攻击。"
      - "惊人的反应速度！{defender}在攻击击发的瞬间侧身翻滚，光束擦着装甲边缘飞过。"

    parry:
      - "精彩！{defender}用手持武器精准架住{weapon}的攻击，火花四溅！"

    block:
      - "{defender}的装甲格挡稳稳化解了{weapon}的冲击。"

# 命中部位库
hit_locations:
  - "头部传感器"
  - "胸部驾驶舱"
  - "肩部装甲"
  - "手臂关节"
  - "腿部推进器"
  - "背包喷射口"

# 动画映射配置
animation_mapping:
  weapons:
    melee:  # 格斗武器
      attack: "anim_melee_attack"
      critical: "anim_melee_critical"
      miss: "anim_melee_miss"

    rifle:  # 射击武器
      attack: "anim_rifle_attack"
      critical: "anim_rifle_critical"
      miss: "anim_rifle_miss"

    awakening:  # 觉醒武器（浮游炮等）
      attack: "anim_awakening_attack"
      critical: "anim_awakening_critical"

  camera_angles:
    melee: "close_up"
    ranged: "side_view"
    sniper: "first_person"
    awakening: "dramatic_angle"

# 特效配置
effects:
  attack:
    hit: ["flash_light"]
    crit: ["flash_heavy", "shake_heavy", "slow_motion_0.3s"]
    dodge: ["speed_lines"]
    parry: ["spark_heavy"]

# 音效配置
sound_effects:
  weapons:
    melee: "sfx_melee_swing.wav"
    rifle: "sfx_beam_rifle_fire.wav"
    awakening: "sfx_funnel_launch.wav"

  impacts:
    hit: "sfx_armor_hit.wav"
    crit: "sfx_armor_crit.wav"
    dodge: "sfx_dodge_woosh.wav"
    parry: "sfx_weapon_clash.wav"

# 播放优先级
priorities:
  critical_attack: 100
  dodge: 80
  parry: 75
  normal_attack: 50
  miss: 30

# 事件持续时间（秒）
durations:
  attack_melee: 2.0
  attack_ranged: 1.5
  dodge: 1.0
  parry: 1.2
  round_transition: 0.5
```

### 1.5 集成到战斗引擎

修改 `src/combat/engine.py` 中的 `_execute_attack` 方法：

```python
"""
战斗引擎（集成演出系统）
"""
from ..presentation.mapper import EventMapper
from ..presentation.renderers import TextRenderer
from ..presentation.models import RawAttackEvent, RoundTimeline

class BattleSimulator:
    """战斗模拟器（支持演出系统）"""

    def __init__(self, mecha_a, mecha_b, enable_presentation=True):
        self.mecha_a = mecha_a
        self.mecha_b = mecha_b
        self.round_number = 0

        # 演出系统
        self.enable_presentation = enable_presentation
        if enable_presentation:
            from ..presentation.config import load_presentation_config
            config = load_presentation_config("config/presentation_config.yaml")
            self.event_mapper = EventMapper(config)
            self.renderer = TextRenderer(verbose=True)
            self.timelines: List[RoundTimeline] = []

        # 当前回合时间轴
        self.current_timeline: Optional[RoundTimeline] = None

    def _execute_round(self) -> None:
        """执行单个战斗回合"""
        self.round_number += 1

        # 初始化当前回合时间轴
        if self.enable_presentation:
            self.current_timeline = RoundTimeline(round_number=self.round_number)

        # ... 现有的回合逻辑（距离生成、先手判定等）

        # 执行攻击
        self._execute_attack(first_mover, second_mover, distance, is_first=True)
        self._execute_attack(second_mover, first_mover, distance, is_first=False)

        # 渲染回合
        if self.enable_presentation:
            self.renderer.render_round(self.current_timeline)
            self.timelines.append(self.current_timeline)

    def _execute_attack(self, attacker, defender, distance, is_first) -> None:
        """执行单次攻击（生成演出事件）"""
        # ... 现有的攻击逻辑（武器选择、EN消耗、圆桌判定等）

        # 创建原始事件
        raw_event = RawAttackEvent(
            round_number=self.round_number,
            attacker_id=attacker.name,
            defender_id=defender.name,
            weapon_id=weapon.name,
            weapon_type=weapon.type.value,  # MELEE/RIFLE/AWAKENING
            attack_result=result.value,  # HIT/MISS/CRIT等
            damage=damage,
            roll=ctx.roll,
            distance=distance,
            will_delta_attacker=ctx.current_attacker_will_delta,
            will_delta_defender=ctx.current_defender_will_delta,
            triggered_skills=ctx.triggered_skill_ids
        )

        # 转换为演出事件
        if self.enable_presentation:
            presentation_event = self.event_mapper.map_attack_event(raw_event)
            self.current_timeline.add_event(presentation_event)

            # 实时渲染（可选）
            # self.renderer.render_event(presentation_event)

        # 调试输出（如果禁用演出系统，使用原有print）
        if not self.enable_presentation:
            print(f"{'[先攻]' if is_first else '[反击]'} {attacker.name} 使用 【{weapon.name}】")
            print(f"   {result.value}! 伤害: {damage}")
```

---

## 2. WebSocket实时通信（Web前端集成）

### 2.1 后端WebSocket服务器

创建 `src/presentation/websocket_server.py`：

```python
"""
WebSocket服务器（实时推送演出事件）
"""
from fastapi import WebSocket
from typing import List
import json
from .models import PresentationEvent, RoundTimeline

class PresentationBroadcaster:
    """演出事件广播器"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """接受新连接"""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """断开连接"""
        self.active_connections.remove(websocket)

    async def broadcast_event(self, event: PresentationEvent):
        """广播演出事件"""
        if self.active_connections:
            # 转换事件为字典
            event_dict = self._event_to_dict(event)

            # 广播给所有连接的客户端
            for connection in self.active_connections:
                await connection.send_json(event_dict)

    async def broadcast_timeline(self, timeline: RoundTimeline):
        """广播完整回合时间轴"""
        if self.active_connections:
            await asyncio.gather(*[
                connection.send_json(timeline.to_dict())
                for connection in self.active_connections
            ])

    def _event_to_dict(self, event: PresentationEvent) -> dict:
        """事件转字典"""
        if isinstance(event, PresentationAttackEvent):
            return {
                "type": "attack",
                "attacker": event.raw_data.attacker_id,
                "defender": event.raw_data.defender_id,
                "weapon": event.raw_data.weapon_id,
                "result": event.raw_data.attack_result,
                "damage": event.raw_data.damage,
                "text": event.text_template,
                "location": event.hit_location,
                "camera": event.camera_angle,
                "animation": event.animation_id,
                "effects": event.screen_effects,
                "sounds": event.sound_effects,
                "duration": event.duration
            }
        return {"type": event.event_type.value}

# 全局广播器实例
broadcaster = PresentationBroadcaster()
```

### 2.2 FastAPI路由集成

```python
"""
FastAPI应用（集成WebSocket）
"""
from fastapi import FastAPI, WebSocket
from .presentation.websocket_server import broadcaster

app = FastAPI()

@app.websocket("/ws/battle")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点（前端连接）"""
    await broadcaster.connect(websocket)
    try:
        while True:
            # 保持连接，等待数据
            await websocket.receive_text()
    except:
        broadcaster.disconnect(websocket)
```

### 2.3 前端React组件

```typescript
/**
 * BattleViewer组件 - 接收并显示演出事件
 */
import React, { useEffect, useState } from 'react';

interface PresentationEvent {
  type: string;
  attacker?: string;
  defender?: string;
  weapon?: string;
  result?: string;
  damage?: number;
  text?: string;
  location?: string;
  camera?: string;
  animation?: string;
  effects?: string[];
  sounds?: string[];
  duration?: number;
}

interface RoundTimeline {
  round_number: number;
  events: PresentationEvent[];
  total_duration: number;
}

export const BattleViewer: React.FC = () => {
  const [timelines, setTimelines] = useState<RoundTimeline[]>([]);
  const [currentRound, setCurrentRound] = useState(1);

  useEffect(() => {
    // 连接WebSocket
    const ws = new WebSocket('ws://localhost:8000/ws/battle');

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.round_number !== undefined) {
        // 完整回合时间轴
        setTimelines((prev) => [...prev, data]);
        setCurrentRound(data.round_number);
      } else if (data.type === 'attack') {
        // 单个事件
        console.log('收到攻击事件:', data);
      }
    };

    return () => {
      ws.close();
    };
  }, []);

  return (
    <div className="battle-viewer">
      {/* 3D场景 */}
      <BattleScene events={timelines.find(t => t.round_number === currentRound)?.events} />

      {/* 战斗日志 */}
      <BattleLog timelines={timelines} />

      {/* 机体状态面板 */}
      <StatusPanel />
    </div>
  );
};

/**
 * 战斗日志组件
 */
const BattleLog: React.FC<{ timelines: RoundTimeline[] }> = ({ timelines }) => {
  return (
    <div className="battle-log">
      {timelines.map((timeline) => (
        <div key={timeline.round_number} className="round">
          <h3>ROUND {timeline.round_number}</h3>
          {timeline.events.map((event, idx) => (
            <div key={idx} className="event">
              {event.text && <p>{event.text}</p>}
              {event.damage !== undefined && <span>伤害: {event.damage}</span>}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
};
```

---

## 3. 数据导出与回放

### 3.1 导出为JSON

```python
"""
导出演出数据为JSON
"""
import json
from .models import RoundTimeline

def export_timeline_to_json(timeline: RoundTimeline, filepath: str) -> None:
    """导出时间轴为JSON文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(timeline.to_dict(), f, ensure_ascii=False, indent=2)

def import_timeline_from_json(filepath: str) -> RoundTimeline:
    """从JSON文件导入时间轴"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # 重建RoundTimeline对象
    # ...
```

### 3.2 回放系统

```python
"""
战斗回放器
"""
import time
from .models import RoundTimeline
from .renderers import PresentationRenderer

class BattleReplayer:
    """战斗回放器"""

    def __init__(self, timelines: List[RoundTimeline], renderer: PresentationRenderer):
        self.timelines = timelines
        self.renderer = renderer

    def replay(self, speed: float = 1.0):
        """回放战斗

        Args:
            speed: 播放速度倍率（1.0=正常，2.0=2倍速）
        """
        for timeline in self.timelines:
            self.renderer.render_round(timeline)

            for event in timeline.events:
                # 根据播放速度调整等待时间
                wait_time = event.duration / speed
                time.sleep(wait_time)

    def save_to_file(self, filepath: str):
        """保存回放数据到文件"""
        import json

        data = {
            "timelines": [t.to_dict() for t in self.timelines],
            "metadata": {
                "total_rounds": len(self.timelines),
                "total_duration": sum(t.get_total_duration() for t in self.timelines)
            }
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
```

---

## 4. 测试指南

### 4.1 单元测试

创建 `tests/test_presentation.py`：

```python
"""
演出系统单元测试
"""
import pytest
from src.presentation.models import RawAttackEvent, PresentationAttackEvent
from src.presentation.mapper import EventMapper
from src.presentation.renderers import TextRenderer

@pytest.fixture
def sample_config():
    """示例配置"""
    return {
        "text_templates": {
            "attack": {
                "hit": ["{attacker}的{weapon}命中了{defender}！"],
                "crit": ["致命一击！{attacker}的{weapon}贯穿了{location}！"]
            }
        },
        "hit_locations": ["头部", "胸部", "手臂"],
        "animation_mapping": {
            "weapons": {
                "rifle": {"attack": "anim_rifle"}
            }
        },
        "priorities": {
            "normal_attack": 50,
            "critical_attack": 100
        },
        "durations": {
            "attack_ranged": 1.5
        }
    }

@pytest.fixture
def sample_raw_event():
    """示例原始事件"""
    return RawAttackEvent(
        round_number=1,
        attacker_id="高达",
        defender_id="扎古",
        weapon_id="光束步枪",
        weapon_type="RIFLE",
        attack_result="HIT",
        damage=1500,
        roll=75.0,
        distance=2000,
        will_delta_attacker=2,
        will_delta_defender=1,
        triggered_skills=["瞄准射击"]
    )

def test_event_mapper_maps_hit_event(sample_config, sample_raw_event):
    """测试事件转换器正确映射HIT事件"""
    mapper = EventMapper(sample_config)
    presentation_event = mapper.map_attack_event(sample_raw_event)

    assert isinstance(presentation_event, PresentationAttackEvent)
    assert "高达" in presentation_event.text_template
    assert "光束步枪" in presentation_event.text_template
    assert presentation_event.hit_location in ["头部", "胸部", "手臂"]
    assert presentation_event.animation_id == "anim_rifle"
    assert presentation_event.priority == 50
    assert presentation_event.duration == 1.5

def test_event_mapper_maps_crit_event(sample_config):
    """测试事件转换器正确映射CRIT事件"""
    raw_event = RawAttackEvent(
        round_number=1,
        attacker_id="高达",
        defender_id="扎古",
        weapon_id="光束步枪",
        weapon_type="RIFLE",
        attack_result="CRIT",
        damage=3000,
        roll=95.0,
        distance=2000,
        will_delta_attacker=5,
        will_delta_defender=0,
        triggered_skills=[]
    )

    mapper = EventMapper(sample_config)
    presentation_event = mapper.map_attack_event(raw_event)

    assert "致命一击" in presentation_event.text_template
    assert presentation_event.priority == 100  # CRIT优先级更高
    assert presentation_event.hit_location in ["头部", "胸部", "手臂"]

def test_text_renderer_renders_attack_event(sample_raw_event, sample_config):
    """测试文本渲染器正确渲染攻击事件"""
    import io
    import sys

    # 重定向stdout
    captured_output = io.StringIO()
    sys.stdout = captured_output

    mapper = EventMapper(sample_config)
    renderer = TextRenderer(verbose=True)
    presentation_event = mapper.map_attack_event(sample_raw_event)

    renderer.render_event(presentation_event)

    # 恢复stdout
    sys.stdout = sys.__stdout__

    output = captured_output.getvalue()
    assert "高达" in output
    assert "光束步枪" in output
    assert "1500" in output  # 伤害值
```

### 4.2 集成测试

```python
"""
演出系统集成测试
"""
import pytest
from src.combat.engine import BattleSimulator
from src.factory import MechaFactory

def test_battle_generates_presentation_events():
    """测试战斗引擎正确生成演出事件"""
    # 创建机体
    factory = MechaFactory()
    mecha_a = factory.create_mecha("mecha_rx78", "pilot_amuro")
    mecha_b = factory.create_mecha("mecha_zaku", "pilot_char")

    # 运行战斗（启用演出系统）
    simulator = BattleSimulator(mecha_a, mecha_b, enable_presentation=True)
    simulator.run_battle()

    # 验证生成了时间轴
    assert len(simulator.timelines) > 0

    # 验证每个回合都有事件
    for timeline in simulator.timelines:
        assert len(timeline.events) > 0
        assert timeline.round_number > 0
```

---

## 5. 性能优化建议

### 5.1 事件池化

```python
"""
事件对象池（减少GC压力）
"""
from typing import List

class EventPool:
    """事件对象池"""

    def __init__(self, event_class, initial_size: int = 100):
        self.event_class = event_class
        self.pool: List = []
        self._initialize_pool(initial_size)

    def _initialize_pool(self, size: int):
        """初始化对象池"""
        for _ in range(size):
            self.pool.append(self.event_class())

    def acquire(self) -> Any:
        """从池中获取对象"""
        if self.pool:
            return self.pool.pop()
        return self.event_class()

    def release(self, event: Any) -> None:
        """归还对象到池中"""
        # 重置对象状态
        if hasattr(event, '__dict__'):
            for key in list(event.__dict__.keys()):
                del event.__dict__[key]
        self.pool.append(event)
```

### 5.2 懒加载配置

```python
"""
懒加载配置（只在首次使用时加载）
"""
class LazyConfigLoader:
    """懒加载配置"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self._config = None

    @property
    def config(self):
        """首次访问时加载配置"""
        if self._config is None:
            import yaml
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f)
        return self._config
```

### 5.3 异步渲染

```python
"""
异步渲染器（不阻塞战斗逻辑）
"""
import asyncio

class AsyncRenderer(PresentationRenderer):
    """异步渲染器"""

    async def render_event_async(self, event: PresentationEvent):
        """异步渲染事件"""
        # 在独立的线程/进程中渲染
        await asyncio.to_thread(self.render_event, event)
```

---

## 6. 调试工具

### 6.1 时间轴可视化

```python
"""
时间轴可视化工具
"""
from .models import RoundTimeline

def visualize_timeline(timeline: RoundTimeline) -> str:
    """生成时间轴的ASCII可视化"""
    output = [f"ROUND {timeline.round_number}"]
    output.append("=" * 80)

    for event in timeline.events:
        bar = "█" * int(event.duration * 10)
        output.append(f"{event.event_type.value:15} |{bar:50}| {event.duration:.1f}s")

    return "\n".join(output)

# 示例输出：
# ROUND 1
# ===============================================================================
# ATTACK          |██████████████████████████████████████████████████| 5.0s
# SKILL_TRIGGER   |██████████| 1.0s
# DAMAGE_APPLY    |██| 0.2s
```

### 6.2 事件追踪器

```python
"""
事件追踪器（记录所有事件到日志文件）
"""
import logging
from datetime import datetime

class EventTracker:
    """事件追踪器"""

    def __init__(self, log_file: str = "presentation_events.log"):
        self.logger = logging.getLogger("EventTracker")
        self.logger.setLevel(logging.INFO)

        handler = logging.FileHandler(log_file, encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        self.logger.addHandler(handler)

    def track_event(self, event: PresentationEvent):
        """记录事件"""
        self.logger.info(f"{event.event_type.value}: {event}")

    def track_timeline(self, timeline: RoundTimeline):
        """记录时间轴"""
        self.logger.info(f"Round {timeline.round_number}: {len(timeline.events)} events")
```

---

## 7. 扩展点

### 7.1 自定义渲染器示例

```python
"""
Markdown渲染器（生成战斗报告）
"""
class MarkdownRenderer(PresentationRenderer):
    """Markdown渲染器"""

    def render_round(self, timeline: RoundTimeline) -> None:
        """渲染回合为Markdown"""
        output = [f"## ROUND {timeline.round_number}\n"]

        for event in timeline.events:
            if isinstance(event, PresentationAttackEvent):
                output.append(f"- **{event.raw_data.attacker_id}** 使用 {event.raw_data.weapon_id}")
                output.append(f"  - 结果: {event.raw_data.attack_result}")
                output.append(f"  - 伤害: {event.raw_data.damage}")
                output.append(f"  - 描述: {event.text_template}\n")

        return "\n".join(output)

    def render_event(self, event: PresentationEvent) -> None:
        pass
```

### 7.2 自定义事件转换器插件

```python
"""
自定义转换器插件（添加特殊演出效果）
"""
class CustomEventMapper(EventMapper):
    """自定义事件转换器（示例：Boss战特殊演出）"""

    def map_attack_event(self, raw_event: RawAttackEvent) -> PresentationAttackEvent:
        """转换事件（添加Boss战特殊效果）"""
        event = super().map_attack_event(raw_event)

        # 如果攻击者是Boss，添加特殊镜头和特效
        if "BOSS" in raw_event.attacker_id.upper():
            event.camera_angle = "boss_dramatic_angle"
            event.screen_effects.append("boss_aura")
            event.sound_effects.append("sfx_boss_attack.wav")

        return event
```

---

## 8. 常见问题FAQ

### Q1: 如何修改文字模板？
**A**: 编辑 `config/presentation_config.yaml` 中的 `text_templates` 部分，无需修改代码。

### Q2: 如何添加新的渲染器？
**A**:
1. 继承 `PresentationRenderer` 类
2. 实现 `render_round()` 和 `render_event()` 方法
3. 在 `BattleSimulator` 中替换 `self.renderer`

### Q3: 如何实现慢动作效果？
**A**:
1. 在事件中添加 `animation_speed` 字段（如0.5表示50%速度）
2. 前端渲染器根据此值调整动画播放速度
3. 或在配置文件的 `effects.crit` 中添加 `"slow_motion_0.3s"`

### Q4: 性能瓶颈在哪里？
**A**:
- **事件创建**：大量小对象可能触发GC，使用对象池优化
- **序列化**：WebSocket传输时JSON序列化耗时，考虑使用MessagePack
- **渲染**：前端动画播放是主要瓶颈，考虑延迟加载和对象池

### Q5: 如何支持多语言？
**A**:
1. 在配置文件中添加 `text_templates_zh`, `text_templates_en` 等
2. 根据用户语言偏好加载对应的模板
3. 或使用i18n库（如 `gettext`）在运行时翻译

---

## 9. 下一步工作

### 短期（1-2周）
- [ ] 实现基础数据模型和EventMapper
- [ ] 编写单元测试覆盖核心逻辑
- [ ] 完成TextRenderer并集成到战斗引擎
- [ ] 编写配置文件文档和示例

### 中期（3-4周）
- [ ] 实现WebSocket服务器
- [ ] 开发React前端原型
- [ ] 添加时间轴可视化工具
- [ ] 实现回放系统

### 长期（1-2月）
- [ ] 集成3D引擎（Three.js/Babylon.js）
- [ ] 添加音效和特效系统
- [ ] 实现视频导出功能
- [ ] 性能优化和压力测试
