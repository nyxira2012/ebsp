"""
随机流确定性测试（Doc 15 §4 红线 3 / §6 复现与种子 / §8）。

裁判持有本场随机流（圆桌掷点、技能触发、先手波动、距离、演出竞标统一
收编）：同委托同种子必得同一战报——即便两次裁定之间全局随机流状态不同
（战报不消费全局流，注入失效即漂移，此为本测试的假绿防线）；不同种子
应产出不同战报；seed 缺省时自动生成并记入 report.seed_used（仅后端侧）。
"""

import json
import random

from src.combat.engagement import Engagement, EngagementContext, EngagementSpec

DEBUG_CONTEXT = EngagementContext(source="debug")


def _spec(gundam_rx78, zaku_ii, seed=None) -> EngagementSpec:
    """独立委托：输入快照各深拷贝一份，调用方与 spec 互不渗漏。"""
    return EngagementSpec(
        mecha_a=gundam_rx78.model_copy(deep=True),
        mecha_b=zaku_ii.model_copy(deep=True),
        context=DEBUG_CONTEXT,
        seed=seed,
    )


class TestDeterminism:
    def test_same_seed_same_report_regardless_of_global_stream(self, gundam_rx78, zaku_ii):
        """同 seed 双跑：两次裁定前把全局流拨到不同状态，战报仍逐字段相等。"""
        try:
            random.seed(101)
            first = Engagement(_spec(gundam_rx78, zaku_ii, seed=20260918)).resolve()
            random.seed(-7)  # 迥异的全局流状态：若战报误消费全局流，此处必然漂移
            second = Engagement(_spec(gundam_rx78, zaku_ii, seed=20260918)).resolve()
        finally:
            random.seed()  # 复位，防止固定种子污染同进程其它测试的随机流
        assert first.timeline.model_dump() == second.timeline.model_dump()
        assert first.final_states == second.final_states
        assert first.seed_used == second.seed_used == 20260918

    def test_same_seed_same_report_with_probability_skill(self, gundam_rx78, zaku_ii):
        """技能概率掷点（trigger_chance/本能——processor 与 skills 回调两个
        消费点）同样走注入流：参战方挂 spirit_instinct（0.3 概率）后，
        同 seed 双跑在迥异全局流状态下战报仍逐字段相等——概率链若回落
        全局流，整场多次掷点下双跑漂移几乎必然。"""
        instinct_a = gundam_rx78.model_copy(deep=True)
        instinct_a.skills = ["spirit_instinct"]
        try:
            random.seed(202)
            first = Engagement(_spec(instinct_a, zaku_ii, seed=77)).resolve()
            random.seed(-13)  # 迥异的全局流状态
            second = Engagement(_spec(instinct_a, zaku_ii, seed=77)).resolve()
        finally:
            random.seed()  # 复位，防止固定种子污染同进程其它测试的随机流
        assert first.timeline.model_dump() == second.timeline.model_dump()

    def test_different_seeds_produce_different_reports(self, gundam_rx78, zaku_ii):
        """不同 seed 的战报（序列化后）组间至少两组不同。

        战报含伤害序列/判定结果/演出文本等大量随机敏感字段，多个 seed 全部
        逐字节相同只剩"注入未生效、恒走全局流"一种解释。
        """
        serialized = set()
        for seed in (1, 2, 3, 4):
            report = Engagement(_spec(gundam_rx78, zaku_ii, seed=seed)).resolve()
            serialized.add(json.dumps(report.timeline.model_dump(mode="json"), sort_keys=True))
        assert len(serialized) >= 2

    def test_default_seed_generated_and_recorded(self, gundam_rx78, zaku_ii):
        """seed=None：resolve 正常完成，seed_used 自动生成为 32 位域内整数。"""
        report = Engagement(_spec(gundam_rx78, zaku_ii)).resolve()
        again = Engagement(_spec(gundam_rx78, zaku_ii)).resolve()
        for seeded in (report.seed_used, again.seed_used):
            assert isinstance(seeded, int)
            assert 0 <= seeded < 2**32
        # 战报本体不受缺省路径影响：结构与裁定完整
        assert report.timeline.rounds
        assert report.ruling.finish in ("ko", "decision", "draw")
