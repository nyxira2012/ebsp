#!/usr/bin/env python3
"""E.B.S.P 美术资产二次处理统一工具（抠图 + 调色板优化 + 遮挡预检）。

业务背景：
    本脚本统一负责对已有图像资产的全部本地算法后处理，包含三大功能模块：
    1. 【背景透明抠除】(remove_bg)：
       - 色键抠图（magenta / auto）：自动采样边缘品红并消解溢色（Spill Suppression），一并扣除手臂、线缆封闭镂空；
       - 白底连通域抠图（white）：利用 scipy 识别与画布连通的近白区域，保护角色白军装/白手套内部。
    2. 【调色板量化与极限压缩】(optimize_asset)：
       - 针对日式 2D 动漫赛璐璐平涂风格，进行调色板量化（如 128/192 色）；
       - WebP method=6 深度编码，量化版与直转版择优落盘，体积通常压缩 40%~70%。
    3. 【UI 遮挡质检预检】(preview_bg)：
       - 按照 1920x1080 黄金战术安全舱组件实测坐标，在背景候选图上绘制 UI 实体遮挡框与核心透视安全窗。

用法示例：
    # 1. 一键全流程处理（最常用：自动色键抠图 + 赛璐璐量化压缩，原地替换）
    python scripts/artgen/process_asset.py --pipeline -i assets/mecha.webp

    # 2. 仅抠图（自动检测边缘色键，输出同名或另存）
    python scripts/artgen/process_asset.py --remove-bg --key auto -i assets/adjutant.webp

    # 3. 仅优化体积（支持 character 预设或 bg 预设）
    python scripts/artgen/process_asset.py --optimize --preset-opt character -i assets/*.webp
    python scripts/artgen/process_asset.py --optimize --preset-opt bg -i assets/bg.webp

    # 4. 生成背景 UI 遮挡质检图（产出 *_preview.webp）
    python scripts/artgen/process_asset.py --preview assets/bg.webp

    # 5. 查看白底图疑似镂空坐标（辅助白底精准抠图）
    python scripts/artgen/process_asset.py --suggest assets/white_bg_char.webp
"""

from __future__ import annotations

import argparse
import os
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

# ==============================================================================
# 模块一：背景透明抠除算法 (Background Removal)
# ==============================================================================

DEFAULT_THRESHOLD = 28
KEY_COLORS = {"white": (255, 255, 255), "magenta": (255, 0, 255)}
BORDER_SAMPLE_PX = 3
SPILL_DELTA = 15
GAP_PURITY_MAX = 5.0
GAP_AREA_MIN = 0.003
ALPHA_RATIO_MIN = 0.15
ALPHA_RATIO_MAX = 0.85


def _border_connected(labeled: np.ndarray) -> set[int]:
    """获取与画布四边接触的连通域标签集合。"""
    return set(
        np.unique(
            np.concatenate([labeled[0], labeled[-1], labeled[:, 0], labeled[:, -1]])
        )
    ) - {0}


def suggest_gap_seeds(image: Image.Image, threshold: int = DEFAULT_THRESHOLD) -> list[tuple[int, int, float, float]]:
    """检测疑似镂空白底的坐标，供 --seeds 人工确认。"""
    arr = np.asarray(image.convert("RGB")).astype(np.int16)
    dist = 255 - arr.min(axis=2)
    labeled, n = ndimage.label(dist < threshold)
    border = _border_connected(labeled)
    areas = np.bincount(labeled.ravel(), minlength=n + 1)
    means = ndimage.mean(dist, labeled, index=np.arange(1, n + 1))

    suspects: list[tuple[int, int, float, float]] = []
    for i in range(1, n + 1):
        if i in border or areas[i] < GAP_AREA_MIN * labeled.size:
            continue
        if means[i - 1] >= GAP_PURITY_MAX:
            continue
        ys, xs = np.nonzero(labeled == i)
        suspects.append((int(xs.mean()), int(ys.mean()), float(areas[i] / labeled.size), float(means[i - 1])))
    suspects.sort(key=lambda s: -s[2])
    return suspects


