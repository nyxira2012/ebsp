
"""
测试 SnapshotFactory
验证 Config -> Snapshot 的转换逻辑
"""
import pytest
from src.models import (
    MechaConfig, PilotConfig, EquipmentConfig, WeaponType, MechaSnapshot
)
from src.factory import SnapshotFactory

class TestSnapshotFactory:
    
    @pytest.fixture
    def mecha_conf(self):
        return MechaConfig(
            id="m_001", name="Test Mecha", portrait_id="p_m_001",
            init_hp=3000, init_en=120, init_armor=800, init_mobility=90,
            init_hit=10.0, init_precision=5.0, init_crit=5.0,
            init_dodge=10.0, init_parry=5.0, init_block=5.0, init_block_red=300,
            slots=["WEAPON", "EQUIP"]
        )
        
    @pytest.fixture
    def pilot_conf(self):
        return PilotConfig(
            id="p_001", name="Test Pilot", portrait_id="p_p_001",
            stat_shooting=150, stat_melee=100, stat_reaction=110,
            stat_awakening=100, stat_defense=100,
            innate_skills=["skill_ace"]
        )
        
    @pytest.fixture
    def weapon_conf(self):
        return EquipmentConfig(
            id="w_001", name="Beam Rifle", type="WEAPON",
            weapon_type=WeaponType.SHOOTING,
            weapon_power=1200, weapon_range_min=1, weapon_range_max=4,
            weapon_en_cost=10
        )
        
    @pytest.fixture
    def equip_parts(self):
        return EquipmentConfig(
            id="e_001", name="Booster", type="EQUIP",
            stat_modifiers={"mobility": 10.0, "hit_rate": 5.0}
        )

    def test_basic_creation(self, mecha_conf, pilot_conf):
        """测试基础快照生成"""
        snapshot = SnapshotFactory.create_mecha_snapshot(
            mecha_conf, pilot_conf
        )
        
        assert snapshot.mecha_name == "Test Mecha"
        assert snapshot.final_max_hp == 3000
        assert snapshot.final_mobility == 90
        assert snapshot.pilot_stats_backup['stat_shooting'] == 150
        assert len(snapshot.weapons) == 0 # No weapons passed

    def test_with_weapon_and_parts(self, mecha_conf, pilot_conf, weapon_conf, equip_parts):
        """测试带武器和装备的快照生成"""
        snapshot = SnapshotFactory.create_mecha_snapshot(
            mecha_conf, pilot_conf, equipments=[weapon_conf, equip_parts]
        )
        
        # 验证装备属性修正
        # Base Mobility 90 + Booster 10 = 100
        assert snapshot.final_mobility == 100
        # Base Hit 10 + Booster 5 = 15
        assert snapshot.hit_rate == 15.0 # Check compatibility prop
        assert snapshot.final_hit == 15.0
        
        # 验证武器列表
        assert len(snapshot.weapons) == 1
        w = snapshot.weapons[0]
        assert w.name == "Beam Rifle"
        assert w.final_power == 1200
        assert w.type == WeaponType.SHOOTING

    def test_upgrade_bonuses(self, mecha_conf, pilot_conf):
        """测试改造加成"""
        # Level 5 upgrade
        snapshot = SnapshotFactory.create_mecha_snapshot(
            mecha_conf, pilot_conf, upgrade_level=5
        )
        
        # HP + 5*200 = 1000 -> 3000+1000=4000
        assert snapshot.final_max_hp == 4000
        # Armor + 5*20 = 100 -> 800+100=900
        assert snapshot.final_armor == 900
