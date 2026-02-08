
import sys
import os
import io

# Windows UTF-8 兼容性处理
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models import Mecha, Pilot, Weapon, WeaponType, Terrain, BattleContext
from src.combat.engine import BattleSimulator
from src.combat.resolver import AttackTableResolver
from src.skills import EffectManager, SkillRegistry

def test_spirit_valor():
    print("=== Testing Spirit: Valor (Hot Blood) ===")
    
    # Setup Pilot & Mecha
    pilot_a = Pilot("p1", "Amuro", 100, 100, 100, 100, 100)
    mecha_a = Mecha("m1", "Gundam", pilot_a, 5000, 5000, 200, 200, 10, 10, 10, 10, 10, 10, 10, 100)
    
    pilot_b = Pilot("p2", "Char", 100, 100, 100, 100, 100)
    mecha_b = Mecha("m2", "Zaku", pilot_b, 5000, 5000, 200, 200, 10, 10, 10, 10, 10, 10, 10, 100)
    
    weapon = Weapon("w1", "Beam Rifle", WeaponType.RIFLE, 1000, 10, 0, 5000)
    mecha_a.weapons.append(weapon)
    
    # 1. Calculate Damage WITHOUT Valor
    ctx = BattleContext(1, 1000, Terrain.SPACE, mecha_a, mecha_b, weapon)
    
    # Mock roll to ensure HIT
    ctx.roll = 0 
    
    # We can't easily call internal methods of resolver without context, 
    # but we can check the hook logic directly or run a full resolve.
    # Let's run full resolve.
    # Force result to hit to see damage? 
    # AttackTableResolver.resolve_attack uses tables.
    # Let's just check the damage formula hook directly via a unit test style approach.
    
    # Apply Valor
    print("Applying Valor to Amuro...")
    from src.skills import SpiritCommands
    SpiritCommands.activate_valor(mecha_a)
    
    # Check if effect exists
    has_valor = any(e.id == 'spirit_valor' for e in mecha_a.effects)
    print(f"Has Valor Effect: {has_valor}")
    
    # Test Hook
    base_damage = 1000
    # Context must have attacker set for the hook to work
    ctx.attacker = mecha_a
    
    final_damage = SkillRegistry.process_hook("PRE_DAMAGE_CALC", base_damage, ctx)
    print(f"Base Damage: 1000 -> Hooked Damage: {final_damage}")
    
    if final_damage == 2000:
        print("✅ PASS: Damage doubled!")
    else:
        print(f"❌ FAIL: Expected 2000, got {final_damage}")

def test_spirit_strike():
    print("\n=== Testing Spirit: Strike (Sure Hit) ===")
    pilot_a = Pilot("p1", "Amuro", 100, 100, 100, 100, 100)
    mecha_a = Mecha("m1", "Gundam", pilot_a, 5000, 5000, 200, 200, 10, 10, 10, 10, 10, 10, 10, 100)
    
    # Apply Strike
    from src.skills import SpiritCommands
    SpiritCommands.activate_strike(mecha_a)
    
    ctx = BattleContext(1, 1000, Terrain.SPACE, attacker=mecha_a)
    
    hit_bonus = 0.0
    final_hit_bonus = SkillRegistry.process_hook("PRE_HIT_RATE", hit_bonus, ctx)
    
    print(f"Base Hit Bonus: 0.0 -> Hooked: {final_hit_bonus}")
    
    if final_hit_bonus == 100.0:
        print("✅ PASS: Hit rate set to 100!")
    else:
        print(f"❌ FAIL: Expected 100.0, got {final_hit_bonus}")

if __name__ == "__main__":
    test_spirit_valor()
    test_spirit_strike()
