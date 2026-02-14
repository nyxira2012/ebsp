"""
测试数据加载器 (loader.py)
覆盖 DataLoader 的数据加载和查询功能
"""

import pytest
import json
import tempfile
from pathlib import Path
from src.loader import DataLoader
from src.models import Pilot, Weapon, Mecha, WeaponType


# ============================================================================
# Fixtures - 创建临时测试数据
# ============================================================================

@pytest.fixture
def temp_data_dir():
    """创建临时测试数据目录"""
    import tempfile
    import shutil

    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)

    # 创建测试数据文件
    # 1. pilots.json (PilotConfig - Pydantic v2)
    pilots_data = [
        {
            "id": "p_amuro",
            "name": "阿姆罗",
            "portrait_id": "p_amuro",
            "stat_shooting": 180,
            "stat_melee": 150,
            "stat_awakening": 120,
            "stat_defense": 100,
            "stat_reaction": 160,
            "innate_skills": []
        },
        {
            "id": "p_char",
            "name": "夏亚",
            "portrait_id": "p_char",
            "stat_shooting": 170,
            "stat_melee": 160,
            "stat_awakening": 150,
            "stat_defense": 110,
            "stat_reaction": 150,
            "innate_skills": []
        },
        {
            "id": "p_bright",
            "name": "布莱特",
            "portrait_id": "p_bright",
            "stat_shooting": 120,
            "stat_melee": 100,
            "stat_awakening": 80,
            "stat_defense": 130,
            "stat_reaction": 110,
            "innate_skills": []
        }
    ]

    pilots_file = temp_path / "pilots.json"
    with open(pilots_file, 'w', encoding='utf-8') as f:
        json.dump(pilots_data, f, ensure_ascii=False, indent=2)

    # 2. equipments.json (EquipmentConfig - Pydantic v2)
    equipments_data = [
        {
            "id": "w_beam_rifle",
            "name": "光束步枪",
            "type": "WEAPON",
            "weapon_type": "射击",
            "weapon_power": 1200,
            "weapon_range_min": 1000,
            "weapon_range_max": 6000,
            "weapon_en_cost": 10,
            "weapon_anim_id": "a_beam_rifle"
        },
        {
            "id": "w_bazooka",
            "name": "火箭筒",
            "type": "WEAPON",
            "weapon_type": "特殊",
            "weapon_power": 2500,
            "weapon_range_min": 2000,
            "weapon_range_max": 5000,
            "weapon_en_cost": 25,
            "weapon_anim_id": "a_bazooka"
        },
        {
            "id": "w_beam_saber",
            "name": "光束军刀",
            "type": "WEAPON",
            "weapon_type": "格斗",
            "weapon_power": 1800,
            "weapon_range_min": 0,
            "weapon_range_max": 1500,
            "weapon_en_cost": 15,
            "weapon_anim_id": "a_beam_saber"
        }
    ]

    equipments_file = temp_path / "equipments.json"
    with open(equipments_file, 'w', encoding='utf-8') as f:
        json.dump(equipments_data, f, ensure_ascii=False, indent=2)

    # 3. mechas.json (MechaConfig - Pydantic v2)
    mechas_data = [
        {
            "id": "m_rx78",
            "name": "RX-78高达",
            "portrait_id": "p_m_rx78",
            "model_asset": "gundam_rx78",
            "init_hp": 5000,
            "init_en": 100,
            "init_armor": 1000,
            "init_mobility": 100,
            "init_hit": 10.0,
            "init_precision": 10.0,
            "init_crit": 5.0,
            "init_dodge": 10.0,
            "init_parry": 10.0,
            "init_block": 10.0,
            "init_block_red": 500,
            "slots": ["WEAPON", "WEAPON"],
            "fixed_weapons": ["w_beam_rifle", "w_beam_saber"]
        },
        {
            "id": "m_sazabi",
            "name": "沙扎比",
            "portrait_id": "p_m_sazabi",
            "model_asset": "sazabi",
            "init_hp": 6000,
            "init_en": 120,
            "init_armor": 1200,
            "init_mobility": 90,
            "init_hit": 15.0,
            "init_precision": 12.0,
            "init_crit": 8.0,
            "init_dodge": 15.0,
            "init_parry": 12.0,
            "init_block": 8.0,
            "init_block_red": 400,
            "slots": ["WEAPON"],
            "fixed_weapons": ["w_bazooka"]
        },
        {
            "id": "m_white_base",
            "name": "白色基地",
            "portrait_id": "p_m_wb",
            "model_asset": "white_base",
            "init_hp": 10000,
            "init_en": 200,
            "init_armor": 2000,
            "init_mobility": 50,
            "init_hit": 5.0,
            "init_precision": 5.0,
            "init_crit": 0.0,
            "init_dodge": 5.0,
            "init_parry": 5.0,
            "init_block": 20.0,
            "init_block_red": 1000,
            "slots": [],
            "fixed_weapons": []
        }
    ]

    mechas_file = temp_path / "mechas.json"
    with open(mechas_file, 'w', encoding='utf-8') as f:
        json.dump(mechas_data, f, ensure_ascii=False, indent=2)

    yield temp_path

    # 清理临时目录
    shutil.rmtree(temp_dir)


