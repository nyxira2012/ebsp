"""
完整战斗模拟器
================

从配置中随机选择机体、驾驶员、装备和武器，生成完整的战斗快照后进行战斗模拟。

使用公共 API:
- DataLoader: 加载配置数据
- MechaFactory: 生成战斗快照
- BattleSimulator: 执行战斗
- EventMapper / TextRenderer: 演出系统
"""

import sys
import os
import random
import argparse
from typing import List, Optional, Tuple

# 确保导入路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# Windows UTF-8 支持
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.loader import DataLoader
from src.factory import MechaFactory
from src.models import (
    MechaConfig, PilotConfig, SubPilotConfig, EquipmentConfig,
    MechaSnapshot, WeaponType
)


def is_melee_weapon(equip: EquipmentConfig) -> bool:
    """检查装备是否为近战武器

    Args:
        equip: 装备配置

    Returns:
        是否为近战武器
    """
    return equip.type == "WEAPON" and equip.weapon_type == WeaponType.MELEE

from src.combat.engine import BattleSimulator
from src.presentation import EventMapper, TextRenderer


# ============================================================================
# 战斗配置 (用户可直接修改此处配置)
# ============================================================================
#
# 可用机体 ID: mech_rx78, mech_zaku, mech_nu, mech_sazabi
# 可用主驾驶 ID: pilot_amuro, pilot_char, pilot_dummy
# 可用副驾驶 ID: subpilot_sayla, subpilot_four, subpilot_haman
#
# 可用武器 ID: wpn_beam_rifle, wpn_beam_saber, wpn_machine_gun, wpn_heat_axe,
#               wpn_bazooka, wpn_heavy_hammer, wpn_funnel_system, wpn_railgun
# 可用装备 ID: e_booster, e_chobham_armor, e_gundam_armor, e_sazabi_thruster,
#               e_magnetron_coating, e_targeting_sensor, e_power_generator
#
# 留空 "" 表示随机选择
# 使用列表 [] 表示不添加任何物品
# ============================================================================

# A 方配置
CONFIG_MECH_A = ""           # 机体 ID，例: "mech_rx78"
CONFIG_PILOT_A = ""          # 主驾驶 ID，例: "pilot_amuro"
CONFIG_SUB_PILOT_A = ""      # 副驾驶 ID，例: "subpilot_sayla" (留空则随机决定是否添加)

# A 方武器配置（留空则随机，[] 则不添加额外武器）
CONFIG_WEAPONS_A = []        # 额外武器列表，例: ["wpn_beam_saber", "wpn_heavy_hammer"]

# A 方装备配置（留空则随机，[] 则不添加装备）
CONFIG_EQUIPS_A = []         # 装备列表，例: ["e_booster", "e_targeting_sensor"]

# B 方配置
CONFIG_MECH_B = ""           # 机体 ID，例: "mech_zaku"
CONFIG_PILOT_B = ""          # 主驾驶 ID，例: "pilot_char"
CONFIG_SUB_PILOT_B = ""      # 副驾驶 ID，例: "subpilot_haman" (留空则随机决定是否添加)

# B 方武器配置（留空则随机，[] 则不添加额外武器）
CONFIG_WEAPONS_B = []        # 额外武器列表，例: ["wpn_funnel_system"]

# B 方装备配置（留空则随机，[] 则不添加装备）
CONFIG_EQUIPS_B = []         # 装备列表，例: ["e_chobham_armor", "e_sazabi_thruster"]

# 通用配置
CONFIG_RANDOM_SEED = ""      # 随机种子，例: 42 (留空则完全随机)
CONFIG_ENABLE_PRESENTATION = True    # 是否启用演出系统
CONFIG_VERBOSE = True        # 是否显示详细战斗日志

# ============================================================================
# 配置加载
# ============================================================================

# 技能名称缓存（从 skills.json 加载）
_SKILL_NAME_CACHE: dict = {}


