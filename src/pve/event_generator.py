import random
from typing import List, Optional, Any

from src.pve.models import EventSequence, PveEvent
from src.pve.enums import EventType


class EventSequenceGenerator:
    """PVE 事件序列生成器。

    根据区域配置随机生成一条线性事件序列，替代原有的点阵地图生成器。
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
    def generate(cls, region_config: Optional[Any] = None) -> EventSequence:
        """根据区域配置生成事件序列。

        生成的序列结构：
        - 前 N-1 个事件由权重随机生成（COMBAT/ELITE_COMBAT/LOOT/EVENT）。
        - 最后 1 个事件固定为 BOSS_COMBAT，确保必须面对最终挑战。

        Args:
            region_config: 区域配置对象（RegionConfig 或 Mock）。
                           若为 None，则使用默认参数。

        Returns:
            EventSequence: 生成的事件序列。
        """
        # 1. 读取配置参数
        event_count_range = cls.DEFAULT_EVENT_COUNT_RANGE
        weights = dict(cls.DEFAULT_WEIGHTS)
        boss_template = "boss_default"
        elite_pool = ["elite_1", "elite_2"]
        normal_pool = ["mob_1", "mob_2"]

        if region_config is not None:
            try:
                count_range = getattr(region_config, 'event_count_range', None)
                if count_range and len(count_range) == 2:
                    event_count_range = (count_range[0], count_range[1])
            except Exception:
                pass

            try:
                boss_template = getattr(region_config, 'boss_template', boss_template)
            except Exception:
                pass

            try:
                elite_pool = getattr(region_config, 'elite_pool', elite_pool) or elite_pool
            except Exception:
                pass

            try:
                normal_pool = getattr(region_config, 'normal_pool', normal_pool) or normal_pool
            except Exception:
                pass

            try:
                cfg_weights = getattr(region_config, 'event_weights', None)
                if cfg_weights and isinstance(cfg_weights, dict):
                    weights = {EventType(k): v for k, v in cfg_weights.items() if k in EventType.__members__}
            except Exception:
                pass

        # 2. 确定总事件数（含末尾 Boss，所以正式随机槽位 = total - 1）
        total_events = random.randint(*event_count_range)
        random_slot_count = max(total_events - 1, 1)  # 至少 1 个随机事件 + 1 个 Boss

        # 3. 加权随机抽取事件类型
        event_types_pool = list(weights.keys())
        event_type_weights = [weights[t] for t in event_types_pool]

        events: List[PveEvent] = []
        for i in range(random_slot_count):
            chosen_type = random.choices(event_types_pool, weights=event_type_weights, k=1)[0]
            event_id = cls._pick_event_id(chosen_type, elite_pool, normal_pool)
            events.append(PveEvent(index=i, event_type=chosen_type, event_id=event_id))

        # 4. 末尾强制追加 Boss 事件
        boss_event = PveEvent(
            index=len(events),
            event_type=EventType.BOSS_COMBAT,
            event_id=boss_template
        )
        events.append(boss_event)

        return EventSequence(events=events, current_index=0)

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
