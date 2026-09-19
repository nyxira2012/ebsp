#!/usr/bin/env python3
"""ComfyUI 远程生图工具（单文件自包含：工程参数内置，提示词内容全由调用方传入）。

分工纪律（2026-09-17 定）：
    脚本只管工程——画布尺寸、品红键底契约、透明抠图、导出缩放、防覆盖
    版本号、四段式命名、朝向纪律默认值（朝右）与背景短语自动追加。
    画风锁/构图约束/动作描述等一切内容词由调用方（人或 AI）在命令行
    position prompt 里完整传入——本管线 cfg=1（turbo 两段采样，负向接
    ConditioningZeroOut），负向提示词通道无效，一切约束只能写进正向，
    故不设 negative 参数。

用法示例：
    # ① 副驾座舱操纵态（cpt，双手向前伸展操控科幻界面，大魄力近大远小纵深）：
    python scripts/artgen/comfy.py -p subpilot \
      "2d日式动漫，1990年代复古日式机甲赛璐璐动画美学，英姿飒爽王牌副驾驶大特写，3/4俯冲动态透视，超广角近大远小镜头景深，大腿以上大特写，头顶留白≥10%，身着机能紧身驾驶服（plugsuit），身体大幅度前倾下压操纵，背部与腰线流线型紧绷，双手向前伸展全神贯注操纵未来科幻机甲（arms extending forward actively piloting futuristic mecha），双手与手臂拉出前后景深纵深，柔顺长发在空中飘扬，眼神凌厉专注锁死敌机，身后完全虚空无背景物体，身姿失重悬空飘浮，画面无任何文字，单人，少女塞拉·玛斯，金色长发，蓝白联邦军驾驶服，身体与视线朝向右前方战场" \
      -o ../ebs-duo/public/assets/subpilots/sp-sayla-cpt-free-v1.webp

    # ② 副驾被动技能高光态（psv，半身大特写，战术指引/精神共鸣/防壁展开，身型曼妙紧致）：
    python scripts/artgen/comfy.py -p subpilot \
      "2d日式动漫，1990年代复古日式机甲赛璐璐动画美学，副驾驶触发被动技能高光立绘，大特写半身像（bust-up dynamic angle framing），大魄力3/4动势斜角构图，超广角镜头近大远小金田透视，头顶留白≥10%，身后完全虚空无背景物体，身姿失重悬空飘浮，身型曲线曼妙优雅紧致，极具魅惑力与战斗张力，未来科幻机能美感，单人，[角色五官发色]，[机能紧身服]，[高光动作与技能特效]，身体与视线朝向右前方战场" \
      --orientation none \
      -o ../ebs-duo/public/assets/subpilots/sp-[角色]-psv-v1.webp

    # 演练：只看装配后的正向 Prompt 与工程规格，不请求服务器
    python scripts/artgen/comfy.py -p subpilot "……" --dry-run

    # 查看槽位工程参数清单
    python scripts/artgen/comfy.py --list-presets
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

# 确保本目录模块（process_asset）直接可导入
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 默认服务器地址，可用环境变量或 --server 覆盖
DEFAULT_SERVER = "http://112.74.103.45:8188"

# ==============================================================================
# 内置 ComfyUI API 工作流模板（Turbo 8步出图 + Qwen CLIP 文本编码 + VAE 解码；
# 两段采样共用同一条 8 步时间轴：1pass er_sde 0-6步保留残差 ->
# 2pass dpmpp_2m_sde 6-999步细化。2pass 必须 add_noise=disable 直接接力残差，
# 若再注噪等于双倍噪声进细化段，出图破碎）
# ==============================================================================
DEFAULT_WORKFLOW_TEMPLATE: dict[str, Any] = json.loads(r"""
{
  "599": {
    "inputs": {
      "add_noise": "enable",
      "noise_seed": ["851", 0],
      "steps": 8,
      "cfg": 1.0,
      "sampler_name": "er_sde",
      "scheduler": "simple",
      "start_at_step": 0,
      "end_at_step": 6,
      "return_with_leftover_noise": "enable",
      "model": ["859", 0],
      "positive": ["627", 0],
      "negative": ["763", 0],
      "latent_image": ["698", 0]
    },
    "class_type": "KSamplerAdvanced",
    "_meta": {"title": "1pass"}
  },
  "627": {
    "inputs": {
      "text": "2d日式动漫，1girl 25yo，3/4身立绘，红色军装白色短裙，在汇报工作，面朝右边，蓝色背景",
      "clip": ["860:755", 0]
    },
    "class_type": "CLIPTextEncode",
    "_meta": {"title": "CLIP文本编码"}
  },
  "698": {
    "inputs": {"width": 800, "height": 1200, "batch_size": 1},
    "class_type": "EmptyLatentImage",
    "_meta": {"title": "Empty Latent Image (Base Dimensions) 初始大小"}
  },
  "763": {
    "inputs": {"conditioning": ["627", 0]},
    "class_type": "ConditioningZeroOut",
    "_meta": {"title": "条件零化"}
  },
  "829": {
    "inputs": {"samples": ["599", 0], "vae": ["860:858", 0]},
    "class_type": "VAEDecode",
    "_meta": {"title": "VAE解码 (1pass)"}
  },
  "851": {
    "inputs": {"seed": 638208442578987},
    "class_type": "SeedNode",
    "_meta": {"title": "Seed 1ST"}
  },
  "859": {
    "inputs": {
      "lora_name": "krea2-Cc-天魔-身材.safetensors",
      "strength_model": 0.0,
      "model": ["860:761", 0]
    },
    "class_type": "LoraLoaderModelOnly",
    "_meta": {"title": "LoRA加载器（仅模型）"}
  },
  "868": {
    "inputs": {
      "add_noise": "disable",
      "noise_seed": ["851", 0],
      "steps": 8,
      "cfg": 1.0,
      "sampler_name": "dpmpp_2m_sde",
      "scheduler": "sgm_uniform",
      "start_at_step": 6,
      "end_at_step": 999,
      "return_with_leftover_noise": "disable",
      "model": ["860:761", 0],
      "positive": ["627", 0],
      "negative": ["763", 0],
      "latent_image": ["599", 0]
    },
    "class_type": "KSamplerAdvanced",
    "_meta": {"title": "2pass"}
  },
  "869": {
    "inputs": {"samples": ["868", 0], "vae": ["860:858", 0]},
    "class_type": "VAEDecode",
    "_meta": {"title": "VAE解码 (2pass)"}
  },
  "871": {
    "inputs": {"anything": ["627", 0]},
    "class_type": "Anything Everywhere",
    "_meta": {"title": "text"}
  },
  "872": {
    "inputs": {
      "anything": ["860:761", 0],
      "anything11": ["860:755", 0],
      "anything12": ["860:858", 0]
    },
    "class_type": "Anything Everywhere",
    "_meta": {"title": "Anything Everywhere"}
  },
  "860:755": {
    "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors", "type": "krea2", "device": "default"},
    "class_type": "CLIPLoader",
    "_meta": {"title": "加载CLIP"}
  },
  "860:858": {
    "inputs": {"vae_name": "qwen_image_vae.safetensors"},
    "class_type": "VAELoader",
    "_meta": {"title": "加载VAE"}
  },
  "860:761": {
    "inputs": {"unet_name": "museByStableYogi_v25INT8Turbo.safetensors", "weight_dtype": "default"},
    "class_type": "UNETLoader",
    "_meta": {"title": "UNet加载器"}
  }
}
""")


# 抠图用背景色短语：追加到提示词末尾——magenta 与后处理色键抠图是硬契约，
# 选了 magenta 就必须让模型画出纯品红底
BACKGROUND_PRESETS = {
    "none": "",
    "white": "纯白色背景，无渐变无阴影",
    "magenta": "纯品红色背景，背景无渐变无阴影，干净单一品红背景 (#FF00FF)，背景完全纯色空白无杂物",
}

# 功能性朝向短语：项目纪律默认朝右（敌侧由前端 StandArt 统一镜像）
ORIENTATION_PRESETS = {
    "right": "面朝右边，身体与视线朝向右方（facing right, looking right）",
    "left": "面朝左边，身体与视线朝向左方（facing left, looking left）",
    "front": "正面正向视角（facing viewer, frontal view）",
    "none": "",
}
DEFAULT_ORIENTATION = "right"

# 轮询间隔与单次生成超时（秒）
POLL_INTERVAL = 2.0
DEFAULT_TIMEOUT = 600.0


# ==============================================================================
# 槽位工程参数（不含任何画风/构图提示词——内容词全由调用方传入；
# 措辞基准模板见模块 docstring 用法示例）
# ==============================================================================

PRESETS: dict[str, dict[str, Any]] = {
    "subpilot": {
        "title": "副驾驶立绘",
        "width": 1024,
        "height": 1024,
        "background": "magenta",
        "has_transparency": True,
        "optimize_colors": None,
        "optimize_quality": 85,
        "optimize_max_side": 512,  # 1024 母版等比缩小至 512x512 导出
    },
    "hero_mecha": {
        "title": "英雄机甲半身立绘",
        "width": 800,
        "height": 1200,
        "background": "magenta",
        "has_transparency": True,
        "optimize_colors": 128,
        "optimize_quality": 80,
    },
    "adjutant": {
        "title": "战术副官全息立绘",
        # 720x1080 生图保五官精度，导出等比缩小至 480x720
        "width": 720,
        "height": 1080,
        "background": "magenta",
        "has_transparency": True,
        "optimize_colors": 128,
        "optimize_quality": 80,
        "optimize_max_side": 720,
    },
    "unit_portrait": {
        "title": "机体档案胸像特写",
        "width": 1024,
        "height": 1024,
        "background": "none",
        "has_transparency": False,
        "optimize_colors": 128,
        "optimize_quality": 80,
    },
    "pilot_avatar": {
        "title": "机师方形正统头像",
        "width": 1024,
        "height": 1024,
        "background": "none",
        "has_transparency": False,
        "optimize_colors": 128,
        "optimize_quality": 80,
    },
    "hangar_bg": {
        "title": "格纳库全景背景底图",
        "width": 1376,
        "height": 768,
        "background": "none",
        "has_transparency": False,
        "is_background": True,
        "optimize_colors": None,
        "optimize_quality": 52,
        "optimize_max_side": 960,
    },
}

# 槽位前缀与形态简写（四段式命名：[前缀]-[角色]-[槽位]-[版本].webp）
PRESET_SLOT_TAGS: dict[str, tuple[str, str]] = {
    "subpilot": ("sp", "cpt"),
    "hero_mecha": ("mech", "std"),
    "adjutant": ("adj", "std"),
    "pilot_avatar": ("plt", "avt"),
    "unit_portrait": ("mech", "avt"),
    "hangar_bg": ("bg", "hangar"),
}

# 各槽位产物落盘子目录（相对 ../ebs-duo/public/assets；仅 -o 缺省时生效）
PRESET_OUT_DIRS: dict[str, str] = {
    "subpilot": "subpilots",
    "adjutant": "adjutants",
    "hero_mecha": "mechas",
    "unit_portrait": "mechas",
    "pilot_avatar": "pilots",
    "hangar_bg": "backgrounds",
}


def resolve_params(
    preset: dict[str, Any] | None,
    width: int | None,
    height: int | None,
    background: str | None,
) -> tuple[int, int, str]:
    """预设 + 显式覆盖 → 实际画布尺寸与背景模式（无预设走通用缺省）。"""
    if preset:
        return (
            width or int(preset["width"]),
            height or int(preset["height"]),
            background or str(preset.get("background", "none")),
        )
    return (width or 800, height or 1200, background or "white")


def resolve_max_side(preset: dict[str, Any] | None, export_max_side: int | None) -> int | None:
    """导出最长边上限：显式参数优先，否则读预设，无则不缩放。"""
    return export_max_side or (preset.get("optimize_max_side") if preset else None)


def scale_note(width: int, height: int, max_side: int | None) -> str:
    """导出缩放说明文案：生图尺寸（必要时附默认导出尺寸）。"""
    if max_side and max(width, height) > max_side:
        scale = max_side / max(width, height)
        return f"{width}x{height} -> 默认导出 {round(width*scale)}x{round(height*scale)}"
    return f"{width}x{height}"


def assemble_prompt(
    user_prompt: str,
    background: str = "none",
    orientation: str = DEFAULT_ORIENTATION,
    is_background: bool = False,
) -> str:
    """内容词 + 朝向短语 + 背景短语 → 最终正向 Prompt（唯一有效通道）。

    纯背景图（is_background）不追加朝向词；magenta 背景短语与后处理
    色键抠图互为硬契约，二者必须同进同出。
    """
    parts = [user_prompt.strip("，,")]
    ori_mode = "none" if is_background else (orientation or "none")
    ori_phrase = ORIENTATION_PRESETS.get(ori_mode, "")
    if ori_phrase:
        parts.append(ori_phrase.strip("，,"))
    bg_phrase = BACKGROUND_PRESETS.get(background, "")
    if bg_phrase:
        parts.append(bg_phrase.strip("，,"))
    return "，".join(p for p in parts if p)


# ==============================================================================
# ComfyUI 客户端与工作流准备
# ==============================================================================

class ComfyUIClient:
    """ComfyUI HTTP API 客户端。"""

    def __init__(self, base_url: str, headers: dict[str, str] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"User-Agent": "EBSP-Artgen/2.0"}
        if headers:
            self.headers.update(headers)

    def submit(self, workflow: dict[str, Any]) -> str:
        """提交工作流到执行队列。"""
        payload = json.dumps(
            {"prompt": workflow, "client_id": str(uuid.uuid4())}
        ).encode("utf-8")
        req_headers = {"Content-Type": "application/json", **self.headers}
        req = urllib.request.Request(
            f"{self.base_url}/prompt",
            data=payload,
            headers=req_headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)["prompt_id"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"提交工作流失败（HTTP {exc.code}）：{detail}") from exc

    def wait(self, prompt_id: str, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
        """阻塞等待指定任务执行完成。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with urllib.request.urlopen(
                f"{self.base_url}/history/{prompt_id}", timeout=30
            ) as resp:
                history: dict[str, dict[str, Any]] = json.load(resp)
            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(f"工作流执行失败：{json.dumps(status.get('messages'), ensure_ascii=False)}")
                return entry["outputs"]
            time.sleep(POLL_INTERVAL)
        raise TimeoutError(f"等待 {timeout}s 后任务仍未完成：{prompt_id}")

    def download(self, image_ref: dict[str, str]) -> bytes:
        """从服务器 /view 端点下载生成图片字节流。"""
        query = urllib.parse.urlencode(image_ref)
        with urllib.request.urlopen(f"{self.base_url}/view?{query}", timeout=60) as resp:
            return resp.read()