def load_skill_names(data_dir: str = "data") -> None:
    """从 skills.json 加载技能名称

    Args:
        data_dir: 数据文件目录路径
    """
    import json
    global _SKILL_NAME_CACHE

    skills_path = os.path.join(data_dir, "skills.json")
    if not os.path.exists(skills_path):
        return

    with open(skills_path, 'r', encoding='utf-8') as f:
        skills_data = json.load(f)

    for skill_id, skill_entries in skills_data.items():
        if skill_entries and isinstance(skill_entries, list):
            # 取第一个条目的 name 字段
            _SKILL_NAME_CACHE[skill_id] = skill_entries[0].get('name', skill_id)


def get_skill_name(skill_id: str) -> str:
    """获取技能的中文名称

    Args:
        skill_id: 技能 ID

    Returns:
        技能中文名称，未找到时返回原 ID
    """
    return _SKILL_NAME_CACHE.get(skill_id, skill_id)


def load_game_data(data_dir: str = "data") -> DataLoader:
    """加载所有游戏配置数据

    Args:
        data_dir: 数据文件目录路径

    Returns:
        DataLoader: 包含所有配置数据的加载器
    """
    loader = DataLoader(data_dir)
    loader.load_all()
    # 同时加载技能名称
    load_skill_names(data_dir)
    return loader


# ============================================================================
# 随机配装系统
# ============================================================================