def _sample_border_key(arr: np.ndarray, width_px: int = BORDER_SAMPLE_PX) -> np.ndarray:
    """从画布四边采样背景色中位数（应对生成模型轻微色偏）。"""
    frame = np.concatenate(
        [
            arr[:width_px].reshape(-1, 3),
            arr[-width_px:].reshape(-1, 3),
            arr[:, :width_px].reshape(-1, 3),
            arr[:, -width_px:].reshape(-1, 3),
        ]
    )
    return np.median(frame, axis=0)


def remove_white_background(
    image: Image.Image,
    threshold: int = DEFAULT_THRESHOLD,
    gap_seeds: tuple[tuple[int, int], ...] = (),
    key: str = "white",
) -> Image.Image:
    """将图片的纯色背景替换为透明通道。

    Args:
        image: RGB 模式的输入立绘。
        threshold: 与背景色的最大通道距离小于该值视为背景。
        gap_seeds: 白底模式下封闭镂空白底的种子坐标。
        key: ``white`` 走边界连通域分析；``magenta`` 为固定色键色；
            ``auto`` 从画布四边实测背景色（推荐品红底使用）。后两者按纯色键直接阈值抠图。
    """
    arr = np.asarray(image.convert("RGB")).astype(np.int16)
    if key == "auto":
        key_arr = _sample_border_key(arr)
    else:
        key_arr = np.array(KEY_COLORS.get(key, KEY_COLORS["white"]))
    near_bg = np.abs(arr - key_arr).max(axis=2) < threshold

    if key == "white":
        labeled, _ = ndimage.label(near_bg)
        border = _border_connected(labeled)
        background = np.isin(labeled, list(border))

        height, width = near_bg.shape
        for x, y in gap_seeds:
            comp = labeled[min(y, height - 1), min(x, width - 1)]
            if comp != 0 and comp not in border:
                background |= labeled == comp
    else:
        background = near_bg

    # 腐蚀 1px 去色键色晕边，再高斯羽化软化轮廓
    alpha = ndimage.binary_erosion(~background, iterations=1)
    alpha = ndimage.gaussian_filter(alpha.astype(np.float32), sigma=0.8)
    alpha_u8 = np.clip(alpha * 255, 0, 255).astype(np.uint8)

    rgb = np.asarray(image.convert("RGB")).astype(np.int16)
    if key != "white":
        # 溢色消除：抑制模型边缘色键 rim light 泛光
        spill = (rgb[..., 0] > rgb[..., 1] + SPILL_DELTA) & (rgb[..., 2] > rgb[..., 1] + SPILL_DELTA)
        cap = rgb[..., 1] + SPILL_DELTA
        rgb = np.dstack(
            [
                np.where(spill, np.minimum(rgb[..., 0], cap), rgb[..., 0]),
                rgb[..., 1],
                np.where(spill, np.minimum(rgb[..., 2], cap), rgb[..., 2]),
            ]
        )

    rgba = np.dstack([rgb.astype(np.uint8), alpha_u8])
    return Image.fromarray(rgba, mode="RGBA")


# 别名供外部模块调用
remove_background = remove_white_background


def check_quality(alpha_u8: np.ndarray) -> list[str]:
    """对抠图结果做启发式透明占比质量检查。"""
    warnings: list[str] = []
    transparent_ratio = float((alpha_u8 < 128).mean())
    if not ALPHA_RATIO_MIN <= transparent_ratio <= ALPHA_RATIO_MAX:
        warnings.append(
            f"透明占比 {transparent_ratio:.0%} 超出合理区间（15%~85%），可能漏抠或误抠"
        )
    return warnings


# ==============================================================================
# 模块二：调色板量化与极限压缩 (Asset Optimization)
# ==============================================================================

def _encode_webp(image: Image.Image, quality: int) -> bytes:
    """以指定质量将图片编码为 WebP 字节流（method=6 深度搜索最佳压缩）。"""
    buf = BytesIO()
    image.save(buf, "WEBP", quality=quality, method=6)
    return buf.getvalue()


