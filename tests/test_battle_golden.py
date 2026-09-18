"""
金样张防漂移闸门（Doc 15 §7 P0 随批落地 / §8；裁决 #9）。

固定种子跑一场模拟，战报全量对比 tests/golden/battle_timeline_v1.json——
契约字段任何漂移（改名/搬家/漏输出）在此报警。

确定性（Doc 15 §4 红线 3，P2 起）：种子经 ``EngagementSpec(seed=...)``
注入，裁判持有本场随机流，不依赖全局 random 状态。

三处同步规则（Doc 15 §8）：改字段必须先改 Doc 14（契约正册）→
再改 src/presentation/contracts.py（及 engagement 装配）→ 重录金样张。
跳步即打回。

重录方法（字段变更走完前两步后执行）::

    UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/test_battle_golden.py
"""

import json
import os
from pathlib import Path
from typing import Any

from src.combat.engagement import Engagement, EngagementContext, EngagementSpec

GOLDEN_PATH = Path(__file__).parent / "golden" / "battle_timeline_v1.json"
GOLDEN_SEED = 20260918
SIZE_BUDGET_BYTES = 512 * 1024  # Doc 15 §3：单场战报数百 KB 量级


def _resolve_seeded(mecha_a, mecha_b):
    """以注入种子裁定一场（裁判持有本场随机流，见模块 docstring）。"""
    spec = EngagementSpec(
        mecha_a=mecha_a,
        mecha_b=mecha_b,
        context=EngagementContext(source="debug"),
        seed=GOLDEN_SEED,
    )
    return Engagement(spec).resolve()


def _first_diff(actual: Any, golden: Any, path: str = "$") -> str:
    """定位全量对比的第一处分歧路径——金样张失败时给出可追查的位置。"""
    if type(actual) is not type(golden):
        return f"{path}: 类型 {type(actual).__name__} != {type(golden).__name__}"
    if isinstance(actual, dict):
        for key in sorted(set(actual) | set(golden)):
            if key not in actual:
                return f"{path}.{key}: golden 多出字段"
            if key not in golden:
                return f"{path}.{key}: golden 缺失字段"
            sub = _first_diff(actual[key], golden[key], f"{path}.{key}")
            if sub:
                return sub
        return ""
    if isinstance(actual, list):
        if len(actual) != len(golden):
            return f"{path}: 长度 {len(actual)} != {len(golden)}"
        for idx, (a_item, g_item) in enumerate(zip(actual, golden)):
            sub = _first_diff(a_item, g_item, f"{path}[{idx}]")
            if sub:
                return sub
        return ""
    return "" if actual == golden else f"{path}: {actual!r} != {golden!r}"


class TestBattleTimelineGolden:
    def test_timeline_matches_golden(self, gundam_rx78, zaku_ii):
        report = _resolve_seeded(gundam_rx78, zaku_ii)
        actual = report.timeline.model_dump(mode="json")

        if os.environ.get("UPDATE_GOLDEN"):
            GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN_PATH.write_text(
                json.dumps(actual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

        golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        diff = _first_diff(actual, golden)
        assert diff == "", f"战报与金样张漂移：{diff}"

        # 附带断言（Doc 14 §3 顶层四块 / 入口标记 / 体积预算）
        assert set(actual.keys()) == {"meta", "init", "rounds", "result"}
        assert actual["meta"]["route"] == "debug"
        assert len(json.dumps(actual, ensure_ascii=False)) < SIZE_BUDGET_BYTES