def prepare_workflow(
    template: dict[str, dict[str, object]],
    prompt: str,
    seed: int,
    width: int,
    height: int,
    filename_prefix: str,
    two_pass: bool = True,
) -> dict[str, dict[str, Any]]:
    """基于模板生成待提交的工作流副本，支持 1pass / 2pass 动态切换。

    种子只经 SeedNode 一处注入（1pass/2pass 的 noise_seed 均引用它）；
    产物落盘由脚本端统一追加的 __save__ 节点承担，模板内不保存存档节点。
    """
    workflow: dict[str, dict[str, Any]] = copy.deepcopy(template)

    # 采样模式调整：2pass 接力（1pass 0-6 步留残差 -> 2pass 6-999 步细化）
    # vs 1pass 全程 8 步出图（清理 2pass 相关节点）
    if two_pass:
        save_source: list[object] = ["869", 0]
    else:
        workflow.pop("868", None)
        workflow.pop("869", None)
        save_source = ["829", 0]
    inputs_599 = workflow["599"].setdefault("inputs", {})
    inputs_599["start_at_step"] = 0
    inputs_599["end_at_step"] = 6 if two_pass else 8
    inputs_599["return_with_leftover_noise"] = "enable" if two_pass else "disable"
    if two_pass:
        inputs_868 = workflow["868"].setdefault("inputs", {})
        inputs_868["start_at_step"] = 6
        inputs_868["end_at_step"] = 999
        inputs_868["return_with_leftover_noise"] = "disable"

    for workflow_node in workflow.values():
        inputs = workflow_node.get("inputs", {})
        class_type = str(workflow_node.get("class_type", ""))
        if class_type == "CLIPTextEncode" and "text" in inputs:
            inputs["text"] = prompt
        elif class_type == "EmptyLatentImage":
            inputs["width"] = width
            inputs["height"] = height
        elif class_type == "SeedNode":
            inputs["seed"] = seed

    workflow["__save__"] = {
        "class_type": "SaveImage",
        "inputs": {"images": save_source, "filename_prefix": filename_prefix},
    }
    return workflow


