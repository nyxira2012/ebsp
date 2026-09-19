import random
from typing import Any, Dict, List, Optional, Union

from src.models import InstanceZoneConfig, ZoneConfig
from src.pve.models import EventSequence, PveEvent
from src.pve.enums import EventType


class EventSequenceGenerator:
    """PVE 事件序列生成器。

    根据子区域配置随机生成一条线性事件序列，替代原有的点阵地图生成器。

    Doc 13 规范：
    - 支持固定遭遇位置（fixed_encounters）
    - 支持暗雷数量限制（total_random_encounters）
    - 序列末尾固定为 Boss（如果存在配置）

    支持两种配置格式（Doc 13 迁移期）：
    - InstanceZoneConfig：新副本格式，读 sequence 序列配置；
    - ZoneConfig：旧区域格式，读事件数/权重/资源池字段。
    """

    # 默认权重配置（不含 BOSS_COMBAT，Boss 固定在末尾）
    DEFAULT_WEIGHTS = {
        EventType.COMBAT: 40,
        EventType.ELITE_COMBAT: 15,
        EventType.LOOT: 25,
        EventType.EVENT: 20,
    }

    DEFAULT_EVENT_COUNT_RANGE = (8, 12)

    @classmethod
    def generate(
        cls, config: Optional[Union[InstanceZoneConfig, ZoneConfig]] = None
    ) -> EventSequence:
        """根据子区域配置生成事件序列。

        生成的序列结构：
        1. 首先放置 fixed_encounters 中指定的固定事件
        2. 剩余位置按权重随机填充事件
        3. 考虑 total_random_encounters 限制

        Args:
            config: 子区域配置（新 InstanceZoneConfig 或旧 ZoneConfig），
                None 时全部使用默认值。

        Returns:
            EventSequence: 生成的事件序列。
        """
        # 1. 读取配置参数
        event_count_range = cls.DEFAULT_EVENT_COUNT_RANGE
        weights = dict(cls.DEFAULT_WEIGHTS)
        boss_template = "boss_default"
        elite_pool = ["elite_1", "elite_2"]
        normal_pool = ["mob_1", "mob_2"]

        # 固定遭遇配置 {0-based index: {"type": "COMBAT", "template_id": "..."}}
        fixed_encounters: Dict[int, Dict[str, Any]] = {}
        random_encounter_chance = 0.4
        total_random_encounters: Optional[int] = None
        event_chance = 0.2

        if isinstance(config, InstanceZoneConfig):
            seq = config.sequence
            event_count_range = (seq.length, seq.length)
            for idx_str, enc in seq.fixed_encounters.items():
                try:
                    idx = int(idx_str)
                except ValueError:
                    continue
                fixed_encounters[idx] = {"type": enc.type, "template_id": enc.template_id}
            random_encounter_chance = seq.random_encounter_chance
            total_random_encounters = seq.total_random_encounters
            event_chance = seq.event_chance
        elif isinstance(config, ZoneConfig):
            if len(config.event_count_range) == 2:
                event_count_range = (config.event_count_range[0], config.event_count_range[1])
            if config.boss_template:
                boss_template = config.boss_template
            if config.elite_pool:
                elite_pool = config.elite_pool
            if config.normal_pool:
                normal_pool = config.normal_pool
            if config.event_weights:
                weights = {
                    EventType(k): v
                    for k, v in config.event_weights.items()
                    if k in EventType.__members__
                }

        # 2. 确定总事件数
        total_events = event_count_range[0]  # 使用固定长度（新格式）
        if event_count_range[0] != event_count_range[1]:
            total_events = random.randint(*event_count_range)

        # 3. 初始化事件序列
        events: List[PveEvent] = [None] * total_events  # type: ignore

        # 4. 先放置固定遭遇
        fixed_indices = set()
        for idx, fixed_data in fixed_encounters.items():
            if 1 <= idx <= total_events:  # 1-based 转为 0-based
                array_idx = idx - 1
                event_type = EventType[fixed_data["type"]]
                template_id = fixed_data.get("template_id")
                events[array_idx] = PveEvent(
                    index=array_idx,
                    event_type=event_type,
                    event_id=template_id or cls._pick_event_id(event_type, elite_pool, normal_pool)
                )
                fixed_indices.add(array_idx)

        # 5. 填充剩余位置
        random_count = 0

        for i in range(total_events):
            if events[i] is not None:
                continue  # 已被固定遭遇占用

            chosen_type = cls._choose_event_type(
                total_random_encounters,
                random_count,
                random_encounter_chance,
                event_chance,
                weights,
            )

            if chosen_type in (EventType.COMBAT, EventType.ELITE_COMBAT):
                random_count += 1

            event_id = cls._pick_event_id(chosen_type, elite_pool, normal_pool)
            events[i] = PveEvent(index=i, event_type=chosen_type, event_id=event_id)

        # 6. 末尾强制追加 Boss（固定 Boss 占末位时上面已判过 BOSS_COMBAT）
        last_idx = total_events - 1
        if events[last_idx].event_type != EventType.BOSS_COMBAT:
            events[last_idx] = PveEvent(
                index=last_idx,
                event_type=EventType.BOSS_COMBAT,
                event_id=boss_template
            )

        return EventSequence(events=events, current_index=0)

    @staticmethod
    def _choose_event_type(
        total_random_encounters: Optional[int],
        random_count: int,
        random_encounter_chance: float,
        event_chance: float,
        weights: Dict[EventType, int],
    ) -> EventType:
        """选择下一个事件的类型。

        Args:
            total_random_encounters: 暗雷总次数上限。
            random_count: 当前已生成的暗雷次数。
            random_encounter_chance: 暗雷触发概率。
            event_chance: 补给事件触发概率。
            weights: 事件类型权重字典。

        Returns:
            EventType: 选择的事件类型。
        """
        # 检查是否超过暗雷数量限制
        if total_random_encounters is not None and random_count >= total_random_encounters:
            # 超过限制，只能放置非战斗事件
            return random.choices(
                [EventType.LOOT, EventType.EVENT],
                weights=[weights.get(EventType.LOOT, 1), weights.get(EventType.EVENT, 1)],
                k=1
            )[0]

        # 暗雷判定
        if random.random() < random_encounter_chance:
            return random.choices(list(weights.keys()), weights=list(weights.values()), k=1)[0]

        # 非战斗事件
        return EventType.EVENT if random.random() < event_chance else EventType.LOOT

    @staticmethod
    def _pick_event_id(event_type: EventType, elite_pool: List[str], normal_pool: List[str]) -> Optional[str]:
        """根据事件类型从对应资源池中随机选取一个 ID。

        Args:
            event_type (EventType): 事件类型。
            elite_pool (List[str]): 精英怪模板 ID 列表。
            normal_pool (List[str]): 普通怪模板 ID 列表。

        Returns:
            Optional[str]: 选取的资源 ID，LOOT/EVENT 类型返回固定 ID。
        """
        if event_type == EventType.COMBAT:
            return random.choice(normal_pool) if normal_pool else "mob_default"
        elif event_type == EventType.ELITE_COMBAT:
            return random.choice(elite_pool) if elite_pool else "elite_default"
        elif event_type == EventType.LOOT:
            return "random_chest"
        elif event_type == EventType.EVENT:
            return "random_event"
        return None
