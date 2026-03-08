"""
Mothership Tier & Revenue Logic Audit (v7.0)
============================================
Correcting the "Serious Error" in extraction logic:
1. Retained items are BASED ON PENDING LOOT, not total cargo capacity.
2. Sales are ALWAYS 100% (No scrap value penalty).
3. The relationship between Bag Size and Revenue is a "Correlation" via Mothership Tiers.

Audit Objective: Check if the ship progression (Tax decrease + Region access) 
leads to a sensible revenue growth curve.
"""

import random
from typing import List, Dict

# ============================================================================
# Design Data (Strictly Aligned with Doc 11 & Doc 10)
# ============================================================================
MOTHERSHIP_TIERS = [
    {"name": "Gen 1 (Starter)", "cargo": 50,  "tax": 0.70, "access": "R1"},
    {"name": "Gen 2 (Standard)", "cargo": 100, "tax": 0.50, "access": "R2"},
    {"name": "Gen 3 (Advanced)", "cargo": 170, "tax": 0.45, "access": "R3"},
    {"name": "Gen 5 (Flagship)", "cargo": 300, "tax": 0.45, "access": "R3"},
]

REGION_GEN = {
    "R1": {"chance": 0.30, "weights": [60, 30, 8, 2, 0]},
    "R2": {"chance": 0.45, "weights": [30, 45, 20, 4, 1]},
    "R3": {"chance": 0.60, "weights": [10, 25, 40, 20, 5]},
}

RARITY_VALUES = {"GRAY": 250, "GREEN": 1200, "BLUE": 4500, "PURPLE": 18000, "GOLD": 150000}
RARITY_KEYS = list(RARITY_VALUES.keys())

DAILY_COMBATS = 500

# ============================================================================
# Simulation Engine
# ============================================================================

def simulate_daily_revenue(region_id: str, tax_rate: float, force_extract: bool = True):
    """
    Args:
        force_extract: If True, player triggers emergency extraction (applies TAX).
                       If False, player finishes Boss (0 tax).
    """
    config = REGION_GEN[region_id]
    total_credits_drop = 0  # Credits are NEVER taxed (Doc 10.5.1)
    pending_items_value = 0
    items_count = 0
    
    for _ in range(DAILY_COMBATS):
        # 1. Credits (Base Guarantee)
        # Assuming avg 100 credits per combat as base
        total_credits_drop += random.randint(50, 150)
        
        # 2. Loot Items (Subject to TAX if extracting)
        if random.random() <= config["chance"]:
            rarity = random.choices(RARITY_KEYS, weights=config["weights"])[0]
            pending_items_value += RARITY_VALUES[rarity]
            items_count += 1
            
    # Apply Tax logic
    if force_extract:
        # User Corrected: Retained items = Pending * (1 - Tax)
        # We assume value distribution is linear for simplicity
        retained_items_value = pending_items_value * (1 - tax_rate)
    else:
        retained_items_value = pending_items_value
        
    final_revenue = total_credits_drop + retained_items_value
    return int(final_revenue), items_count

def main():
    print("\n" + "="*80)
    print("MOTHERSHIP REVENUE AUDIT v7.0 (CORRECTED MECHANICS)")
    print("================================================================================")
    print("Rule 1: Tax ONLY hits temporary items (Pending Rewards).")
    print("Rule 2: Cargo Capacity has NO direct effect on credit revenue (Selling is 100%).")
    print("Rule 3: Higher Tier Motherships have LOWER tax rates.")

    print(f"\n{'Mothership':<18} | {'Cargo':<5} | {'Tax':<5} | {'Scenario':<12} | {'Daily Credits'}")
    print("-" * 75)
    
    for ship in MOTHERSHIP_TIERS:
        # Case A: High Risk (Emergency Extract)
        rev_extract, items = simulate_daily_revenue(ship["access"], ship["tax"], force_extract=True)
        print(f"{ship['name']:<18} | {ship['cargo']:<5} | {int(ship['tax']*100):>3}% | {'Emergency':<12} | \033[93m{rev_extract:>12,}\033[0m")
        
        # Case B: Perfect Run (Boss Defeated)
        rev_perfect, _ = simulate_daily_revenue(ship["access"], ship["tax"], force_extract=False)
        print(f"{' '*18} | {' '*5} | {' '*5} | {'Perfect Run':<12} | \033[92m{rev_perfect:>12,}\033[0m")
        print("-" * 75)

    print("\n[RELIABILITY AUDIT RESULTS]")
    print("1. Independence: Bag size (50 vs 300) does NOT change revenue for a 'Perfect Run'.")
    print("2. Correlation: Gen 3's 170 slots ship earns more than Gen 1 because it UNLOCKS R3, not because of the slots.")
    print("3. Tax Impact: During an 'Emergency Extract', the Gen 3 ship keeps 55% of loot vs Gen 1's 30%.")
    print("   This makes higher-tier ships safer for long-duration farming.")
    print("\n[CONCLUSION]")
    print("The design uses Mothership Tiers to bundle 'Inventory Quality of Life' with 'Revenue Security'.")

if __name__ == "__main__":
    main()
