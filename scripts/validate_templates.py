#!/usr/bin/env python3
"""
演出模板验证工具

用途：
1. 检查 YAML 模板文件的格式正确性
2. 检查通用模板（damage_material=GENERIC）是否包含材质词（违反 Doc 6 机制 3）
3. 验证模板字段的完整性

使用方法：
    python scripts/validate_templates.py
    python scripts/validate_templates.py --check-material-conflict
    python scripts/validate_templates.py --file data/presentation/templates.yaml
"""

import sys
import os
import argparse
import yaml
from pathlib import Path
from typing import List, Dict, Set, Tuple

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# 材质词词典 - 这些词不应该出现在 damage_material=GENERIC 的模板中
MATERIAL_KEYWORDS = {
    # 能量类
    "光束", "光", "beam", "laser", "能量", "粒子", "高能",
    "熔融", "灼烧", "熔化",

    # 实弹/动能类
    "实弹", "弹头", "子弹", "弹壳", "火药", "kinetic",
    "动能", "弹道", "火神炮", "机炮", "步枪", "炮弹",

    # 物理/金属类（武器材质）
    "金属", "刃", "刀刃", "剑刃", "军刀", "斧", "锤",

    # 其他具体材质/武器类型词
    "热能", "等离子", "导弹", "火箭", "鱼雷",

    # 注意："撞击" 不是材质词，而是动作描述，已移除
}


class TemplateValidator:
    """模板验证器"""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.data: Dict = {}

    def load(self) -> bool:
        """加载 YAML 文件"""
        if not self.file_path.exists():
            self.errors.append(f"文件不存在: {self.file_path}")
            return False

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self.data = yaml.safe_load(f)
            return True
        except yaml.YAMLError as e:
            self.errors.append(f"YAML 解析错误: {e}")
            return False

    def validate_action_bones(self) -> None:
        """验证 ActionBone 模板"""
        action_bones = self.data.get('action_bones', [])
        if not action_bones:
            self.warnings.append("没有找到 action_bones 定义")
            return

        for idx, bone in enumerate(action_bones):
            bone_id = bone.get('bone_id', f'[index {idx}]')

            # 检查必需字段
            required_fields = ['bone_id', 'motion_style', 'text_fragments', 'anim_id']
            for field in required_fields:
                if field not in bone:
                    self.errors.append(f"action_bones[{idx}] ({bone_id}): 缺少必需字段 '{field}'")

            # 检查 motion_style 是否有效
            valid_styles = {
                'SLASH_LIGHT', 'SLASH_HEAVY', 'STRIKE_BLUNT',
                'SHOOT_INSTANT', 'SHOOT_MASSIVE', 'PROJ_SINGLE', 'PROJ_RAIN',
                'IMPACT_RAM', 'PSYCHO_WAVE', 'AOE_BURST', 'ANY'
            }
            motion_style = bone.get('motion_style')
            if motion_style and motion_style not in valid_styles:
                self.warnings.append(f"action_bones[{idx}] ({bone_id}): "
                                    f"未知的 motion_style '{motion_style}'")

            # 检查 damage_material 是否有效
            valid_materials = {'ENERGY', 'KINETIC', 'PHYSICAL', 'GENERIC', 'ANY'}
            material = bone.get('damage_material', 'ANY')
            if material not in valid_materials:
                self.errors.append(f"action_bones[{idx}] ({bone_id}): "
                                  f"无效的 damage_material '{material}'")

            # 检查 text_fragments 格式
            fragments = bone.get('text_fragments', [])
            if not isinstance(fragments, list):
                self.errors.append(f"action_bones[{idx}] ({bone_id}): "
                                  f"text_fragments 必须是数组")
            elif not fragments:
                self.errors.append(f"action_bones[{idx}] ({bone_id}): "
                                  f"text_fragments 不能为空")

    def validate_reaction_bones(self) -> None:
        """验证 ReactionBone 模板"""
        reaction_bones = self.data.get('reaction_bones', [])
        if not reaction_bones:
            self.warnings.append("没有找到 reaction_bones 定义")
            return

        for idx, bone in enumerate(reaction_bones):
            bone_id = bone.get('bone_id', f'[index {idx}]')

            # 检查必需字段
            required_fields = ['bone_id', 'channel', 'damage_material', 'text_fragments']
            for field in required_fields:
                if field not in bone:
                    self.errors.append(f"reaction_bones[{idx}] ({bone_id}): "
                                      f"缺少必需字段 '{field}'")

            # 检查 channel 是否有效
            valid_channels = {'FATAL', 'EVADE', 'IMPACT', 'SPECIAL'}
            channel = bone.get('channel')
            if channel and channel not in valid_channels:
                self.errors.append(f"reaction_bones[{idx}] ({bone_id}): "
                                  f"无效的 channel '{channel}'")

            # 检查 macro_motion 是否有效
            valid_macros = {
                'RANGED_DIRECT', 'MELEE_CLASH',
                'RANGED_AOE', 'OMNI_DIRECTIONAL', 'ANY'
            }
            macro_motion = bone.get('macro_motion')
            if macro_motion and macro_motion not in valid_macros:
                self.errors.append(f"reaction_bones[{idx}] ({bone_id}): "
                                  f"无效的 macro_motion '{macro_motion}'")

            # 检查材质词冲突（核心验证）
            self._check_material_conflict(bone, idx)

    def _check_material_conflict(self, bone: Dict, idx: int) -> None:
        """检查通用模板是否包含材质词"""
        material = bone.get('damage_material', 'GENERIC')
        bone_id = bone.get('bone_id', f'[index {idx}]')
        fragments = bone.get('text_fragments', [])

        # 只检查 GENERIC 材质的模板
        if material != 'GENERIC':
            return

        found_keywords: Set[str] = set()

        for fragment in fragments:
            if not isinstance(fragment, str):
                continue

            # 检查每个材质关键词
            for keyword in MATERIAL_KEYWORDS:
                if keyword in fragment:
                    found_keywords.add(keyword)

        if found_keywords:
            keywords_str = '、'.join(sorted(found_keywords))
            self.warnings.append(
                f"reaction_bones[{idx}] ({bone_id}): "
                f"通用模板 (damage_material=GENERIC) 包含材质词: [{keywords_str}]。"
                f"根据 Doc 6 机制 3，通用模板应避免具体材质描述。"
            )

    def validate_all(self) -> bool:
        """执行所有验证"""
        if not self.load():
            return False

        self.validate_action_bones()
        self.validate_reaction_bones()

        return len(self.errors) == 0

    def print_report(self) -> None:
        """打印验证报告"""
        print(f"\n{'='*70}")
        print(f"模板验证报告: {self.file_path}")
        print(f"{'='*70}")

        if self.errors:
            print(f"\n❌ 错误 ({len(self.errors)}):")
            for error in self.errors:
                print(f"  - {error}")

        if self.warnings:
            print(f"\n⚠️  警告 ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  - {warning}")

        if not self.errors and not self.warnings:
            print("\n✅ 所有检查通过！")

        print(f"\n{'='*70}")
        print(f"统计: {len(self.errors)} 错误, {len(self.warnings)} 警告")
        print(f"{'='*70}\n")


