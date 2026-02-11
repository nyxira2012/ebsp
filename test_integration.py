
"""
集成验证脚本
演示如何使用 DataLoader 加载配置，并使用 SnapshotFactory 生成机体快照。
"""
import sys
import os

# 确保可以找到 src
sys.path.append(os.getcwd())

from src.loader import DataLoader
from src.factory import SnapshotFactory

def main():
    print("=== EBS-P 数据聚合系统演示 ===")
    
    # 1. 初始化并加载数据
    loader = DataLoader(data_dir="data")
    try:
        loader.load_all()
    except Exception as e:
        print(f"加载数据失败: {e}")
        return

    # 2. 从加载的数据中选取对象
    try:
        mecha_conf = loader.get_mecha_config("mech_rx78")
        pilot_conf = loader.get_pilot_config("pilot_amuro")
        
        # 选取一些装备 (例如增压器)
        booster = loader.get_equipment_config("e_booster")
        
    except KeyError as e:
        print(f"获取配置失败: {e}")
        return

    # 3. 使用工厂生产快照
    print(f"\n正在为机体 [{mecha_conf.name}] 聚合驾驶员 [{pilot_conf.name}]...")
    
    snapshot = SnapshotFactory.create_mecha_snapshot(
        mecha_conf=mecha_conf,
        pilot_conf=pilot_conf,
        equipments=[booster], # 穿戴增压器
        upgrade_level=5       # 机体已进行 5 段改造
    )

    # 4. 展示结果 (利用新模型的 Pydantic 自动格式化或我们的兼容属性)
    print("\n--- 聚合机体快照预览 ---")
    print(f"实例 ID: {snapshot.instance_id}")
    print(f"机体名: {snapshot.mecha_name}")
    print(f"当前 HP (含加成): {snapshot.current_hp} / {snapshot.final_max_hp}")
    print(f"当前机动 (含装备加成): {snapshot.final_mobility}")
    print(f"最终命中 (统计): {snapshot.final_hit}")
    print(f"驾驶员五维 (已备份): {snapshot.pilot_stats_backup}")
    
    # 5. 展示武器
    print("\n--- 武器列表 ---")
    for w in snapshot.weapons:
        print(f"- {w.name} [{w.type}]: 威力={w.final_power}, 射程={w.range_min}-{w.range_max}")

if __name__ == "__main__":
    main()