@pytest.fixture
def loader(temp_data_dir):
    """创建数据加载器"""
    return DataLoader(data_dir=str(temp_data_dir))


# ============================================================================
# 测试初始化
# ============================================================================

class TestDataLoaderInitialization:
    """测试DataLoader初始化"""

    def test_init_with_default_dir(self):
        """测试使用默认目录初始化"""
        loader = DataLoader()
        assert loader.data_dir == Path("data")
        assert len(loader.pilots) == 0
        assert len(loader.weapons) == 0
        assert len(loader.mechas) == 0

    def test_init_with_custom_dir(self):
        """测试使用自定义目录初始化"""
        loader = DataLoader(data_dir="custom_data")
        assert loader.data_dir == Path("custom_data")

    def test_data_containers_initially_empty(self, temp_data_dir):
        """测试数据容器初始为空"""
        loader = DataLoader(data_dir=str(temp_data_dir))
        assert len(loader.pilots) == 0
        assert len(loader.weapons) == 0
        assert len(loader.mechas) == 0


# ============================================================================
# 测试加载驾驶员数据
# ============================================================================

class TestLoadPilots:
    """测试加载驾驶员数据"""

    def test_load_pilots_success(self, loader):
        """测试成功加载驾驶员"""
        loader._load_pilots()

        assert len(loader.pilots) == 3
        assert "p_amuro" in loader.pilots
        assert "p_char" in loader.pilots
        assert "p_bright" in loader.pilots

    def test_pilot_data_correctness(self, loader):
        """测试驾驶员数据正确性"""
        loader._load_pilots()

        amuro = loader.pilots["p_amuro"]
        assert amuro.name == "阿姆罗"
        assert amuro.stat_shooting == 180
        assert amuro.stat_melee == 150
        assert amuro.stat_awakening == 120
        assert amuro.stat_defense == 100
        assert amuro.stat_reaction == 160
        # 熟练度字段 (weapon_proficiency, mecha_proficiency) 保留在 PilotConfig 中
        # 用于计算武器命中惩罚和机体防御率

    def test_pilot_portrait_id(self, loader):
        """测试驾驶员头像ID"""
        loader._load_pilots()

        amuro = loader.pilots["p_amuro"]
        assert amuro.portrait_id == "p_amuro"

    def test_load_pilots_file_not_found(self):
        """测试文件不存在错误"""
        loader = DataLoader(data_dir="nonexistent_dir")

        with pytest.raises(FileNotFoundError, match="驾驶员数据文件不存在"):
            loader._load_pilots()


# ============================================================================
# 测试加载武器数据
# ============================================================================

