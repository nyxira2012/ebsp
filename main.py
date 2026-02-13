import sys
import io
from typing import NoReturn

# Windows UTF-8 兼容性处理
if sys.platform.startswith('win'):
    # type: ignore (针对特定平台的重写)
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from src import DataLoader, Mecha
from src.skills import TraitManager
from src.combat import BattleSimulator
from src.factory import MechaFactory


def main() -> int:
    """主函数"""
    print("=" * 80)
    print("真实系机甲战斗模拟器 v2.0 (数据驱动版)")
    print("=" * 80)
    print()

    # 1. 初始化数据加载器
    loader: DataLoader = DataLoader(data_dir="data")

    try:
        # 2. 加载所有数据
        loader.load_all()
        print()

        # 4. 获取参战机体 - 从 Config 创建 Snapshot
        config_a = loader.get_mecha_config("mech_rx78")
        config_b = loader.get_mecha_config("mech_zaku")
        mecha_a: Mecha = MechaFactory.create_mecha_snapshot(config_a)
        mecha_b: Mecha = MechaFactory.create_mecha_snapshot(config_b)

        # 5. 应用机体特性
        print("应用机体特性...")
        TraitManager.apply_traits(mecha_a)
        TraitManager.apply_traits(mecha_b)
        print()
        
        # 6. 创建战斗模拟器
        simulator: BattleSimulator = BattleSimulator(mecha_a, mecha_b)
        
        # 7. 运行战斗
        simulator.run_battle()
        
        print()
        print("=" * 80)
        print("战斗模拟器运行完毕")
        print("=" * 80)
        
    except FileNotFoundError as e:
        print(f"❌ 错误: {e}")
        print("请确保 data/ 目录下存在 pilots.json, weapons.json, mechas.json")
        return 1
    
    except Exception as e:
        print(f"❌ 运行时错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code: int = main()
    sys.exit(exit_code)
