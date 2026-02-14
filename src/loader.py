
"""
数据加载器 (Loader)
负责从 JSON 文件读取并解析为 Pydantic 配置模型 (Configs)
"""

import json
from pathlib import Path
from typing import Dict, List, Type, TypeVar
from pydantic import BaseModel

from .models import (
    PilotConfig, EquipmentConfig, MechaConfig, 
    WeaponType # 导入用于校验或转换
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
        self.equipments: Dict[str, EquipmentConfig] = {} # 包含武器和装备
        self.mechas: Dict[str, MechaConfig] = {}

    @property
    def weapons(self) -> Dict[str, EquipmentConfig]:
        """兼容旧测试"""
        return {k: v for k, v in self.equipments.items() if v.type == "WEAPON"}
    
    def load_all(self) -> None:
        """加载所有游戏静态配置。"""
        # 1. 加载驾驶员
        self._load_from_json("pilots.json", PilotConfig, self.pilots)

        # 2. 加载装备与武器 (统一为 EquipmentConfig)
        self._load_from_json("equipments.json", EquipmentConfig, self.equipments)
        # 兼容性处理: 如果还有老的 weapons.json，也可以合并进来
        weapons_path = self.data_dir / "weapons.json"
        if weapons_path.exists():
            self._load_from_json("weapons.json", EquipmentConfig, self.equipments)

        # 3. 加载机体配置
        self._load_from_json("mechas.json", MechaConfig, self.mechas)
    
    def _load_from_json(self, filename: str, model_cls: Type[T], container: Dict[str, T]) -> None:
        """通用的 JSON 加载方法"""
        file_path = self.data_dir / filename
        if not file_path.exists():
            # 根据文件类型抛出相应的错误消息
            if "pilots" in filename:
                raise FileNotFoundError(f"驾驶员数据文件不存在: {file_path}")
            elif "weapons" in filename or "equipments" in filename:
                raise FileNotFoundError(f"武器数据文件不存在: {file_path}")
            elif "mechas" in filename:
                raise FileNotFoundError(f"机体数据文件不存在: {file_path}")
            else:
                raise FileNotFoundError(f"配置文件不存在: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            
        # Pydantic 2.x 使用 model_validate, 1.x 使用 parse_obj
        # 考虑到当前环境，使用通用的转换方式
        for item in raw_data:
            # Pydantic 会自动处理嵌套字典和枚举
            try:
                obj = model_cls.model_validate(item)
                # 所有具体的配置类都有 id 属性
                container[obj.id] = obj  # type: ignore
            except Exception as e:
                print(f"加载 {filename} 中的项失败: {item.get('id', 'unknown')}. 错误: {e}")

    # ============= 获取方法 =============
    
    def get_pilot_config(self, pilot_id: str) -> PilotConfig:
        if pilot_id not in self.pilots:
            raise KeyError(f"驾驶员配置不存在: {pilot_id}")
        return self.pilots[pilot_id]
        
    def get_equipment_config(self, equip_id: str) -> EquipmentConfig:
        if equip_id not in self.equipments:
            raise KeyError(f"装备/武器配置不存在: {equip_id}")
        return self.equipments[equip_id]
        
    def get_mecha_config(self, mecha_id: str) -> MechaConfig:
        if mecha_id not in self.mechas:
            raise KeyError(f"机体配置不存在: {mecha_id}")
        return self.mechas[mecha_id]

    def get_all_weapons(self) -> List[EquipmentConfig]:
        """筛选所有类型为 WEAPON 的配置"""
        return [e for e in self.equipments.values() if e.type == "WEAPON"]

    # ============= 兼容性方法 (用于测试) =============
    
    def _load_pilots(self) -> None: self._load_from_json("pilots.json", PilotConfig, self.pilots)
    def _load_weapons(self) -> None: self._load_from_json("equipments.json", EquipmentConfig, self.equipments)
    def _load_mechas(self) -> None: self._load_from_json("mechas.json", MechaConfig, self.mechas)

    def get_pilot(self, pid: str) -> PilotConfig: return self.get_pilot_config(pid)
    def get_weapon(self, wid: str) -> EquipmentConfig: return self.get_equipment_config(wid)
    def get_mecha(self, mid: str) -> MechaConfig: return self.get_mecha_config(mid)
