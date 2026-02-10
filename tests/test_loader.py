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
    # 1. pilots.json
    pilots_data = [
        {
            "id": "p_amuro",
            "name": "阿姆罗",
            "stats": {
                "shooting": 180,
                "melee": 150,
                "awakening": 120,
                "defense": 100,
                "reaction": 160
            },
            "proficiency": {
                "weapon": 800,
                "mecha": 3000
            }
        },
        {
            "id": "p_char",
            "name": "夏亚",
            "stats": {
                "shooting": 170,
                "melee": 160,
                "awakening": 150,
                "defense": 110,
                "reaction": 150
            },
            "proficiency": {
                "weapon": 900,
                "mecha": 2800
            }
        },
        {
            "id": "p_bright",  # 没有proficiency字段
            "name": "布莱特",
            "stats": {
                "shooting": 120,
                "melee": 100,
                "awakening": 80,
                "defense": 130,
                "reaction": 110
            }
        }
    ]

    pilots_file = temp_path / "pilots.json"
    with open(pilots_file, 'w', encoding='utf-8') as f:
        json.dump(pilots_data, f, ensure_ascii=False, indent=2)

    # 2. weapons.json
    weapons_data = [
        {
            "id": "w_beam_rifle",
            "name": "光束步枪",
            "type": "RIFLE",
            "power": 1200,
            "en_cost": 10,
            "range": {"min": 1000, "max": 6000},
            "hit_penalty": 0.0
        },
        {
            "id": "w_bazooka",
            "name": "火箭筒",
            "type": "HEAVY",
            "power": 2500,
            "en_cost": 25,
            "range": {"min": 2, "max": 5}
            # 没有hit_penalty字段
        },
        {
            "id": "w_beam_saber",
            "name": "光束军刀",
            "type": "MELEE",
            "power": 1800,
            "en_cost": 15,
            "range": {"min": 1000, "max": 1800},
            "hit_penalty": 5.0
        }
    ]

    weapons_file = temp_path / "weapons.json"
    with open(weapons_file, 'w', encoding='utf-8') as f:
        json.dump(weapons_data, f, ensure_ascii=False, indent=2)

    # 3. mechas.json
    mechas_data = [
        {
            "id": "m_rx78",
            "name": "RX-78高达",
            "pilot_id": "p_amuro",
            "weapon_ids": ["w_beam_rifle", "w_beam_saber"],
            "stats": {
                "hp": 5000,
                "en": 100,
                "armor": 1000,
                "mobility": 100
            },
            "attributes": {
                "hit": 10.0,
                "precision": 10.0,
                "crit": 5.0
            },
            "defense": {
                "dodge": 10.0,
                "parry": 10.0,
                "block": 10.0,
                "block_val": 500
            },
            "traits": ["trait_newtype"]
        },
        {
            "id": "m_sazabi",
            "name": "沙扎比",
            "pilot_id": "p_char",
            "weapon_ids": ["w_bazooka"],
            "stats": {
                "hp": 6000,
                "en": 120,
                "armor": 1200,
                "mobility": 90
            },
            "attributes": {
                "hit": 15.0,
                "precision": 12.0,
                "crit": 8.0
            },
            "defense": {
                "dodge": 15.0,
                "parry": 12.0,
                "block": 8.0
            }
            # 没有traits字段
        },
        {
            "id": "m_white_base",
            "name": "白色基地",
            "pilot_id": "p_bright",
            "weapon_ids": [],  # 没有武器
            "stats": {
                "hp": 10000,
                "en": 200,
                "armor": 2000,
                "mobility": 50
            },
            "attributes": {
                "hit": 5.0,
                "precision": 5.0,
                "crit": 0.0
            },
            "defense": {
                "dodge": 5.0,
                "parry": 5.0,
                "block": 20.0,
                "block_val": 1000
            }
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
        assert amuro.weapon_proficiency == 800
        assert amuro.mecha_proficiency == 3000

    def test_pilot_default_proficiency(self, loader):
        """测试默认熟练度"""
        loader._load_pilots()

        bright = loader.pilots["p_bright"]
        assert bright.weapon_proficiency == 500  # 默认值
        assert bright.mecha_proficiency == 2000  # 默认值

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
        assert rifle.weapon_type == WeaponType.RIFLE
        assert rifle.power == 1200
        assert rifle.en_cost == 10
        assert rifle.range_min == 1000
        assert rifle.range_max == 6000
        assert rifle.hit_penalty == 0.0

    def test_weapon_default_hit_penalty(self, loader):
        """测试默认命中惩罚"""
        loader._load_weapons()

        bazooka = loader.weapons["w_bazooka"]
        assert bazooka.hit_penalty == 0.0  # 默认值

    def test_weapon_type_parsing(self, loader):
        """测试武器类型解析"""
        loader._load_weapons()

        assert loader.weapons["w_beam_rifle"].weapon_type == WeaponType.RIFLE
        assert loader.weapons["w_bazooka"].weapon_type == WeaponType.HEAVY
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
        loader.load_all()

        rx78 = loader.mechas["m_rx78"]
        assert rx78.name == "RX-78高达"
        assert rx78.max_hp == 5000
        assert rx78.current_hp == 5000
        assert rx78.max_en == 100
        assert rx78.current_en == 100
        assert rx78.hit_rate == 10.0
        assert rx78.precision == 10.0
        assert rx78.crit_rate == 5.0
        assert rx78.dodge_rate == 10.0
        assert rx78.parry_rate == 10.0
        assert rx78.block_rate == 10.0
        assert rx78.defense_level == 1000
        assert rx78.mobility == 100
        assert rx78.block_value == 500

    def test_mecha_pilot_reference(self, loader):
        """测试机体驾驶员引用"""
        loader.load_all()

        rx78 = loader.mechas["m_rx78"]
        assert rx78.pilot.id == "p_amuro"
        assert rx78.pilot.name == "阿姆罗"

    def test_mecha_weapons_list(self, loader):
        """测试机体武器列表"""
        loader.load_all()

        rx78 = loader.mechas["m_rx78"]
        assert len(rx78.weapons) == 2
        assert rx78.weapons[0].id == "w_beam_rifle"
        assert rx78.weapons[1].id == "w_beam_saber"

    def test_mecha_empty_weapons(self, loader):
        """测试机体无武器"""
        loader.load_all()

        white_base = loader.mechas["m_white_base"]
        assert len(white_base.weapons) == 0

    def test_mecha_traits(self, loader):
        """测试机体特性"""
        loader.load_all()

        rx78 = loader.mechas["m_rx78"]
        assert rx78.traits == ["trait_newtype"]

    def test_mecha_no_traits_field(self, loader):
        """测试机体无traits字段"""
        loader.load_all()

        sazabi = loader.mechas["m_sazabi"]
        assert sazabi.traits == []  # 默认为空列表

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

    def test_mecha_with_invalid_pilot_id(self, temp_data_dir):
        """测试引用不存在的驾驶员"""
        # 创建错误的mechas.json
        mechas_data = [{
            "id": "m_invalid",
            "name": "Invalid Mecha",
            "pilot_id": "nonexistent_pilot",
            "weapon_ids": [],
            "stats": {"hp": 5000, "en": 100, "armor": 1000, "mobility": 100},
            "attributes": {"hit": 10.0, "precision": 10.0, "crit": 5.0},
            "defense": {"dodge": 10.0, "parry": 10.0, "block": 10.0}
        }]

        mechas_file = temp_data_dir / "mechas.json"
        with open(mechas_file, 'w', encoding='utf-8') as f:
            json.dump(mechas_data, f, ensure_ascii=False)

        loader = DataLoader(data_dir=str(temp_data_dir))
        loader._load_pilots()  # 先加载驾驶员

        with pytest.raises(ValueError, match="引用了不存在的驾驶员"):
            loader._load_mechas()

    def test_mecha_with_invalid_weapon_id(self, temp_data_dir):
        """测试引用不存在的武器"""
        # 创建错误的mechas.json
        mechas_data = [{
            "id": "m_invalid",
            "name": "Invalid Mecha",
            "pilot_id": "p_amuro",  # 需要先加载这个驾驶员
            "weapon_ids": ["nonexistent_weapon"],
            "stats": {"hp": 5000, "en": 100, "armor": 1000, "mobility": 100},
            "attributes": {"hit": 10.0, "precision": 10.0, "crit": 5.0},
            "defense": {"dodge": 10.0, "parry": 10.0, "block": 10.0}
        }]

        # 需要先创建有效的pilots.json和加载武器
        pilots_data = [{
            "id": "p_amuro",
            "name": "Amuro",
            "stats": {"shooting": 100, "melee": 100, "awakening": 100, "defense": 100, "reaction": 100}
        }]
        pilots_file = temp_data_dir / "pilots.json"
        with open(pilots_file, 'w', encoding='utf-8') as f:
            json.dump(pilots_data, f, ensure_ascii=False)

        weapons_data = []  # 空武器列表
        weapons_file = temp_data_dir / "weapons.json"
        with open(weapons_file, 'w', encoding='utf-8') as f:
            json.dump(weapons_data, f, ensure_ascii=False)

        mechas_file = temp_data_dir / "mechas.json"
        with open(mechas_file, 'w', encoding='utf-8') as f:
            json.dump(mechas_data, f, ensure_ascii=False)

        loader = DataLoader(data_dir=str(temp_data_dir))
        loader.load_all()

        # 应该抛出错误
        # 注意：load_all不会抛出异常，因为数据已经在加载时处理了
        # 这里需要检查是否有无效武器
        assert len(loader.mechas) == 0  # 由于错误应该没有加载成功


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

        with pytest.raises(KeyError, match="驾驶员不存在"):
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

        with pytest.raises(KeyError, match="武器不存在"):
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

        with pytest.raises(KeyError, match="机体不存在"):
            loader.get_mecha("nonexistent")


# ============================================================================
# 测试load_all方法
# ============================================================================

class TestLoadAll:
    """测试load_all方法"""

    def test_load_all_loads_everything(self, loader, capsys):
        """测试load_all加载所有数据"""
        loader.load_all()

        assert len(loader.pilots) == 3
        assert len(loader.weapons) == 3
        assert len(loader.mechas) == 3

        # 检查输出
        captured = capsys.readouterr()
        assert "开始加载数据" in captured.out
        assert "已加载 3 个驾驶员" in captured.out
        assert "已加载 3 个武器" in captured.out
        assert "已加载 3 个机体" in captured.out
        assert "数据加载完成" in captured.out

    def test_load_all_dependencies_order(self, loader):
        """测试加载顺序（依赖关系）"""
        # 机体依赖驾驶员和武器
        loader.load_all()

        # 机体的驾驶员引用应该有效
        for mecha in loader.mechas.values():
            assert mecha.pilot is not None
            assert mecha.pilot.id in loader.pilots

        # 机体的武器引用应该有效
        for mecha in loader.mechas.values():
            for weapon in mecha.weapons:
                assert weapon.id in loader.weapons


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
        weapons_file = temp_data_dir / "weapons.json"
        with open(weapons_file, 'w', encoding='utf-8') as f:
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
            "stats": {"shooting": 100, "melee": 100, "awakening": 100, "defense": 100, "reaction": 100}
        }]
        (temp_data_dir / "pilots.json").write_text(json.dumps(pilots_data), encoding='utf-8')

        weapons_data = [{
            "id": "w_test",
            "name": "Test Weapon",
            "type": "RIFLE",
            "power": 1000,
            "en_cost": 10,
            "range": {"min": 1, "max": 100}
        }]
        (temp_data_dir / "weapons.json").write_text(json.dumps(weapons_data), encoding='utf-8')

        mechas_file = temp_data_dir / "mechas.json"
        with open(mechas_file, 'w', encoding='utf-8') as f:
            json.dump([], f)

        loader = DataLoader(data_dir=str(temp_data_dir))
        loader.load_all()

        assert len(loader.mechas) == 0
