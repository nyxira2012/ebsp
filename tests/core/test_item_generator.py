import pytest
from unittest.mock import patch, MagicMock
from src.core.item_generator import EquipmentGenerator
from src.loader import DataLoader
from src.models import EquipmentConfig, AffixConfig

def test_equipment_generator():
    loader = DataLoader()
    loader.equipments = {"test_eq": EquipmentConfig(id="test_eq", name="Test", type="WEAPON")}
    loader.affixes = {
        "stat_hit": AffixConfig(id="stat_hit", type="stat", target="final_hit", base_value=1.0, ilvl_scale=0.1, min_ilvl=1, weight=1000, slot_tags=["WEAPON"]),
        "skill_snipe": AffixConfig(id="skill_snipe", type="skill", skill_id="sniper", min_ilvl=1, weight=100, slot_tags=["WEAPON"])
    }
    
    gen = EquipmentGenerator(loader)
    
    with patch("random.randint", return_value=10):
        with patch("random.choices", side_effect=[
            [3], [loader.affixes["stat_hit"]], # slot 1: T3, stat_hit
            [0],                               # slot 2: T0
            [1], [loader.affixes["stat_hit"]], # slot 3: T1, stat_hit (duplicates allowed if set logic removed)
            [loader.affixes["skill_snipe"]]    # skill
        ]):
            with patch("random.random", return_value=0.001): # < SKILL_CHANCE
                res = gen.generate_equipment("test_eq", 10)
                
                assert res["ilvl"] == 10
                assert len(res["affixes"]) == 2
                assert res["skill"] == "sniper"