class TestLoadWeapons:
    """测试加载武器数据"""

    def test_load_weapons_success(self, loader):
        """测试成功加载武器"""
        loader._load_weapons()

        assert len(loader.weapons) == 3
        assert "w_beam_rifle" in loader.weapons
        assert "w_bazooka" in loader.weapons
        assert "w_beam_saber" in loader.weapons

    def test_weapon_data_correctness(self, loader):
        """测试武器数据正确性"""
        loader._load_weapons()

        rifle = loader.weapons["w_beam_rifle"]
        assert rifle.name == "光束步枪"
        assert rifle.weapon_type == WeaponType.SHOOTING  # 新的枚举值
        assert rifle.weapon_power == 1200  # 字段名改变
        assert rifle.weapon_en_cost == 10  # 字段名改变
        assert rifle.weapon_range_min == 1000  # 字段名改变
        assert rifle.weapon_range_max == 6000  # 字段名改变
        assert rifle.weapon_anim_id == "a_beam_rifle"

    def test_weapon_type_parsing(self, loader):
        """测试武器类型解析"""
        loader._load_weapons()

        assert loader.weapons["w_beam_rifle"].weapon_type == WeaponType.SHOOTING
        assert loader.weapons["w_bazooka"].weapon_type == WeaponType.SPECIAL
        assert loader.weapons["w_beam_saber"].weapon_type == WeaponType.MELEE

    def test_load_weapons_file_not_found(self):
        """测试文件不存在错误"""
        loader = DataLoader(data_dir="nonexistent_dir")

        with pytest.raises(FileNotFoundError, match="武器数据文件不存在"):
            loader._load_weapons()


# ============================================================================
# 测试加载机体数据
# ============================================================================

class TestLoadMechas:
    """测试加载机体数据"""

    def test_load_mechas_success(self, loader):
        """测试成功加载机体"""
        loader.load_all()  # 需要先加载驾驶员和武器

        assert len(loader.mechas) == 3
        assert "m_rx78" in loader.mechas
        assert "m_sazabi" in loader.mechas
        assert "m_white_base" in loader.mechas

    def test_mecha_data_correctness(self, loader):
        """测试机体数据正确性"""
        loader._load_mechas()

        rx78 = loader.mechas["m_rx78"]
        assert rx78.name == "RX-78高达"
        assert rx78.init_hp == 5000  # 字段名改变
        assert rx78.init_en == 100  # 字段名改变
        assert rx78.init_armor == 1000  # 字段名改变
        assert rx78.init_mobility == 100  # 字段名改变
        assert rx78.init_hit == 10.0  # 字段名改变
        assert rx78.init_precision == 10.0  # 字段名改变
        assert rx78.init_crit == 5.0  # 字段名改变
        assert rx78.init_dodge == 10.0  # 字段名改变
        assert rx78.init_parry == 10.0  # 字段名改变
        assert rx78.init_block == 10.0  # 字段名改变
        assert rx78.init_block_red == 500  # 字段名改变
        assert rx78.portrait_id == "p_m_rx78"
        assert rx78.model_asset == "gundam_rx78"

    def test_mecha_slots_and_weapons(self, loader):
        """测试机体槽位和内置武器"""
        loader._load_mechas()

        rx78 = loader.mechas["m_rx78"]
        assert rx78.slots == ["WEAPON", "WEAPON"]
        assert rx78.fixed_weapons == ["w_beam_rifle", "w_beam_saber"]

        white_base = loader.mechas["m_white_base"]
        assert white_base.slots == []
        assert white_base.fixed_weapons == []

    def test_load_mechas_file_not_found(self):
        """测试文件不存在错误"""
        loader = DataLoader(data_dir="nonexistent_dir")

        with pytest.raises(FileNotFoundError, match="机体数据文件不存在"):
            loader._load_mechas()


# ============================================================================
# 测试依赖验证
# ============================================================================

class TestDependencyValidation:
    """测试依赖关系验证"""
    # 注意：新的 MechaConfig 只存储 ID 字符串，不存储对象引用
    # 依赖验证在工厂层面处理，不在 DataLoader 中
    pass


# ============================================================================
# 测试数据查询
# ============================================================================