def optimize_image_bytes(
    image: Image.Image,
    colors: int | None = 128,
    quality: int = 90,
    max_side: int | None = None,
) -> tuple[str, bytes]:
    """在内存中进行 WebP 调色板优化与编码。"""
    has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
    converted = image.convert("RGBA" if has_alpha else "RGB")

    if max_side is not None and max(converted.size) > max_side:
        scale = max_side / max(converted.size)
        size = (round(converted.width * scale), round(converted.height * scale))
        converted = converted.resize(size, Image.LANCZOS)

    candidates: list[tuple[str, bytes]] = [
        ("webp-direct", _encode_webp(converted, quality)),
    ]
    if colors is not None and colors > 0:
        if has_alpha:
            quantized = converted.quantize(colors=colors, method=Image.FASTOCTREE)
        else:
            quantized = converted.quantize(colors=colors, method=Image.MEDIANCUT)
        candidates.append(("quantized", _encode_webp(quantized.convert(converted.mode), quality)))

    return min(candidates, key=lambda item: len(item[1]))


def optimize(
    path: Path,
    output: Path,
    colors: int | None,
    quality: int,
    max_side: int | None,
) -> tuple[int, int, str]:
    """优化单张图片并落盘。"""
    image = Image.open(path)
    name, payload = optimize_image_bytes(image, colors=colors, quality=quality, max_side=max_side)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    return path.stat().st_size, len(payload), name


# ==============================================================================
# 模块三：UI 遮挡预检与透视窗标注 (Background Preview)
# ==============================================================================

def get_font(size: int = 14) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """获取支持中文渲染的系统字体。"""
    candidates = [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for font_path in candidates:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass
    return ImageFont.load_default()


OCCLUDERS: list[tuple[float, float, float, float, str]] = [
    (0.0, 0.0, 100.0, 5.56, "顶栏 (TopBar)"),
    (9.38, 7.04, 22.14, 38.5, "简报板 (Briefing)"),
    (9.38, 76.0, 40.10, 94.63, "通讯台 (Comms Deck)"),
    (41.1, 10.9, 72.5, 94.63, "机甲立柱 (Hero Mecha C位/可置空)"),
    (68.75, 7.8, 90.62, 67.0, "档案夹 (Dossier Stack)"),
    (81.8, 86.2, 90.62, 92.8, "出击台 (Sortie Dock)"),
    (0.0, 94.63, 100.0, 100.0, "底部主控坞 (Command Dock)"),
]

HOLO_OCCLUDER: tuple[float, float, float, float, str] = (
    21.5, 32.4, 39.5, 76.0, "全息副官 (Holo Adjutant / 可关)"
)

VISIBLE_WINDOWS: list[tuple[float, float, float, float, str]] = [
    (9.38, 38.5, 22.14, 76.0, "左翼核心透视窗"),
    (22.14, 5.56, 41.1, 32.4, "左中高空透视窗"),
    (68.75, 67.0, 81.8, 86.2, "右下透视带"),
    (0.0, 5.56, 9.38, 94.63, "左舷通透带"),
    (90.62, 5.56, 100.0, 94.63, "右舷通透带"),
]

REGIONAL_ZONES: list[tuple[float, float, str]] = [
    (0.0, 41.1, "ZONE A: 左翼次级整备区 (作业机甲 / 脚手架 / 地勤)"),
    (41.1, 72.5, "ZONE B: 中央主泊位 (张开夹爪 / 空置转盘 / 纵深巨门)"),
    (72.5, 100.0, "ZONE C: 右翼深舱 (暗部舱壁 / 货运滑轨 / 出击航标)"),
]

OCCLUDER_FILL = (10, 14, 22, 195)
OCCLUDER_EDGE = (220, 75, 75, 255)
HOLO_FILL = (8, 30, 42, 140)
HOLO_EDGE = (56, 189, 248, 255)
WINDOW_EDGE = (74, 222, 128, 255)
ZONE_LINE = (245, 158, 11, 220)


def render_occlusion_preview(image: Image.Image) -> Image.Image:
    """在背景图片上渲染 UI 遮挡面板、全息位、三大构图分区与可见视窗标注图层。"""
    base = image.convert("RGB")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = base.size

    font_main = get_font(max(12, int(height * 0.016)))
    font_zone = get_font(max(13, int(height * 0.018)))

    # 1. 绘制三大功能分区
    for z_start, z_end, z_label in REGIONAL_ZONES:
        xs = z_start / 100 * width
        xe = z_end / 100 * width
        if z_end < 99.0:
            for y in range(0, int(height), 14):
                draw.line([(xe, y), (xe, min(y + 7, height))], fill=ZONE_LINE, width=2)
        tag_y = 6.2 / 100 * height
        bbox = font_zone.getbbox(z_label)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        badge_box = (xs + 8, tag_y, xs + 12 + tw, tag_y + th + 6)
        draw.rectangle(badge_box, fill=(18, 14, 8, 230), outline=ZONE_LINE, width=1)
        draw.text((xs + 10, tag_y + 2), z_label, font=font_zone, fill=ZONE_LINE)

    # 2. 绘制常规 UI 实体遮挡面板
    for x0, y0, x1, y1, label in OCCLUDERS:
        box = (x0 / 100 * width, y0 / 100 * height, x1 / 100 * width, y1 / 100 * height)
        draw.rectangle(box, fill=OCCLUDER_FILL, outline=OCCLUDER_EDGE, width=2)
        bbox = font_main.getbbox(label)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.rectangle((box[0] + 4, box[1] + 3, box[0] + 8 + tw, box[1] + th + 7), fill=(10, 14, 22, 230))
        draw.text((box[0] + 6, box[1] + 4), label, font=font_main, fill=OCCLUDER_EDGE)

    # 3. 绘制全息副官立绘位
    hx0, hy0, hx1, hy1, hlabel = HOLO_OCCLUDER
    holo_box = (hx0 / 100 * width, hy0 / 100 * height, hx1 / 100 * width, hy1 / 100 * height)
    draw.rectangle(holo_box, fill=HOLO_FILL, outline=HOLO_EDGE, width=2)
    bbox = font_main.getbbox(hlabel)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.rectangle((holo_box[0] + 4, holo_box[1] + 3, holo_box[0] + 8 + tw, holo_box[1] + th + 7), fill=(8, 24, 36, 230))
    draw.text((holo_box[0] + 6, holo_box[1] + 4), hlabel, font=font_main, fill=HOLO_EDGE)

    # 4. 绘制核心可见视窗
    for x0, y0, x1, y1, label in VISIBLE_WINDOWS:
        window_box = (x0 / 100 * width, y0 / 100 * height, x1 / 100 * width, y1 / 100 * height)
        for offset in range(3):
            draw.rectangle(
                (window_box[0] - offset, window_box[1] - offset, window_box[2] + offset, window_box[3] + offset),
                outline=WINDOW_EDGE,
            )
        vtext = f"VISIBLE ({label})"
        bbox = font_main.getbbox(vtext)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.rectangle((window_box[0] + 4, window_box[1] + 5, window_box[0] + 8 + tw, window_box[1] + th + 9), fill=(10, 24, 14, 230))
        draw.text((window_box[0] + 6, window_box[1] + 6), vtext, font=font_main, fill=WINDOW_EDGE)

    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")


def make_preview(path: Path, output: Path) -> None:
    """为单张候选背景图生成带遮挡标注的预览图。"""
    image = Image.open(path)
    result = render_occlusion_preview(image)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output, "WEBP", quality=85)
    print(f"[遮挡预检] {path.name} -> {output.name}")