class LoadoutBuilder:
    """机体配装构建器 - 根据槽位配置选择武器和装备"""

    def __init__(self, loader: DataLoader):
        """初始化配装构建器

        Args:
            loader: 数据加载器，包含所有配置数据
        """
        self.loader = loader

    def build_loadout(
        self,
        mecha_config: MechaConfig,
        pilot_config: Optional[PilotConfig] = None,
        sub_pilot_config: Optional[SubPilotConfig] = None,
        random_seed: Optional[int] = None,
        fixed_weapons: Optional[List[str]] = None,
        fixed_equips: Optional[List[str]] = None
    ) -> List[EquipmentConfig]:
        """为指定机体构建配装列表

        Args:
            mecha_config: 机体配置
            pilot_config: 主驾驶员配置（可选）
            sub_pilot_config: 副驾驶配置（可选）
            random_seed: 随机种子（用于可重复测试）
            fixed_weapons: 用户指定的武器 ID 列表（None 表示随机）
            fixed_equips: 用户指定的装备 ID 列表（None 表示随机）

        Returns:
            配装列表（包含武器和装备）
        """
        if random_seed is not None:
            random.seed(random_seed)

        loadout = []
        # 复制槽位列表，用于跟踪已占用槽位
        available_slots = mecha_config.slots.copy()

        # 辅助函数：根据装备类型确定占用的槽位类型
        def get_slot_type_for_equipment(equip: EquipmentConfig) -> Optional[str]:
            """确定装备应该占用的槽位类型"""
            if equip.type == "WEAPON":
                return "WEAPON"
            elif equip.type == "EQUIP":
                # 检查是否是专属装备
                if equip.compatible_series:
                    return "EXCLUSIVE"
                return "EQUIP"
            return None

        # 辅助函数：尝试占用一个槽位
        def try_occupy_slot(slot_type: str) -> bool:
            """尝试占用一个指定类型的槽位"""
            if slot_type in available_slots:
                available_slots.remove(slot_type)
                return True
            return False

        # 处理机体的固定武器（fixed_weapons）
        # 这些武器会占用对应的槽位
        if fixed_weapons is None:
            # 没有用户指定，使用机体的默认 fixed_weapons
            fixed_weapon_ids = mecha_config.fixed_weapons or []
        else:
            fixed_weapon_ids = fixed_weapons

        for weapon_id in fixed_weapon_ids:
            if weapon_id not in self.loader.equipments:
                continue
            equip = self.loader.equipments[weapon_id]
            slot_type = get_slot_type_for_equipment(equip)
            if slot_type and try_occupy_slot(slot_type):
                loadout.append(equip)
            # 如果没有可用槽位，则不添加该武器

        # 处理用户指定的装备
        if fixed_equips is not None:
            for equip_id in fixed_equips:
                if equip_id not in self.loader.equipments:
                    continue
                equip = self.loader.equipments[equip_id]
                slot_type = get_slot_type_for_equipment(equip)
                if slot_type and try_occupy_slot(slot_type):
                    loadout.append(equip)

        # 为剩余槽位随机选择装备
        for slot_type in available_slots[:]:  # 使用副本遍历
            equip = self.select_equipment_for_slot(
                slot_type, mecha_config, loadout
            )
            if equip:
                loadout.append(equip)
                available_slots.remove(slot_type)

        # 确保至少有一个近战武器
        loadout = self._ensure_melee_weapon(loadout, mecha_config, available_slots)

        return loadout

    def _ensure_melee_weapon(
        self,
        loadout: List[EquipmentConfig],
        mecha_config: MechaConfig,
        available_slots: List[str]
    ) -> List[EquipmentConfig]:
        """确保配装中至少有一个近战武器

        如果当前配装没有近战武器，会尝试：
        1. 从 loader 中找一个近战武器
        2. 如果有可用的 WEAPON 槽位，添加近战武器
        3. 如果没有可用槽位，替换一个非近战武器为近战武器

        Args:
            loadout: 当前配装列表
            mecha_config: 机体配置
            available_slots: 剩余可用槽位列表（会被修改）

        Returns:
            更新后的配装列表
        """
        # 检查是否已有近战武器
        has_melee = any(
            equip.weapon_type == WeaponType.MELEE
            for equip in loadout
            if equip.type == "WEAPON"
        )
        if has_melee:
            return loadout

        # 获取所有可用的近战武器
        mecha_series = mecha_config.series or ""
        melee_weapons = [
            equip for equip in self.loader.equipments.values()
            if equip.type == "WEAPON"
            and equip.weapon_type == WeaponType.MELEE
            and equip not in loadout
        ]

        if not melee_weapons:
            # 没有可用的近战武器，保持原配装
            return loadout

        # 选择一个近战武器
        selected_melee = random.choice(melee_weapons)

        # 尝试找到 WEAPON 槽位来添加近战武器
        if "WEAPON" in available_slots:
            loadout.append(selected_melee)
            available_slots.remove("WEAPON")
        else:
            # 没有可用槽位，尝试替换一个非近战武器
            for i, equip in enumerate(loadout):
                if equip.type == "WEAPON" and equip.weapon_type != WeaponType.MELEE:
                    loadout[i] = selected_melee
                    break

        return loadout

    def select_equipment_for_slot(
        self,
        slot_type: str,
        mecha_config: MechaConfig,
        current_loadout: List[EquipmentConfig]
    ) -> Optional[EquipmentConfig]:
        """为指定槽位选择合适的装备

        Args:
            slot_type: 槽位类型 (WEAPON, EQUIP, EXCLUSIVE, FIXED)
            mecha_config: 机体配置
            current_loadout: 当前已选择的配装

        Returns:
            选中的装备配置，如果没有合适的则返回 None
        """
        if slot_type == "FIXED":
            # FIXED 槽位由 fixed_weapons 处理，这里返回 None
            return None

        mecha_series = mecha_config.series or ""

        # 获取所有可选装备
        candidates = []

        for equip in self.loader.equipments.values():
            # 验证槽位兼容性
            if not self.is_slot_compatible(equip, slot_type, mecha_series):
                continue

            # 检查是否已在配装中（避免重复）
            if equip in current_loadout:
                continue

            candidates.append(equip)

        if not candidates:
            return None

        # 随机选择一个
        return random.choice(candidates)

    def is_slot_compatible(
        self,
        equip: EquipmentConfig,
        slot_type: str,
        mecha_series: str
    ) -> bool:
        """检查装备是否与槽位兼容

        Args:
            equip: 装备配置
            slot_type: 槽位类型
            mecha_series: 机体系列

        Returns:
            是否兼容
        """
        # EXCLUSIVE 槽位需要系列匹配
        if slot_type == "EXCLUSIVE":
            if not equip.compatible_series:
                return False
            return mecha_series in equip.compatible_series

        # WEAPON 槽位需要武器类型
        if slot_type == "WEAPON":
            return equip.type == "WEAPON"

        # EQUIP 槽位需要装备类型
        if slot_type == "EQUIP":
            return equip.type == "EQUIP"

        return False


