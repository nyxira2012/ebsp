import random
from typing import List, Optional, Any, Dict

from src.pve.models import EventSequence, PveEvent
from src.pve.enums import EventType


class EventSequenceGenerator:
    """PVE 事件序列生成器。

    根据区域配置随机生成一条线性事件序列，替代原有的点阵地图生成器。

    Doc 13 规范：
    - 支持固定遭遇位置（fixed_encounters）
    - 支持暗雷数量限制（total_random_encounters）
    - 序列末尾固定为 Boss（如果存在配置）
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
    def generate(cls, region_config: Optional[Any] = None, zone_config: Optional[Any] = None) -> EventSequence:
        """根据区域配置生成事件序列。

        生成的序列结构：
        1. 首先放置 fixed_encounters 中指定的固定事件
        2. 剩余位置按权重随机填充事件
        3. 考虑 total_random_encounters 限制

        Args:
            region_config: 区域配置对象（RegionConfig 或 Mock）。
            zone_config: 子区域序列配置（ZoneSequenceConfig 或包含 sequence 属性的对象）。

        Returns:
            EventSequence: 生成的事件序列。
        """
        # 1. 读取配置参数
        event_count_range = cls.DEFAULT_EVENT_COUNT_RANGE
        weights = dict(cls.DEFAULT_WEIGHTS)
        boss_template = "boss_default"
        elite_pool = ["elite_1", "elite_2"]
        normal_pool = ["mob_1", "mob_2"]

        # 固定遭遇配置 {index: {"type": "COMBAT", "template_id": "..."}}
        fixed_encounters: Dict[int, Dict[str, Any]] = {}
        random_encounter_chance = 0.4
        total_random_encounters: Optional[int] = None
        event_chance = 0.2

        # 从 region_config 读取旧格式配置（兼容性）
        if region_config is not None:
            count_range = getattr(region_config, 'event_count_range', None)
            if count_range and len(count_range) == 2:
                event_count_range = (count_range[0], count_range[1])

            boss_template = getattr(region_config, 'boss_template', boss_template)
            elite_pool = getattr(region_config, 'elite_pool', elite_pool) or elite_pool
            normal_pool = getattr(region_config, 'normal_pool', normal_pool) or normal_pool

            cfg_weights = getattr(region_config, 'event_weights', None)
            if cfg_weights and isinstance(cfg_weights, dict):
                try:
                    weights = {EventType(k): v for k, v in cfg_weights.items() if k in EventType.__members__}
                except (ValueError, KeyError):
                    pass  # 保持默认权重

        # 从 zone_config 读取新格式配置（Doc 13）
        if zone_config is not None:
            sequence_config = getattr(zone_config, 'sequence', None)
            if sequence_config is not None:
                if hasattr(sequence_config, 'length'):
                    event_count_range = (sequence_config.length, sequence_config.length)

                # 解析 fixed_encounters
                raw_fixed = getattr(sequence_config, 'fixed_encounters', {})
                if raw_fixed and isinstance(raw_fixed, dict):
                    try:
                        for idx_str, enc in raw_fixed.items():
                            idx = int(idx_str)
                            fixed_encounters[idx] = {
                                "type": enc.type,
                                "template_id": enc.template_id
                            }
                    except (ValueError, AttributeError, TypeError):
                        pass  # 跳过无效的固定遭遇配置

                if hasattr(sequence_config, 'random_encounter_chance'):
                    random_encounter_chance = sequence_config.random_encounter_chance
                if hasattr(sequence_config, 'total_random_encounters'):
                    total_random_encounters = sequence_config.total_random_encounters
                if hasattr(sequence_config, 'event_chance'):
                    event_chance = sequence_config.event_chance

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
        event_types_pool = list(weights.keys())
        event_type_weights = [weights[t] for t in event_types_pool]

        for i in range(total_events):
            if events[i] is not None:
                continue  # 已被固定遭遇占用

            chosen_type = cls._choose_event_type(
                total_random_encounters,
                random_count,
                random_encounter_chance,
                event_chance,
                event_types_pool,
                event_type_weights,
                weights
            )

            if chosen_type in (EventType.COMBAT, EventType.ELITE_COMBAT):
                random_count += 1

            event_id = cls._pick_event_id(chosen_type, elite_pool, normal_pool)
            events[i] = PveEvent(index=i, event_type=chosen_type, event_id=event_id)

        # 6. 末尾强制追加 Boss（如果没有固定 Boss）
        last_idx = total_events - 1
        if events[last_idx].event_type != EventType.BOSS_COMBAT:
            if (total_events not in fixed_encounters or
                fixed_encounters.get(total_events, {}).get("type") != "BOSS_COMBAT"):
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
        event_types_pool: List[EventType],
        event_type_weights: List[int],
        weights: Dict[EventType, int]
    ) -> EventType:
        """选择下一个事件的类型。

        Args:
            total_random_encounters: 暗雷总次数上限。
            random_count: 当前已生成的暗雷次数。
            random_encounter_chance: 暗雷触发概率。
            event_chance: 补给事件触发概率。
            event_types_pool: 可用的事件类型列表。
            event_type_weights: 事件类型对应的权重列表。
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
            return random.choices(event_types_pool, weights=event_type_weights, k=1)[0]

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
