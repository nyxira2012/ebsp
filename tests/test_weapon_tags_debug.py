"""
调试脚本：验证武器标签是否正确传递到演出系统
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "."))

from src import DataLoader, Mecha
from src.factory import MechaFactory
from src.combat.engine import BattleSimulator

# 加载两个测试机体
print("=" * 80)
print("武器标签传递调试")
print("=" * 80)

# 初始化数据加载器
loader = DataLoader(data_dir="data")
loader.load_all()

# 加载机体配置
config_a = loader.get_mecha_config("mech_rx78")
config_b = loader.get_mecha_config("mech_zaku")
mecha_a = MechaFactory.create_mecha_snapshot(config_a, weapon_configs=loader.equipments)
mecha_b = MechaFactory.create_mecha_snapshot(config_b, weapon_configs=loader.equipments)

print("\n=== 机体A的武器 ===")
for weapon in mecha_a.weapons:
    print(f"武器: {weapon.name}")
    print(f"  - 类型: {weapon.type.value}")
    print(f"  - 标签: {getattr(weapon, 'tags', [])}")
    print()

print("\n=== 机体B的武器 ===")
for weapon in mecha_b.weapons:
    print(f"武器: {weapon.name}")
    print(f"  - 类型: {weapon.type.value}")
    print(f"  - 标签: {getattr(weapon, 'tags', [])}")
    print()

# 运行一回合战斗，查看演出系统接收到的数据
print("\n=== 运行战斗（1回合） ===")
sim = BattleSimulator(mecha_a, mecha_b, enable_presentation=True)

# 手动执行一回合
sim.round_number = 0
sim._execute_round()

print("\n=== 检查演出系统中的武器标签 ===")
if sim.presentation_timeline:
    for round_event in sim.presentation_timeline:
        print(f"回合 {round_event.round_number}:")
        for seq in round_event.attack_sequences:
            print(f"  攻击序列: {seq.attacker_id} -> {seq.defender_id}")
            for event in seq.events:
                print(f"    事件类型: {event.event_type}")
                print(f"    武器名称: {event.weapon_name}")
                # 通过 raw_event 访问完整的武器信息
                if event.raw_event:
                    print(f"    武器类型: {event.raw_event.weapon_type}")
                    print(f"    武器标签: {event.raw_event.weapon_tags}")
                else:
                    print("    [警告] raw_event 为空！")
                print()
else:
    print("没有演出事件生成！")

print("\n调试完成！")