class TestDataQueries:
    """测试数据查询方法"""

    def test_get_pilot_success(self, loader):
        """测试成功获取驾驶员"""
        loader.load_all()

        pilot = loader.get_pilot("p_amuro")
        assert pilot.id == "p_amuro"
        assert pilot.name == "阿姆罗"

    def test_get_pilot_not_found(self, loader):
        """测试获取不存在的驾驶员"""
        loader.load_all()

        with pytest.raises(KeyError, match="驾驶员配置不存在"):
            loader.get_pilot("nonexistent")

    def test_get_weapon_success(self, loader):
        """测试成功获取武器"""
        loader.load_all()

        weapon = loader.get_weapon("w_beam_rifle")
        assert weapon.id == "w_beam_rifle"
        assert weapon.name == "光束步枪"

    def test_get_weapon_not_found(self, loader):
        """测试获取不存在的武器"""
        loader.load_all()

        with pytest.raises(KeyError, match="装备/武器配置不存在"):
            loader.get_weapon("nonexistent")

    def test_get_mecha_success(self, loader):
        """测试成功获取机体"""
        loader.load_all()

        mecha = loader.get_mecha("m_rx78")
        assert mecha.id == "m_rx78"
        assert mecha.name == "RX-78高达"

    def test_get_mecha_not_found(self, loader):
        """测试获取不存在的机体"""
        loader.load_all()

        with pytest.raises(KeyError, match="机体配置不存在"):
            loader.get_mecha("nonexistent")


# ============================================================================
# 测试load_all方法
# ============================================================================

class TestLoadAll:
    """测试load_all方法"""

    def test_load_all_loads_everything(self, loader):
        """测试load_all加载所有数据"""
        loader.load_all()

        assert len(loader.pilots) == 3
        assert len(loader.weapons) == 3
        assert len(loader.mechas) == 3

    def test_load_all_dependencies_order(self, loader):
        """测试加载顺序（依赖关系）"""
        # 机体依赖驾驶员和武器（通过ID引用）
        loader.load_all()

        # 验证所有配置都加载成功
        assert len(loader.pilots) == 3
        assert len(loader.equipments) == 3
        assert len(loader.mechas) == 3


# ============================================================================
# 测试边界条件
# ============================================================================

class TestEdgeCases:
    """测试边界条件"""

    def test_empty_pilots_list(self, temp_data_dir):
        """测试空的驾驶员列表"""
        pilots_file = temp_data_dir / "pilots.json"
        with open(pilots_file, 'w', encoding='utf-8') as f:
            json.dump([], f)

        loader = DataLoader(data_dir=str(temp_data_dir))
        loader._load_pilots()

        assert len(loader.pilots) == 0

    def test_empty_weapons_list(self, temp_data_dir):
        """测试空的武器列表"""
        equipments_file = temp_data_dir / "equipments.json"
        with open(equipments_file, 'w', encoding='utf-8') as f:
            json.dump([], f)

        loader = DataLoader(data_dir=str(temp_data_dir))
        loader._load_weapons()

        assert len(loader.weapons) == 0

    def test_empty_mechas_list(self, temp_data_dir):
        """测试空的机体列表"""
        # 先加载驾驶员和武器
        pilots_data = [{
            "id": "p_test",
            "name": "Test",
            "portrait_id": "p_test",
            "stat_shooting": 100,
            "stat_melee": 100,
            "stat_awakening": 100,
            "stat_defense": 100,
            "stat_reaction": 100
        }]
        (temp_data_dir / "pilots.json").write_text(json.dumps(pilots_data), encoding='utf-8')

        equipments_data = [{
            "id": "w_test",
            "name": "Test Weapon",
            "type": "WEAPON",
            "weapon_type": "射击",
            "weapon_power": 1000,
            "weapon_range_min": 1,
            "weapon_range_max": 100,
            "weapon_en_cost": 10,
            "weapon_anim_id": "test_anim"
        }]
        (temp_data_dir / "equipments.json").write_text(json.dumps(equipments_data), encoding='utf-8')

        mechas_file = temp_data_dir / "mechas.json"
        with open(mechas_file, 'w', encoding='utf-8') as f:
            json.dump([], f)

        loader = DataLoader(data_dir=str(temp_data_dir))
        loader.load_all()

        assert len(loader.mechas) == 0