def find_template_files() -> List[Path]:
    """查找所有模板文件"""
    data_dir = PROJECT_ROOT / 'data' / 'presentation'
    if not data_dir.exists():
        return []

    return list(data_dir.glob('**/*.yaml')) + list(data_dir.glob('**/*.yml'))


def main():
    parser = argparse.ArgumentParser(description='演出模板验证工具')
    parser.add_argument(
        '--file', '-f',
        type=str,
        default=None,
        help='指定要验证的文件路径（默认验证所有）'
    )
    parser.add_argument(
        '--check-material-conflict',
        action='store_true',
        help='仅检查材质词冲突'
    )

    args = parser.parse_args()

    if args.file:
        files = [Path(args.file)]
    else:
        files = find_template_files()

        if not files:
            print("❌ 未找到模板文件 (data/presentation/*.yaml)")
            print("提示：请先创建模板文件，或使用 --file 指定路径")
            return 1

    all_passed = True
    for file_path in files:
        validator = TemplateValidator(str(file_path))

        if args.check_material_conflict:
            if not validator.load():
                continue
            # 仅检查材质词冲突
            reaction_bones = validator.data.get('reaction_bones', [])
            for idx, bone in enumerate(reaction_bones):
                validator._check_material_conflict(bone, idx)
            validator.print_report()
            if validator.warnings:
                all_passed = False
        else:
            if not validator.validate_all():
                all_passed = False
            validator.print_report()

    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
