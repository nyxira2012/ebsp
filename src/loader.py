"""
数据加载器
负责从 JSON 文件读取并解析为 Python 对象
"""

import json
from pathlib import Path
from .models import Pilot, Weapon, Mecha, WeaponType


class DataLoader:
    """数据加载器 - 数据驱动核心"""
    
    def __init__(self, data_dir: str = "data") -> None:
        """
        初始化数据加载器
        
        Args:
            data_dir: 数据文件目录路径
        """
        self.data_dir: Path = Path(data_dir)
        
        # 数据容器
        self.pilots: dict[str, Pilot] = {}
        self.weapons: dict[str, Weapon] = {}
        self.mechas: dict[str, Mecha] = {}
    
    def load_all(self) -> None:
        """加载所有游戏数据。

        按照依赖顺序加载:
        1. 驾驶员数据 (无依赖)
        2. 武器数据 (无依赖)
        3. 机体数据 (依赖驾驶员和武器)

        Raises:
            FileNotFoundError: 当数据文件不存在时
            ValueError: 当引用的驾驶员或武器不存在时
        """
        print("开始加载数据...")

        # 1. 先加载驾驶员 (无依赖)
        self._load_pilots()
        print(f"✓ 已加载 {len(self.pilots)} 个驾驶员")

        # 2. 再加载武器 (无依赖)
        self._load_weapons()
        print(f"✓ 已加载 {len(self.weapons)} 个武器")

        # 3. 最后加载机体 (依赖驾驶员和武器)
        self._load_mechas()
        print(f"✓ 已加载 {len(self.mechas)} 个机体")

        print("数据加载完成!")
    
    def _load_pilots(self) -> None:
        """从 JSON 文件加载驾驶员数据。

        读取 data/pilots.json,解析驾驶员属性并创建 Pilot 对象。
        驾驶员属性包括射击、格斗、觉醒、守备、反应五维数值。

        Raises:
            FileNotFoundError: 当 pilots.json 文件不存在时
            KeyError: 当 JSON 数据缺少必需字段时
        """
        pilot_file: Path = self.data_dir / "pilots.json"

        if not pilot_file.exists():
            raise FileNotFoundError(f"驾驶员数据文件不存在: {pilot_file}")

        with open(pilot_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for pilot_data in data:
            pilot = Pilot(
                id=pilot_data['id'],
                name=pilot_data['name'],
                stat_shooting=pilot_data['stats']['shooting'],
                stat_melee=pilot_data['stats']['melee'],
                stat_awakening=pilot_data['stats']['awakening'],
                stat_defense=pilot_data['stats']['defense'],
                stat_reaction=pilot_data['stats']['reaction'],
                weapon_proficiency=pilot_data.get('proficiency', {}).get('weapon', 500),
                mecha_proficiency=pilot_data.get('proficiency', {}).get('mecha', 2000)
            )
            self.pilots[pilot.id] = pilot
    
    def _load_weapons(self) -> None:
        """从 JSON 文件加载武器数据。

        读取 data/weapons.json,解析武器属性并创建 Weapon 对象。
        武器类型会从字符串转换为 WeaponType 枚举。

        Raises:
            FileNotFoundError: 当 weapons.json 文件不存在时
            KeyError: 当 JSON 数据缺少必需字段或武器类型无效时
        """
        weapon_file: Path = self.data_dir / "weapons.json"

        if not weapon_file.exists():
            raise FileNotFoundError(f"武器数据文件不存在: {weapon_file}")

        with open(weapon_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for weapon_data in data:
            # 解析武器类型
            weapon_type_str: str = weapon_data['type']
            weapon_type: WeaponType = WeaponType[weapon_type_str]  # 枚举名称转换

            weapon = Weapon(
                id=weapon_data['id'],
                name=weapon_data['name'],
                weapon_type=weapon_type,
                power=weapon_data['power'],
                en_cost=weapon_data['en_cost'],
                range_min=weapon_data['range']['min'],
                range_max=weapon_data['range']['max'],
                hit_penalty=weapon_data.get('hit_penalty', 0.0)
            )
            self.weapons[weapon.id] = weapon
    
    def _load_mechas(self) -> None:
        """从 JSON 文件加载机体数据。

        读取 data/mechas.json,解析机体属性并创建 Mecha 对象。
        机体引用驾驶员和武器,会验证这些引用的有效性。

        Raises:
            FileNotFoundError: 当 mechas.json 文件不存在时
            ValueError: 当引用的驾驶员或武器 ID 不存在时
            KeyError: 当 JSON 数据缺少必需字段时
        """
        mecha_file: Path = self.data_dir / "mechas.json"

        if not mecha_file.exists():
            raise FileNotFoundError(f"机体数据文件不存在: {mecha_file}")

        with open(mecha_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for mecha_data in data:
            # 解析驾驶员引用
            pilot_id: str = mecha_data['pilot_id']
            if pilot_id not in self.pilots:
                raise ValueError(f"机体 {mecha_data['id']} 引用了不存在的驾驶员: {pilot_id}")
            pilot: Pilot = self.pilots[pilot_id]

            # 解析武器列表
            weapon_ids: list[str] = mecha_data.get('weapon_ids', [])
            weapons: list[Weapon] = []
            for wpn_id in weapon_ids:
                if wpn_id not in self.weapons:
                    raise ValueError(f"机体 {mecha_data['id']} 引用了不存在的武器: {wpn_id}")
                weapons.append(self.weapons[wpn_id])

            # 创建机体对象
            stats: dict[str, int] = mecha_data['stats']
            attributes: dict[str, float] = mecha_data['attributes']
            defense: dict[str, float | int] = mecha_data['defense']

            mecha = Mecha(
                id=mecha_data['id'],
                name=mecha_data['name'],
                pilot=pilot,
                max_hp=stats['hp'],
                current_hp=stats['hp'],
                max_en=stats['en'],
                current_en=stats['en'],
                hit_rate=attributes['hit'],
                precision=attributes['precision'],
                crit_rate=attributes['crit'],
                dodge_rate=defense['dodge'],
                parry_rate=defense['parry'],
                block_rate=defense['block'],
                defense_level=stats['armor'],
                mobility=stats['mobility'],
                block_value=defense.get('block_val', 0),
                weapons=weapons,
                traits=mecha_data.get('traits', [])
            )

            self.mechas[mecha.id] = mecha
    
    def get_pilot(self, pilot_id: str) -> Pilot:
        """根据 ID 获取驾驶员对象。

        Args:
            pilot_id: 驾驶员的唯一标识符

        Returns:
            Pilot: 对应的驾驶员对象

        Raises:
            KeyError: 当驾驶员 ID 不存在时
        """
        if pilot_id not in self.pilots:
            raise KeyError(f"驾驶员不存在: {pilot_id}")
        return self.pilots[pilot_id]
    
    def get_weapon(self, weapon_id: str) -> Weapon:
        """根据 ID 获取武器对象。

        Args:
            weapon_id: 武器的唯一标识符

        Returns:
            Weapon: 对应的武器对象

        Raises:
            KeyError: 当武器 ID 不存在时
        """
        if weapon_id not in self.weapons:
            raise KeyError(f"武器不存在: {weapon_id}")
        return self.weapons[weapon_id]
    
    def get_mecha(self, mecha_id: str) -> Mecha:
        """根据 ID 获取机体对象。

        Args:
            mecha_id: 机体的唯一标识符

        Returns:
            Mecha: 对应的机体对象

        Raises:
            KeyError: 当机体 ID 不存在时
        """
        if mecha_id not in self.mechas:
            raise KeyError(f"机体不存在: {mecha_id}")
        return self.mechas[mecha_id]