# ============================================================================
# 快照生成器
# ============================================================================

class MechaSnapshotBuilder:
    """机体快照生成器 - 根据配置生成战斗用的快照"""

    def __init__(self, loader: DataLoader):
        """初始化快照生成器

        Args:
            loader: 数据加载器
        """
        self.loader = loader
        self.loadout_builder = LoadoutBuilder(loader)
        # 追踪实际使用的驾驶员配置
        self._last_pilot_config: Optional[PilotConfig] = None
        self._last_sub_pilot_config: Optional[SubPilotConfig] = None

    def create_random_mecha(
        self,
        mecha_config: Optional[MechaConfig] = None,
        pilot_config: Optional[PilotConfig] = None,
        sub_pilot_config: Optional[SubPilotConfig] = None,
        random_seed: Optional[int] = None,
        fixed_weapons: Optional[List[str]] = None,
        fixed_equips: Optional[List[str]] = None
    ) -> MechaSnapshot:
        """创建随机配装的机体快照

        如果未指定配置，则随机选择。

        Args:
            mecha_config: 机体配置（为 None 时随机选择）
            pilot_config: 主驾驶员配置（为 None 时随机选择）
            sub_pilot_config: 副驾驶配置（为 None 时随机选择）
            random_seed: 随机种子
            fixed_weapons: 用户指定的武器 ID 列表（None 表示随机）
            fixed_equips: 用户指定的装备 ID 列表（None 表示随机）

        Returns:
            机体快照
        """
        if random_seed is not None:
            random.seed(random_seed)

        # 随机选择机体
        if mecha_config is None:
            mecha_config = random.choice(list(self.loader.mechas.values()))

        # 随机选择主驾驶员
        if pilot_config is None:
            pilot_config = random.choice(list(self.loader.pilots.values()))

        # 追踪实际使用的驾驶员
        self._last_pilot_config = pilot_config

        # 随机选择副驾驶（30%概率有副驾驶）
        if sub_pilot_config is None and self.loader.sub_pilots:
            if random.random() < 0.3:
                sub_pilot_config = random.choice(list(self.loader.sub_pilots.values()))

        # 追踪实际使用的副驾驶
        self._last_sub_pilot_config = sub_pilot_config

        # 构建配装（传入用户指定的武器和装备）
        loadout = self.loadout_builder.build_loadout(
            mecha_config, pilot_config, sub_pilot_config,
            fixed_weapons=fixed_weapons,
            fixed_equips=fixed_equips,
            random_seed=random_seed
        )

        # 生成快照
        snapshot = MechaFactory.create_mecha_snapshot(
            mecha_conf=mecha_config,
            pilot_conf=pilot_config,
            equipments=loadout,
            weapon_configs=self.loader.equipments,
            sub_pilot_conf=sub_pilot_config
        )

        return snapshot

    def get_last_pilot_config(self) -> Optional[PilotConfig]:
        """获取最后一次创建快照时使用的驾驶员配置"""
        return self._last_pilot_config

    def get_last_sub_pilot_config(self) -> Optional[SubPilotConfig]:
        """获取最后一次创建快照时使用的副驾驶配置"""
        return self._last_sub_pilot_config

    def create_pair(
        self,
        random_seed: Optional[int] = None
    ) -> Tuple[MechaSnapshot, MechaSnapshot]:
        """创建一对随机机体用于对战

        Args:
            random_seed: 随机种子

        Returns:
            (机体A, 机体B) 元组
        """
        if random_seed is not None:
            random.seed(random_seed)

        # 确保两台机体不同
        mecha_configs = list(self.loader.mechas.values())
        config_a = random.choice(mecha_configs)
        config_b = random.choice([m for m in mecha_configs if m.id != config_a.id])

        # 创建两个快照
        snapshot_a = self.create_random_mecha(
            mecha_config=config_a,
            random_seed=random_seed + 1 if random_seed else None
        )
        pilot_a = self.get_last_pilot_config()
        sub_pilot_a = self.get_last_sub_pilot_config()

        snapshot_b = self.create_random_mecha(
            mecha_config=config_b,
            random_seed=random_seed + 2 if random_seed else None
        )
        pilot_b = self.get_last_pilot_config()
        sub_pilot_b = self.get_last_sub_pilot_config()

        return snapshot_a, snapshot_b, pilot_a, pilot_b, sub_pilot_a, sub_pilot_b


