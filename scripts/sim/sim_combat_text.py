import os
import sys
import argparse
import json
import io
import collections
import math
import random
from typing import List, Dict, Any, Optional, Callable

# 确保项目根目录在路径中
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Windows UTF-8 支持
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 核心系统引用
from src.loader import DataLoader
from src.factory import MechaFactory
from src.combat.engine import BattleSimulator
from src.presentation.models import RawAttackEvent, PresentationAttackEvent
from src.presentation.constants import TemplateTier
from src.models import Mecha, Weapon, WeaponType, AttackResult, InitiativeReason

# ============================================================================
# 1. 统计采集模块 (内部类)
# ============================================================================

class PresentationStatisticsCollector:
    """
    负责收集战斗演出数据并生成量化报告。
    """
    def __init__(self):
        self.raw_events: List[RawAttackEvent] = []
        self.tier_counts = collections.Counter()
        self.result_tier_matrix = collections.defaultdict(collections.Counter)
        self.template_usage = collections.Counter()
        self.weapon_template_usage = collections.defaultdict(collections.Counter)

    def on_presentation_events(self, pres_events: List[PresentationAttackEvent]):
        if not pres_events: return
        evt = pres_events[0]
        raw = evt.raw_event
        if not raw: return

        self.raw_events.append(raw)
        self.tier_counts[evt.tier.name] += 1
        self.result_tier_matrix[raw.attack_result][evt.tier.name] += 1
        self.template_usage[evt.template_id] += 1
        self.weapon_template_usage[raw.weapon_type][evt.template_id] += 1

    def calculate_entropy(self) -> float:
        total = sum(self.template_usage.values())
        if total == 0: return 0.0
        entropy = 0.0
        for count in self.template_usage.values():
            p = count / total
            entropy -= p * math.log2(p)
        return entropy

    def generate_report(self) -> Dict[str, Any]:
        total = len(self.raw_events)
        if total == 0: return {"status": "No data"}
        t3_rate = (self.tier_counts.get("T3_FALLBACK", 0) / total) * 100
        return {
            "summary": {
                "total_attacks": total,
                "diversity_entropy": round(self.calculate_entropy(), 3),
                "t3_fallback_rate": f"{t3_rate:.2f}%",
                "tier_distribution": dict(self.tier_counts)
            },
            "result_tier_matrix": {res: dict(tiers) for res, tiers in self.result_tier_matrix.items()},
            "top_templates": dict(self.template_usage.most_common(10)),
            "weapon_variety": {wt: len(templates) for wt, templates in self.weapon_template_usage.items()}
        }

# ============================================================================
# 2. 场景定义模块 (Hard-coded Scenarios)
# ============================================================================

class BattleScenario:
    def __init__(self, name: str, desc: str):
        self.name, self.desc = name, desc
        self.mecha_a = self.mecha_b = None
        self.dist_provider = None

    def setup(self, loader: DataLoader): pass

    def _create(self, loader: DataLoader, mid: str, pid: str = None):
        return MechaFactory.create_mecha_snapshot(
            loader.get_mecha_config(mid),
            pilot_conf=loader.get_pilot_config(pid) if pid else None,
            weapon_configs=loader.equipments
        )

class NormalScenario(BattleScenario):
    def setup(self, loader: DataLoader):
        mids = list(loader.mechas.keys())
        pids = list(loader.pilots.keys())
        self.mecha_a = self._create(loader, mids[0], pids[0] if pids else None)
        self.mecha_b = self._create(loader, mids[1] if len(mids)>1 else mids[0])

class BossPressureScenario(BattleScenario):
    def setup(self, loader: DataLoader):
        mids = list(loader.mechas.keys())
        self.mecha_a = self._create(loader, mids[0])
        self.mecha_b = self._create(loader, mids[1] if len(mids)>1 else mids[0])
        if self.mecha_b:
            self.mecha_b.final_hit += 50
            self.mecha_b.final_max_hp *= 10
            self.mecha_b.current_hp = self.mecha_b.final_max_hp
            for w in self.mecha_b.weapons: w.final_power *= 2

class MeleeBrawlScenario(BattleScenario):
    def setup(self, loader: DataLoader):
        mids = list(loader.mechas.keys())
        self.mecha_a = self._create(loader, mids[0]); self.mecha_b = self._create(loader, mids[1] if len(mids)>1 else mids[0])
        self.dist_provider = lambda r: random.randint(200, 800)

# ============================================================================
# 3. 运行引擎与入口
# ============================================================================

def run_simulation(args):
    data_loader = DataLoader(data_dir="data")
    data_loader.load_all()
    
    scenarios = {
        "normal": NormalScenario("普通对战", "标准对峙，验证通用演出覆盖"),
        "boss": BossPressureScenario("Boss 压迫", "玩家处于劣势，验证受损演出"),
        "melee": MeleeBrawlScenario("近战缠斗", "强制近距离，验证格斗模板")
    }
    scenario = scenarios.get(args.scenario, scenarios["normal"])
    collector = PresentationStatisticsCollector()

    print(f"\n>>> 运行场景: {scenario.name} | 次数: {args.count}")
    
    for i in range(args.count):
        scenario.setup(data_loader)
        sim = BattleSimulator(scenario.mecha_a, scenario.mecha_b, verbose=args.verbose and (i==0))
        sim.register_presentation_event_listener(collector.on_presentation_events)
        if scenario.dist_provider: sim.set_distance_provider(scenario.dist_provider)
        sim.run_battle()

    report = collector.generate_report()
    
    # 仅在显式指定路径时保存文件，否则仅输出到控制台
    if args.report:
        os.makedirs(os.path.dirname(args.report), exist_ok=True)
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=4, ensure_ascii=False)
        print(f"\n>>> 报告已存至: {args.report}")
    else:
        # 如果不保存文件，把核心统计打印出来方便一眼看到
        print("\n>>> 统计简报:")
        print(json.dumps(report["summary"], indent=4, ensure_ascii=False))
        print(">>> 提示: 使用 --report [path] 可将完整详细报告保存为 JSON 文件。")
    
    print(f"\n>>> 模拟结束。T3回退率: {report['summary']['t3_fallback_rate']} | 熵值: {report['summary']['diversity_entropy']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=str, default="normal")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--verbose", action="store_true", default=True)
    parser.add_argument("--no-verbose", dest="verbose", action="store_false")
    parser.add_argument("--report", type=str, default=None, help="详细统计报告保存路径 (可选)")
    run_simulation(parser.parse_args())
