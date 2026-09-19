
"""
数据加载器 (Loader)
负责从 JSON 文件读取并解析为 Pydantic 配置模型 (Configs)
"""

import json
from pathlib import Path
from typing import Dict, List, Type, TypeVar
from pydantic import BaseModel

from .models import (
    PilotConfig, SubPilotConfig, EquipmentConfig, MechaConfig,
    WeaponType, MothershipConfig, RegionConfig, AffixConfig, InstanceConfig,
    PracticeScenarioConfig, EnvironmentConfig
)

T = TypeVar('T', bound=BaseModel)

class DataLoader:
    """数据加载器 - 配置表驱动中心"""
    
    def __init__(self, data_dir: str = "data") -> None:
        """
        初始化数据加载器
        
        Args:
            data_dir: 数据文件目录路径
        """
        self.data_dir: Path = Path(data_dir)
        
        # 配置容器 (存储静态配置)
        self.pilots: Dict[str, PilotConfig] = {}
        self.sub_pilots: Dict[str, SubPilotConfig] = {}
        self.equipments: Dict[str, EquipmentConfig] = {} # 包含武器和装备
        self.mechas: Dict[str, MechaConfig] = {}
        self.motherships: Dict[str, MothershipConfig] = {}
        self.regions: Dict[str, RegionConfig] = {}
        self.affixes: Dict[str, AffixConfig] = {}
        self.instances: Dict[str, InstanceConfig] = {}
        self.environments: Dict[str, EnvironmentConfig] = {}
        self.practice_scenarios: Dict[str, PracticeScenarioConfig] = {}

    @property
    def weapons(self) -> Dict[str, EquipmentConfig]:
        """兼容旧测试"""
        return {k: v for k, v in self.equipments.items() if v.type == "WEAPON"}
    
    def load_all(self) -> None:
        """加载所有游戏静态配置。"""
        # 1. 加载驾驶员和副驾驶（从同一个文件，根据 type 区分）
        self._load_pilots_with_sub()

        # 2. 加载装备与武器 (统一为 EquipmentConfig)
        self._load_from_json("equipments.json", EquipmentConfig, self.equipments)
        # 兼容性处理: 如果还有老的 weapons.json，也可以合并进来
        weapons_path = self.data_dir / "weapons.json"
        if weapons_path.exists():
            self._load_from_json("weapons.json", EquipmentConfig, self.equipments)

        # 3. 加载机体配置
        self._load_from_json("mechas.json", MechaConfig, self.mechas)
        
        # 4. 加载母舰配置
        self._load_from_json("motherships.json", MothershipConfig, self.motherships)
        
        # 5. 加载大区域配置
        self._load_from_json("regions.json", RegionConfig, self.regions)
        
        # 6. 加载词条属性配置 (Doc 8)
        self._load_from_json("affixes.json", AffixConfig, self.affixes)

        # 7. 加载副本配置 (Doc 13)
        self._load_from_json("instances.json", InstanceConfig, self.instances)

        # 8. 加载环境配置 (Doc 16 §5.3)：内容级配置，文件缺省=无环境（不阻断启动）
        environments_path = self.data_dir / "environments.json"
        if environments_path.exists():
            self._load_from_json("environments.json", EnvironmentConfig, self.environments, keep_first=True)

        # 9. 加载练习场对局配置 (Doc 16)：内容级配置，文件缺省=无练习场（不阻断启动）
        practice_path = self.data_dir / "practice_scenarios.json"
        if practice_path.exists():
            self._load_from_json("practice_scenarios.json", PracticeScenarioConfig, self.practice_scenarios, keep_first=True)
            self._validate_practice_scenarios()
    
    def _load_from_json(self, filename: str, model_cls: Type[T], container: Dict[str, T],
                        keep_first: bool = False) -> None:
        """通用的 JSON 加载方法

        keep_first（Doc 16 §3 内容级容器撞键先到先得）：仅练习场/环境两个
        内容文件启用；缺省 False 维持后到覆盖的既有语义，其他容器零变化。
        """
        file_path = self.data_dir / filename

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
        except FileNotFoundError:
            # 根据文件类型抛出相应的错误消息
            if "pilots" in filename:
                raise FileNotFoundError(f"驾驶员数据文件不存在: {file_path}")
            elif "weapons" in filename or "equipments" in filename:
                raise FileNotFoundError(f"武器数据文件不存在: {file_path}")
            elif "mechas" in filename:
                raise FileNotFoundError(f"机体数据文件不存在: {file_path}")
            else:
                raise FileNotFoundError(f"配置文件不存在: {file_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件格式错误: {file_path}, 错误: {e}") from e

        # Pydantic 2.x 使用 model_validate, 1.x 使用 parse_obj
        # 考虑到当前环境，使用通用的转换方式
        for item in raw_data:
            # Pydantic 会自动处理嵌套字典和枚举
            try:
                obj = model_cls.model_validate(item)
                # 所有具体的配置类都有 id 属性（BaseModel 层面未声明，压类型告警）
                obj_id = obj.id  # type: ignore
                if keep_first and obj_id in container:
                    print(f"{filename} 中 id 撞键，保留先到条目，已剔除后到: "
                          f"{obj_id} (name={item.get('name', 'unknown')})")
                    continue
                container[obj_id] = obj
            except Exception as e:
                print(f"加载 {filename} 中的项失败: {item.get('id', 'unknown')}. 错误: {e}")

    def _validate_practice_scenarios(self) -> None:
        """剔除引用了不存在机体/环境的练习场条目（配置错误在加载期暴露，不进运行时）"""
        invalid_ids = [
            sid for sid, s in self.practice_scenarios.items()
            if s.mecha_a_id not in self.mechas or s.mecha_b_id not in self.mechas
            or s.environment_id not in self.environments
        ]
        for sid in invalid_ids:
            scenario = self.practice_scenarios.pop(sid)
            print(f"练习场配置引用了不存在的机体或环境，已剔除: {sid} "
                  f"(a={scenario.mecha_a_id}, b={scenario.mecha_b_id}, env={scenario.environment_id})")

    def _load_pilots_with_sub(self) -> None:
        """加载驾驶员和副驾驶配置，根据 type 字段区分"""
        file_path = self.data_dir / "pilots.json"
        if not file_path.exists():
            raise FileNotFoundError(f"驾驶员数据文件不存在: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        for item in raw_data:
            try:
                # 根据 type 字段决定使用哪个模型
                pilot_type = item.get('type', 'MAIN')
                if pilot_type == 'SUB':
                    obj = SubPilotConfig.model_validate(item)
                    self.sub_pilots[obj.id] = obj
                else:
                    obj = PilotConfig.model_validate(item)
                    self.pilots[obj.id] = obj
            except Exception as e:
                print(f"加载 pilots.json 中的项失败: {item.get('id', 'unknown')}. 错误: {e}")

    # ============= 获取方法 =============
    
    def get_pilot_config(self, pilot_id: str) -> PilotConfig:
        if pilot_id not in self.pilots:
            raise KeyError(f"驾驶员配置不存在: {pilot_id}")
        return self.pilots[pilot_id]

    def get_sub_pilot_config(self, sub_pilot_id: str) -> SubPilotConfig:
        if sub_pilot_id not in self.sub_pilots:
            raise KeyError(f"副驾驶员配置不存在: {sub_pilot_id}")
        return self.sub_pilots[sub_pilot_id]

    def get_equipment_config(self, equip_id: str) -> EquipmentConfig:
        if equip_id not in self.equipments:
            raise KeyError(f"装备/武器配置不存在: {equip_id}")
        return self.equipments[equip_id]
        
    def get_mecha_config(self, mecha_id: str) -> MechaConfig:
        if mecha_id not in self.mechas:
            raise KeyError(f"机体配置不存在: {mecha_id}")
        return self.mechas[mecha_id]

    def get_mothership_config(self, mothership_id: str) -> MothershipConfig:
        if mothership_id not in self.motherships:
            raise KeyError(f"母舰配置不存在: {mothership_id}")
        return self.motherships[mothership_id]

    def get_region_config(self, region_id: str) -> RegionConfig:
        if region_id not in self.regions:
            raise KeyError(f"大区域配置不存在: {region_id}")
        return self.regions[region_id]

    def get_zone_config(self, region_id: str, zone_id: str):
        region = self.get_region_config(region_id)
        for zone in region.zones:
            if zone.zone_id == zone_id:
                return zone
        raise KeyError(f"子区域配置不存在: {region_id} -> {zone_id}")

    def get_affix_config(self, affix_id: str) -> AffixConfig:
        if affix_id not in self.affixes:
            raise KeyError(f"词条配置不存在: {affix_id}")
        return self.affixes[affix_id]

    def get_instance_config(self, instance_id: str) -> InstanceConfig:
        """获取副本配置 (Doc 13)"""
        if instance_id not in self.instances:
            raise KeyError(f"副本配置不存在: {instance_id}")
        return self.instances[instance_id]

    def get_instance_zone_config(self, instance_id: str, zone_id: str):
        """获取副本子区域配置"""
        instance = self.get_instance_config(instance_id)
        if zone_id not in instance.zones:
            raise KeyError(f"副本子区域配置不存在: {instance_id} -> {zone_id}")
        return instance.zones[zone_id]

    def get_environment_config(self, environment_id: str) -> EnvironmentConfig:
        """获取环境配置 (Doc 16 §5.3 环境通道)"""
        if environment_id not in self.environments:
            raise KeyError(f"环境配置不存在: {environment_id}")
        return self.environments[environment_id]

    def get_all_weapons(self) -> List[EquipmentConfig]:
        """筛选所有类型为 WEAPON 的配置"""
        return [e for e in self.equipments.values() if e.type == "WEAPON"]

    def get_all_practice_scenarios(self) -> List[PracticeScenarioConfig]:
        """练习场对局列表（保持配置文件顺序，Doc 16）"""
        return list(self.practice_scenarios.values())

    # ============= 兼容性方法 (用于测试) =============
    
    def _load_pilots(self) -> None: self._load_from_json("pilots.json", PilotConfig, self.pilots)
    def _load_weapons(self) -> None: self._load_from_json("equipments.json", EquipmentConfig, self.equipments)
    def _load_mechas(self) -> None: self._load_from_json("mechas.json", MechaConfig, self.mechas)

    def get_pilot(self, pid: str) -> PilotConfig: return self.get_pilot_config(pid)
    def get_weapon(self, wid: str) -> EquipmentConfig: return self.get_equipment_config(wid)
    def get_mecha(self, mid: str) -> MechaConfig: return self.get_mecha_config(mid)