# ==============================================================================
# CLI 入口与调度
# ==============================================================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="E.B.S.P 美术资产二次处理统一工具（抠图、调色板优化与遮挡预检）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("inputs", type=Path, nargs="*", help="输入图片路径（支持批量）")
    parser.add_argument("-i", "--in-place", action="store_true", help="原地覆盖而不是另存")
    parser.add_argument("-o", "--output", type=Path, default=None, help="输出路径（单个输入时可用）")

    # 流程模式
    mode_group = parser.add_argument_group("处理模式选项（可组合）")
    mode_group.add_argument("--pipeline", action="store_true", help="全流程模式：自动抠图 + 赛璐璐调色板压缩")
    mode_group.add_argument("--remove-bg", action="store_true", help="执行背景抠除并生成 Alpha 通道")
    mode_group.add_argument("--optimize", action="store_true", help="执行调色板量化与 WebP 深度压缩")
    mode_group.add_argument("--preview", action="store_true", help="生成带有 UI 遮挡区域标注的 *_preview.webp 质检图")
    mode_group.add_argument("--suggest", action="store_true", help="白底模式下输出疑似封闭镂空白底的种子坐标")

    # 抠图参数
    bg_group = parser.add_argument_group("抠图参数选项")
    bg_group.add_argument("--key", choices=["auto", "magenta", "white"], default="auto", help="背景色模式（auto 自动采样，magenta 固定品红，white 边界连通域）")
    bg_group.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD, help="背景色距离容差阈值")
    bg_group.add_argument("--seeds", type=str, default="", help="白底封闭镂空种子坐标，格式如 'x1,y1;x2,y2'")

    # 优化参数
    opt_group = parser.add_argument_group("优化参数选项")
    opt_group.add_argument("--preset-opt", choices=["character", "bg"], default=None, help="优化预设：character（立绘量化，缺省192色/q72），bg（背景图，无量化/限宽960/q50）")
    opt_group.add_argument("--colors", type=int, default=None, help="量化色数（None 不做量化）")
    opt_group.add_argument("--quality", type=int, default=None, help="WebP 编码质量")
    opt_group.add_argument("--max-side", type=int, default=None, help="最长边像素上限，超出等比缩小")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.inputs:
        print("错误: 请提供至少一个输入图片路径。输入 -h 查看帮助。")
        return 1

    # 解析种子坐标
    gap_seeds: list[tuple[int, int]] = []
    if args.seeds:
        for pair in args.seeds.split(";"):
            parts = pair.split(",")
            if len(parts) == 2:
                gap_seeds.append((int(parts[0].strip()), int(parts[1].strip())))

    # 仅检测镂空坐标模式
    if args.suggest:
        for path in args.inputs:
            img = Image.open(path)
            suspects = suggest_gap_seeds(img, threshold=args.threshold)
            print(f"[{path.name}] 疑似镂空白底点（前 5 个）：")
            for x, y, area, mean in suspects[:5]:
                print(f"  • ({x}, {y}) - 面积占比: {area:.2%}, 白度均值: {mean:.1f}")
        return 0

    # 自动推断行为
    do_remove_bg = args.remove_bg or args.pipeline or (args.key != "auto")
    do_optimize = args.optimize or args.pipeline or (args.preset_opt is not None) or (args.colors is not None)
    do_preview = args.preview

    # 如果什么标志都没传，默认执行 pipeline
    if not (do_remove_bg or do_optimize or do_preview):
        do_remove_bg = True
        do_optimize = True

    # 优化参数缺省计算
    preset_opt = args.preset_opt or "character"
    if preset_opt == "bg":
        colors = args.colors
        quality = 50 if args.quality is None else args.quality
        max_side = 960 if args.max_side is None else args.max_side
    else:
        colors = 192 if args.colors is None else args.colors
        quality = 72 if args.quality is None else args.quality
        max_side = args.max_side

    for path in args.inputs:
        if not path.exists():
            print(f"警告: 文件不存在，跳过: {path}", file=sys.stderr)
            continue

        raw_size = path.stat().st_size
        img = Image.open(path)

        # 1. 遮挡预检（生成独立 preview 文件）
        if do_preview:
            preview_target = path.with_name(f"{path.stem}_preview.webp")
            make_preview(path, preview_target)

        # 2. 抠图处理
        if do_remove_bg:
            img = remove_white_background(
                img,
                threshold=args.threshold,
                gap_seeds=tuple(gap_seeds),
                key=args.key,
            )
            # 质量告警
            alpha_arr = np.asarray(img.split()[-1])
            for warn in check_quality(alpha_arr):
                print(f"[{path.name} 质量告警] {warn}", file=sys.stderr)

        # 3. 确定最终输出路径
        if args.in_place or len(args.inputs) > 1:
            out_target = path if args.in_place else path.with_stem(f"{path.stem}_processed")
        else:
            out_target = args.output or (path if args.in_place else path.with_stem(f"{path.stem}_processed"))

        # 4. 优化与落盘
        if do_optimize:
            scheme, payload = optimize_image_bytes(img, colors=colors, quality=quality, max_side=max_side)
            out_target.parent.mkdir(parents=True, exist_ok=True)
            out_target.write_bytes(payload)
            new_size = len(payload)
            ratio = (1 - new_size / raw_size) * 100 if raw_size else 0
            print(f"[处理完成] {path.name} -> {out_target.name} ({raw_size/1024:.0f}KB -> {new_size/1024:.0f}KB, -{ratio:.0f}%, {scheme})")
        else:
            out_target.parent.mkdir(parents=True, exist_ok=True)
            img.save(out_target, "WEBP", quality=85)
            print(f"[处理完成] {path.name} -> {out_target.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