# ==============================================================================
# 后处理与落盘
# ==============================================================================

def postprocess_and_save(
    raw_bytes: bytes,
    output_path: Path,
    preset: dict[str, Any] | None = None,
    skip_postprocess: bool = False,
    generate_preview: bool = False,
    max_side: int | None = None,
) -> list[Path]:
    """处理产物并在本地落盘。若命中预设则自动执行抠图/优化/缩放。"""
    from PIL import Image

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(BytesIO(raw_bytes))
    saved_files: list[Path] = []
    actual_max_side = resolve_max_side(preset, max_side)

    if preset and not skip_postprocess:
        import process_asset

        # 1. 自动透明抠图
        if preset.get("has_transparency"):
            try:
                key_mode = "magenta" if preset.get("background") == "magenta" else preset.get("background", "auto")
                image = process_asset.remove_background(image, key=key_mode)
                print(f"[{preset['title']}] 已自动执行色键透明抠图 (key={key_mode})")
            except Exception as e:
                print(f"[警告] 自动抠图跳过: {e}", file=sys.stderr)

        # 2. 自动生成 UI 遮挡预览图（仅在显式请求 --preview 时生成，避免污染目录）
        if preset.get("is_background") and generate_preview:
            try:
                preview_path = output_path.with_stem(f"{output_path.stem}_preview")
                preview_img = process_asset.render_occlusion_preview(image)
                preview_img.save(preview_path, "WEBP", quality=85)
                saved_files.append(preview_path)
                print(f"[{preset['title']}] 已自动生成遮挡质检预览图 -> {preview_path.name}")
            except Exception as e:
                print(f"[警告] 遮挡预览跳过: {e}", file=sys.stderr)

        # 3. 自动调色板压缩优化与等比缩放
        try:
            scheme, payload = process_asset.optimize_image_bytes(
                image,
                colors=preset.get("optimize_colors"),
                quality=preset.get("optimize_quality", 80),
                max_side=actual_max_side,
            )
            output_path.write_bytes(payload)
            saved_files.append(output_path)
            out_img = Image.open(BytesIO(payload))
            dim_str = f"{out_img.width}x{out_img.height}"
            print(f"[{preset['title']}] 调色板优化与缩放完成 ({scheme}, {dim_str}): {len(raw_bytes)/1024:.0f}KB -> {len(payload)/1024:.0f}KB")
            return saved_files
        except Exception as e:
            print(f"[警告] 调色板优化跳过，直接保存: {e}", file=sys.stderr)

    # 普通保存流程（若有指定缩放，执行等比缩小）
    if actual_max_side is not None and max(image.size) > actual_max_side:
        scale = actual_max_side / max(image.size)
        image = image.resize(
            (round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS
        )

    suffix = output_path.suffix.lower()
    if suffix == ".webp":
        image.save(output_path, "WEBP", quality=80)
    elif suffix in (".jpg", ".jpeg"):
        image.convert("RGB").save(output_path, "JPEG", quality=92)
    else:
        if actual_max_side is not None:
            image.save(output_path)
        else:
            output_path.write_bytes(raw_bytes)
    saved_files.append(output_path)
    return saved_files


def resolve_output_path(target_path: Path, overwrite: bool = False) -> Path:
    """若目标文件已存在且未开启 overwrite，则自动递增版本号（如 stem-v2.webp, stem-v3.webp），避免覆盖既有资产。
    严格遵循四段式命名规范：[前缀]-[角色/机体]-[槽位/形态]-[版本号].webp
    """
    if overwrite or not target_path.exists():
        return target_path
    stem = target_path.stem
    suffix = target_path.suffix
    parent = target_path.parent

    # 检查当前文件名是否已包含版本号后缀，例如 -v1, -v2 或历史遗留 _1, _2
    m_v = re.search(r"^(.*?)-v(\d+)$", stem)
    m_us = re.search(r"^(.*?)_(\d+)$", stem)
    if m_v:
        base_stem = m_v.group(1)
        counter = int(m_v.group(2)) + 1
    elif m_us:
        base_stem = m_us.group(1)
        counter = int(m_us.group(2)) + 1
    else:
        base_stem = stem
        counter = 2  # 原图视为第1版，下一版本为 -v2

    while True:
        candidate = parent / f"{base_stem}-v{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def generate(
    prompt: str,
    output_path: Path,
    preset_name: str | None = None,
    server: str = DEFAULT_SERVER,
    seed: int | None = None,
    width: int | None = None,
    height: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    background: str | None = None,
    orientation: str = DEFAULT_ORIENTATION,
    skip_postprocess: bool = False,
    generate_preview: bool = False,
    export_max_side: int | None = None,
    two_pass: bool = True,
    overwrite: bool = False,
) -> list[Path]:
    """核心生图 API。prompt 为完整内容词（画风+构图+主体），工程参数取预设。"""
    actual_output_path = output_path if overwrite else resolve_output_path(output_path, overwrite=False)
    if actual_output_path != output_path:
        print(f"[防覆盖保护] 目标文件 {output_path.name} 已存在，自动重命名并保存为 -> {actual_output_path.name}")

    actual_seed = seed if seed is not None else random.randint(0, 2**48)
    preset = PRESETS.get(preset_name) if preset_name else None
    actual_width, actual_height, bg_mode = resolve_params(preset, width, height, background)
    final_prompt = assemble_prompt(
        prompt,
        background=bg_mode,
        orientation=orientation,
        is_background=bool(preset and preset.get("is_background")),
    )

    # 工作流模板：工程参数内置单一份，避免外部 JSON 漂移
    workflow = prepare_workflow(
        DEFAULT_WORKFLOW_TEMPLATE,
        prompt=final_prompt,
        seed=actual_seed,
        width=actual_width,
        height=actual_height,
        filename_prefix=actual_output_path.stem,
        two_pass=two_pass,
    )

    client = ComfyUIClient(server)
    tag = f"[{preset['title']}] " if preset else ""
    pass_tag = " [2次采样]" if two_pass else " [单次采样]"
    print(f"{tag}提交 ComfyUI 任务 · seed={actual_seed} · {actual_width}x{actual_height}{pass_tag}...")
    prompt_id = client.submit(workflow)
    print(f"{tag}等待生成 (ID: {prompt_id})...")
    outputs = client.wait(prompt_id, timeout=timeout)

    refs = [
        ref
        for node_out in outputs.values()
        for ref in node_out.get("images", [])  # type: ignore[union-attr]
        if ref.get("type") == "output"
    ]
    if not refs:
        raise RuntimeError("ComfyUI 执行完毕但未返回任何图片产物")

    raw_bytes = client.download(dict(refs[0]))
    return postprocess_and_save(
        raw_bytes,
        actual_output_path,
        preset=preset,
        skip_postprocess=skip_postprocess,
        generate_preview=generate_preview,
        max_side=export_max_side,
    )


