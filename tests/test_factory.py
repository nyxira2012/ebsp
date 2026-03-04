
"""
测试 MechaFactory
验证 Config -> Snapshot 的转换逻辑
"""
import pytest
from src.models import (
    MechaConfig, PilotConfig, SubPilotConfig, EquipmentConfig, WeaponType, MechaSnapshot
)
from src.factory import MechaFactory

class TestMechaFactory:
    
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
            stat_modifiers={"final_mobility": 10.0, "final_hit": 5.0}
        )

    def test_basic_creation(self, mecha_conf, pilot_conf):
        """测试基础快照生成"""
        snapshot = MechaFactory.create_mecha_snapshot(
            mecha_conf, pilot_conf
        )
        
        assert snapshot.mecha_name == "Test Mecha"
        assert snapshot.final_max_hp == 3000
        assert snapshot.final_mobility == 90
        assert snapshot.pilot_stats_backup['stat_shooting'] == 150
        assert len(snapshot.weapons) == 0 # No weapons passed

    def test_with_weapon_and_parts(self, mecha_conf, pilot_conf, weapon_conf, equip_parts):
        """测试带武器和装备的快照生成"""
        snapshot = MechaFactory.create_mecha_snapshot(
            mecha_conf, pilot_conf, equipments=[weapon_conf, equip_parts]
        )
        
        # 验证装备属性修正
        # Base Mobility 90 + Booster 10 = 100
        assert snapshot.final_mobility == 100
        # Base Hit 10 + Booster 5 = 15
        assert snapshot.final_hit == 15.0 # Check direct field access
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
        snapshot = MechaFactory.create_mecha_snapshot(
            mecha_conf, pilot_conf, upgrade_level=5
        )

        # HP + 5*200 = 1000 -> 3000+1000=4000
        assert snapshot.final_max_hp == 4000
        # Armor + 5*20 = 100 -> 800+100=900
        assert snapshot.final_armor == 900

    def test_skill_aggregation(self, mecha_conf, pilot_conf, equip_parts):
        """测试技能聚合功能"""
        # 设置装备携带技能
        equip_parts.passive_skills = ["skill_test"]
        pilot_conf.innate_skills = ["trait_nt"]

        snapshot = MechaFactory.create_mecha_snapshot(
            mecha_conf, pilot_conf, equipments=[equip_parts]
        )

        assert "trait_nt" in snapshot.skills
        assert "skill_test" in snapshot.skills
        assert len(snapshot.skills) == len(set(snapshot.skills))  # 去重验证

    def test_skill_aggregation_deduplication(self, mecha_conf, pilot_conf, equip_parts):
        """测试技能聚合去重功能"""
        # 驾驶员和装备携带相同技能
        equip_parts.passive_skills = ["skill_ace"]
        pilot_conf.innate_skills = ["skill_ace", "trait_nt"]

        snapshot = MechaFactory.create_mecha_snapshot(
            mecha_conf, pilot_conf, equipments=[equip_parts]
        )

        # 应该去重，只保留一份
        assert snapshot.skills.count("skill_ace") == 1
        assert "trait_nt" in snapshot.skills
        assert len(snapshot.skills) == 2

    def test_exclusive_slot_validation(self):
        """测试EXCLUSIVE槽位验证"""
        # 创建专属装备（RX系列专用）
        exclusive_armor = EquipmentConfig(
            id="e_gundam_armor",
            name="高达专用装甲",
            type="EQUIP",
            compatible_series=["RX"]
        )

        # RX系列机体 - 应该通过
        assert MechaFactory._validate_equipment_slot(
            exclusive_armor, "EXCLUSIVE", "RX"
        ) is True

        # 非RX系列机体 - 应该失败
        assert MechaFactory._validate_equipment_slot(
            exclusive_armor, "EXCLUSIVE", "ZAKU"
        ) is False

        # 专属装备不能安装到普通EQUIP槽位（类型不匹配）
        assert MechaFactory._validate_equipment_slot(
            exclusive_armor, "WEAPON", "RX"
        ) is False

    def test_exclusive_slot_generic_equipment(self):
        """测试通用装备不能安装到EXCLUSIVE槽位"""
        # 通用装备（无 series 字段）
        generic_equip = EquipmentConfig(
            id="e_booster",
            name="增压器",
            type="EQUIP"
        )

        # 通用装备不能安装到EXCLUSIVE槽位
        assert MechaFactory._validate_equipment_slot(
            generic_equip, "EXCLUSIVE", "RX"
        ) is False

        # 但可以安装到普通EQUIP槽位
        assert MechaFactory._validate_equipment_slot(
            generic_equip, "EQUIP", ""
        ) is True

    def test_sub_pilot_stats_aggregation(self, mecha_conf, pilot_conf):
        """测试副驾驶属性聚合"""
        # 主驾驶员：射击100
        pilot_conf.stat_shooting = 100

        # 副驾驶：射击50，贡献率30%
        sub_pilot = SubPilotConfig(
            id="sub_001",
            name="Sub Pilot",
            portrait_id="p_sub",
            stat_shooting=50,
            contribution_rate=0.3
        )

        snapshot = MechaFactory.create_mecha_snapshot(
            mecha_conf, pilot_conf, sub_pilot_conf=sub_pilot
        )

        # 预期：100 + 50*0.3 = 115
        assert snapshot.pilot_stats_backup['stat_shooting'] == 115
        assert snapshot.sub_pilot_contribution_rate == 0.3
        # 验证副驾驶原始属性备份
        assert snapshot.sub_pilot_stats_backup['stat_shooting'] == 50

    def test_sub_pilot_skill_aggregation(self, mecha_conf, pilot_conf):
        """测试副驾驶技能聚合"""
        pilot_conf.innate_skills = ["trait_nt"]

        sub_pilot = SubPilotConfig(
            id="sub_001",
            name="Sub Pilot",
            portrait_id="p_sub",
            innate_skills=["skill_support"]
        )

        snapshot = MechaFactory.create_mecha_snapshot(
            mecha_conf, pilot_conf, sub_pilot_conf=sub_pilot
        )

        assert "trait_nt" in snapshot.skills
        assert "skill_support" in snapshot.skills
        # 验证副驾驶肖像
        assert snapshot.sub_portrait == "p_sub"

    def test_sub_pilot_contribution_rate_variations(self, mecha_conf, pilot_conf):
        """测试不同副驾驶贡献率"""
        pilot_conf.stat_shooting = 100

        # 50% 贡献率
        sub_pilot_50 = SubPilotConfig(
            id="sub_50",
            name="Sub 50%",
            portrait_id="p_sub",
            stat_shooting=60,
            contribution_rate=0.5
        )

        snapshot = MechaFactory.create_mecha_snapshot(
            mecha_conf, pilot_conf, sub_pilot_conf=sub_pilot_50
        )

        # 100 + 60*0.5 = 130
        assert snapshot.pilot_stats_backup['stat_shooting'] == 130
        assert snapshot.sub_pilot_contribution_rate == 0.5

    def test_no_sub_pilot(self, mecha_conf, pilot_conf):
        """测试无副驾驶时的默认行为"""
        pilot_conf.stat_shooting = 100

        snapshot = MechaFactory.create_mecha_snapshot(
            mecha_conf, pilot_conf
        )

        # 无副驾驶时，属性应为主驾驶员原始值
        assert snapshot.pilot_stats_backup['stat_shooting'] == 100
        assert snapshot.sub_pilot_contribution_rate == 0.0
        assert snapshot.sub_pilot_stats_backup == {}
        assert snapshot.sub_portrait is None