# ============================================================================
# 战斗模拟器包装
# ============================================================================

def run_battle_simulation(
    mecha_a: MechaSnapshot,
    mecha_b: MechaSnapshot,
    verbose: bool = True,
    enable_presentation: bool = True
) -> dict:
    """运行战斗模拟

    Args:
        mecha_a: A 方机体快照
        mecha_b: B 方机体快照
        verbose: 是否输出详细日志
        enable_presentation: 是否启用演出系统

    Returns:
        战斗结果统计字典
    """
    # 创建战斗模拟器
    simulator = BattleSimulator(
        mecha_a=mecha_a,
        mecha_b=mecha_b,
        enable_presentation=enable_presentation,
        verbose=verbose
    )

    # 运行战斗
    simulator.run_battle()

    # 收集结果
    result = {
        "winner": None,
        "loser": None,
        "is_draw": False,
        "rounds": simulator.round_number,
        "mecha_a_final_hp": mecha_a.current_hp,
        "mecha_a_max_hp": mecha_a.final_max_hp,
        "mecha_b_final_hp": mecha_b.current_hp,
        "mecha_b_max_hp": mecha_b.final_max_hp,
    }

    # 判断胜负
    if not mecha_a.is_alive():
        result["winner"] = mecha_b.name
        result["loser"] = mecha_a.name
    elif not mecha_b.is_alive():
        result["winner"] = mecha_a.name
        result["loser"] = mecha_b.name
    else:
        hp_a_pct = mecha_a.get_hp_percentage()
        hp_b_pct = mecha_b.get_hp_percentage()
        if hp_a_pct > hp_b_pct:
            result["winner"] = mecha_a.name
            result["loser"] = mecha_b.name
        elif hp_b_pct > hp_a_pct:
            result["winner"] = mecha_b.name
            result["loser"] = mecha_a.name
        else:
            result["is_draw"] = True

    return result


# ============================================================================
# 主程序
# ============================================================================

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="完整战斗模拟器 - 随机配装与战斗模拟",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python sim_combat.py                    # 使用文件配置（或随机战斗）
  python sim_combat.py --mech-a mech_rx78 --mech-b mech_zaku
  python sim_combat.py --pilot-a pilot_amuro --pilot-b pilot_char
  python sim_combat.py --seed 42           # 使用固定随机种子
  python sim_combat.py --no-presentation   # 禁用演出系统
  python sim_combat.py --quiet            # 静默模式（只输出结果）

