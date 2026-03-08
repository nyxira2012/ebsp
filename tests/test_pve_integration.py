import pytest
from src.pve.services import MothershipIntegrationService
from src.models import RegionConfig, MothershipConfig
import time

def test_validate_region_entry():
    region = RegionConfig(id="region_1", name="Region 1", min_region_level=2, base_ilvl=10)
    
    # 满足条件的母舰
    ms_pass = MothershipConfig(
        id="pass", name="pass", generation=2, tier="SR", 
        engine_level=1, hp_regen_per_min=5, en_regen_per_min=10, 
        region_level=2, cargo_capacity=100, emergency_extraction_tax=0.5, price=0
    )
    
    # 不满足条件的母舰
    ms_fail = MothershipConfig(
        id="fail", name="fail", generation=1, tier="N", 
        engine_level=1, hp_regen_per_min=5, en_regen_per_min=10, 
        region_level=1, cargo_capacity=50, emergency_extraction_tax=0.7, price=0
    )
    
    assert MothershipIntegrationService.validate_region_entry(region, ms_pass) is True
    assert MothershipIntegrationService.validate_region_entry(region, ms_fail) is False

def test_get_max_movement_points():
    ms_engine1 = MothershipConfig(
        id="eng1", name="eng1", generation=1, tier="N", 
        engine_level=1, hp_regen_per_min=5, en_regen_per_min=10, 
        region_level=1, cargo_capacity=50, emergency_extraction_tax=0.7, price=0
    )
    assert MothershipIntegrationService.get_max_movement_points(ms_engine1) == 2

def test_calculate_regeneration():
    ms_regen = MothershipConfig(
        id="regen", name="regen", generation=1, tier="N", 
        engine_level=1, hp_regen_per_min=10, en_regen_per_min=20, 
        region_level=1, cargo_capacity=50, emergency_extraction_tax=0.7, price=0
    )
    
    t0 = time.time()
    t1 = t0 + 120  # 120 seconds later (2 minutes)
    
    hp_reg, en_reg = MothershipIntegrationService.calculate_regeneration(t0, t1, ms_regen)
    assert hp_reg == 20
    assert en_reg == 40
    
    # Negative time check
    hp_reg, en_reg = MothershipIntegrationService.calculate_regeneration(t1, t0, ms_regen)
    assert hp_reg == 0
    assert en_reg == 0

def test_can_fit_in_cargo():
    ms_cargo = MothershipConfig(
        id="cargo", name="cargo", generation=1, tier="N", 
        engine_level=1, hp_regen_per_min=5, en_regen_per_min=10, 
        region_level=1, cargo_capacity=50, emergency_extraction_tax=0.7, price=0
    )
    
    assert MothershipIntegrationService.can_fit_in_cargo(40, 5, ms_cargo) is True
    assert MothershipIntegrationService.can_fit_in_cargo(40, 15, ms_cargo) is False