# ==============================================================================
# CLI 入口
# ==============================================================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """命令行参数解析。"""
    parser = argparse.ArgumentParser(
        description="E.B.S.P 生图工具：工程参数（尺寸/抠底/导出/命名/朝向）内置，"
                    "提示词内容（画风+构图+主体）由调用方完整传入——措辞基准模板见模块 docstring 用法示例",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("prompt", nargs="?", default="", help="完整内容词（画风+构图+主体）；脚本自动追加朝向与背景短语")
    parser.add_argument("-p", "--preset", choices=list(PRESETS.keys()), default=None, help="槽位工程参数（尺寸/抠底/导出缩放/命名）")
    parser.add_argument("-o", "--output", type=Path, default=None, help="输出文件路径（支持 .png / .jpg / .webp）")
    parser.add_argument("--overwrite", action="store_true", default=False, help="若目标文件已存在，允许直接覆盖（默认不覆盖，自动递增版本号如 -v2, -v3 严格保护已有资产）")
    parser.add_argument("--server", default=DEFAULT_SERVER, help="ComfyUI 服务器地址")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，缺省时随机")
    parser.add_argument("--width", type=int, default=None, help="画布宽（缺省从预设读取或 800）")
    parser.add_argument("--height", type=int, default=None, help="画布高（缺省从预设读取或 1200）")
    parser.add_argument("--export-max-side", "--max-side", type=int, default=None, dest="export_max_side", help="导出缩放：最长边像素上限（等比缩小），缺省从预设读取")
    parser.add_argument("--orientation", choices=sorted(ORIENTATION_PRESETS.keys()), default=DEFAULT_ORIENTATION, help="主体朝向短语：默认 right（项目纪律朝右出图，敌侧由前端镜像）")
    parser.set_defaults(two_pass=True)
    parser.add_argument("--two-pass", dest="two_pass", action="store_true", help="显式指定开启 2次采样细化（默认已开启，1pass 0-6步 + 2pass dpmpp_2m_sde 去噪）")
    parser.add_argument("--single-pass", "--no-two-pass", dest="two_pass", action="store_false", help="仅执行单次采样（8步出图，跳过2pass去噪）")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="单次生成超时（秒）")
    parser.add_argument("--background", choices=sorted(BACKGROUND_PRESETS), default=None, help="覆盖背景色预设（magenta 与自动抠图为硬契约）")
    parser.add_argument("--dry-run", action="store_true", help="演练模式：仅打印装配后的提示词与规格，不请求服务器")
    parser.add_argument("--list-presets", action="store_true", help="列出所有槽位工程参数")
    parser.add_argument("--skip-postprocess", action="store_true", help="跳过自动抠图与调色板优化")
    parser.add_argument("--preview", action="store_true", help="是否同时生成带 UI 遮挡框的 *_preview.webp 质检图（默认不生成）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """脚本入口。"""
    args = parse_args(argv)

    if args.list_presets:
        print("\n" + "=" * 76)
        print("E.B.S.P 槽位工程参数清单（提示词内容自备，措辞基准见模块 docstring）:")
        print("=" * 76)
        for key, p in PRESETS.items():
            trans = " [自动抠图]" if p.get("has_transparency") else ""
            bg_prev = " [遮挡质检]" if p.get("is_background") else ""
            size_str = scale_note(int(p['width']), int(p['height']), p.get("optimize_max_side"))
            print(f"• {key:<14} | {p['title']} ({size_str}){trans}{bg_prev}")
        print()
        return 0

    if not args.prompt and not args.dry_run:
        print("错误: 请提供提示词 prompt。输入 -h 查看帮助。")
        return 1

    if args.dry_run:
        preset = PRESETS.get(args.preset) if args.preset else None
        w, h, bg_mode = resolve_params(preset, args.width, args.height, args.background)
        final = assemble_prompt(
            args.prompt,
            background=bg_mode,
            orientation=args.orientation,
            is_background=bool(preset and preset.get("is_background")),
        )
        actual_max_side = resolve_max_side(preset, args.export_max_side)
        size_info = scale_note(w, h, actual_max_side)
        sampling_info = "2次采样 (1pass er_sde 0-6步 -> 2pass dpmpp_2m_sde 6-999步)" if args.two_pass else "单次采样 (1pass 8步)"
        print("=" * 72)
        print(f"【DRY-RUN】{preset['title'] if preset else '无预设'} ({args.preset or '-'}) · {size_info} · {sampling_info}")
        print("-" * 72)
        print(f"【装配后正向 Prompt（唯一有效通道，负向在本管线无效）】:\n  {final}\n")
        print("=" * 72)
        return 0

    if args.output is None:
        duo_pub = Path("../ebs-duo/public/assets")
        duo_assets = Path("../ebs-duo/assets")
        rand_id = random.randint(1000, 9999)
        if args.preset in PRESET_SLOT_TAGS:
            prefix, slot = PRESET_SLOT_TAGS[args.preset]
            stem = f"{prefix}-{slot}-{rand_id}-v1"
        else:
            stem = f"gen-{args.preset or 'asset'}-{rand_id}-v1"

        if duo_pub.exists():
            target_dir = duo_pub / PRESET_OUT_DIRS.get(args.preset or "", "")
        elif duo_assets.exists():
            target_dir = duo_assets
        else:
            target_dir = Path("assets")
        args.output = target_dir / f"{stem}.webp"

    saved = generate(
        prompt=args.prompt,
        output_path=args.output,
        preset_name=args.preset,
        server=args.server,
        seed=args.seed,
        width=args.width,
        height=args.height,
        timeout=args.timeout,
        background=args.background,
        orientation=args.orientation,
        skip_postprocess=args.skip_postprocess,
        generate_preview=args.preview,
        export_max_side=args.export_max_side,
        two_pass=args.two_pass,
        overwrite=args.overwrite,
    )
    for path in saved:
        print(f"产物已落盘：{path}（{path.stat().st_size / 1024:.0f} KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