注意: 命令行参数会覆盖文件开头的配置
        """
    )

    parser.add_argument(
        "--mech-a", "-ma",
        type=str,
        default=CONFIG_MECH_A if CONFIG_MECH_A else None,
        help="A 方机体 ID（为空时随机选择）"
    )
    parser.add_argument(
        "--mech-b", "-mb",
        type=str,
        default=CONFIG_MECH_B if CONFIG_MECH_B else None,
        help="B 方机体 ID（为空时随机选择）"
    )
    parser.add_argument(
        "--pilot-a", "-pa",
        type=str,
        default=CONFIG_PILOT_A if CONFIG_PILOT_A else None,
        help="A 方驾驶员 ID（为空时随机选择）"
    )
    parser.add_argument(
        "--pilot-b", "-pb",
        type=str,
        default=CONFIG_PILOT_B if CONFIG_PILOT_B else None,
        help="B 方驾驶员 ID（为空时随机选择）"
    )
    parser.add_argument(
        "--sub-pilot-a", "-sa",
        type=str,
        default=CONFIG_SUB_PILOT_A if CONFIG_SUB_PILOT_A else None,
        help="A 方副驾驶 ID"
    )
    parser.add_argument(
        "--sub-pilot-b", "-sb",
        type=str,
        default=CONFIG_SUB_PILOT_B if CONFIG_SUB_PILOT_B else None,
        help="B 方副驾驶 ID"
    )
    parser.add_argument(
        "--seed", "-s",
        type=int,
        default=int(CONFIG_RANDOM_SEED) if CONFIG_RANDOM_SEED and CONFIG_RANDOM_SEED.isdigit() else None,
        help="随机种子（用于可重复测试）"
    )
    parser.add_argument(
        "--no-presentation",
        action="store_true",
        default=not CONFIG_ENABLE_PRESENTATION,
        help="禁用演出系统"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        default=not CONFIG_VERBOSE,
        help="静默模式（只输出结果）"
    )

    args = parser.parse_args()

    # 设置随机种子
    seed = args.seed
    if seed is not None:
        random.seed(seed)

    # 加载数据
    loader = load_game_data()

    # 创建快照构建器
    builder = MechaSnapshotBuilder(loader)

    # 获取指定的机体配置
    mech_a_config = loader.get_mecha_config(args.mech_a) if args.mech_a else None
    mech_b_config = loader.get_mecha_config(args.mech_b) if args.mech_b else None

    # 获取指定的驾驶员配置
    pilot_a_config = loader.get_pilot_config(args.pilot_a) if args.pilot_a else None
    pilot_b_config = loader.get_pilot_config(args.pilot_b) if args.pilot_b else None

    # 获取指定的副驾驶配置
    sub_pilot_a_config = (
        loader.get_sub_pilot_config(args.sub_pilot_a) if args.sub_pilot_a else None
    )
    sub_pilot_b_config = (
        loader.get_sub_pilot_config(args.sub_pilot_b) if args.sub_pilot_b else None
    )

    # 获取武器和装备配置（从文件配置或命令行参数）
    weapons_a = CONFIG_WEAPONS_A if CONFIG_WEAPONS_A else None
    weapons_b = CONFIG_WEAPONS_B if CONFIG_WEAPONS_B else None
    equips_a = CONFIG_EQUIPS_A if CONFIG_EQUIPS_A else None
    equips_b = CONFIG_EQUIPS_B if CONFIG_EQUIPS_B else None

    # 创建机体快照，同时获取实际使用的驾驶员配置
    snapshot_a = builder.create_random_mecha(
        mecha_config=mech_a_config,
        pilot_config=pilot_a_config,
        sub_pilot_config=sub_pilot_a_config,
        random_seed=seed + 1 if seed else None,
        fixed_weapons=weapons_a,
        fixed_equips=equips_a
    )
    actual_pilot_a_config = builder.get_last_pilot_config()
    actual_sub_pilot_a_config = builder.get_last_sub_pilot_config()

    snapshot_b = builder.create_random_mecha(
        mecha_config=mech_b_config,
        pilot_config=pilot_b_config,
        sub_pilot_config=sub_pilot_b_config,
        random_seed=seed + 2 if seed else None,
        fixed_weapons=weapons_b,
        fixed_equips=equips_b
    )
    actual_pilot_b_config = builder.get_last_pilot_config()
    actual_sub_pilot_b_config = builder.get_last_sub_pilot_config()

    # 获取驾驶员名称
    actual_pilot_a_name = actual_pilot_a_config.name if actual_pilot_a_config else "None"
    actual_pilot_b_name = actual_pilot_b_config.name if actual_pilot_b_config else "None"
    actual_sub_pilot_a_name = actual_sub_pilot_a_config.name if actual_sub_pilot_a_config else None
    actual_sub_pilot_b_name = actual_sub_pilot_b_config.name if actual_sub_pilot_b_config else None

    # 显示配装信息
    if not args.quiet:
        print("\n" + "=" * 80)
        print("战斗配装")
        print("=" * 80)
        print(f"\n【A 方】{snapshot_a.mecha_name}")
        print(f"  主驾驶: {actual_pilot_a_name}")
        if actual_sub_pilot_a_name:
            print(f"  副驾驶: {actual_sub_pilot_a_name}")
        print(f"  HP: {snapshot_a.final_max_hp} | EN: {snapshot_a.final_max_en} | 装甲: {snapshot_a.final_armor}")
        print(f"  机动: {snapshot_a.final_mobility} | 命中: {snapshot_a.final_hit} | 精准: {snapshot_a.final_precision:.1f}")
        print(f"  躲闪: {snapshot_a.final_dodge:.1f} | 招架: {snapshot_a.final_parry:.1f} | 格挡: {snapshot_a.final_block:.1f}")
        print(f"  武器 ({len(snapshot_a.weapons)}):")
        for w in snapshot_a.weapons:
            print(f"    - {w.name} (威力:{w.final_power} EN:{w.en_cost} 射程:{w.range_min}-{w.range_max}m)")
        if snapshot_a.skills:
            skill_names = [get_skill_name(s) for s in snapshot_a.skills]
            print(f"  技能: {', '.join(skill_names)}")

        print(f"\n【B 方】{snapshot_b.mecha_name}")
        print(f"  主驾驶: {actual_pilot_b_name}")
        if actual_sub_pilot_b_name:
            print(f"  副驾驶: {actual_sub_pilot_b_name}")
        print(f"  HP: {snapshot_b.final_max_hp} | EN: {snapshot_b.final_max_en} | 装甲: {snapshot_b.final_armor}")
        print(f"  机动: {snapshot_b.final_mobility} | 命中: {snapshot_b.final_hit} | 精准: {snapshot_b.final_precision:.1f}")
        print(f"  躲闪: {snapshot_b.final_dodge:.1f} | 招架: {snapshot_b.final_parry:.1f} | 格挡: {snapshot_b.final_block:.1f}")
        print(f"  武器 ({len(snapshot_b.weapons)}):")
        for w in snapshot_b.weapons:
            print(f"    - {w.name} (威力:{w.final_power} EN:{w.en_cost} 射程:{w.range_min}-{w.range_max}m)")
        if snapshot_b.skills:
            skill_names = [get_skill_name(s) for s in snapshot_b.skills]
            print(f"  技能: {', '.join(skill_names)}")

    # 运行战斗
    result = run_battle_simulation(
        snapshot_a,
        snapshot_b,
        verbose=not args.quiet,
        enable_presentation=not args.no_presentation
    )

    # 显示结果
    if not args.quiet:
        print("\n" + "=" * 80)
        print("战斗结果")
        print("=" * 80)

    if result["is_draw"]:
        print("平局！")
    else:
        print(f"胜者: {result['winner']}")
        print(f"败者: {result['loser']}")

    print(f"战斗回合: {result['rounds']}")
    print(f"A 方 HP: {result['mecha_a_final_hp']}/{result['mecha_a_max_hp']} "
          f"({result['mecha_a_final_hp']/result['mecha_a_max_hp']*100:.1f}%)")
    print(f"B 方 HP: {result['mecha_b_final_hp']}/{result['mecha_b_max_hp']} "
          f"({result['mecha_b_final_hp']/result['mecha_b_max_hp']*100:.1f}%)")


if __name__ == "__main__":
    main()
