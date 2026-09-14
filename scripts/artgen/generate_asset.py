#!/usr/bin/env python3
"""ComfyUI 远程生图工具（集成预设与自动化后处理）。

业务背景：
    E.B.S.P 落地页（prototype/）采用 2D 日式动漫赛璐璐风格的机甲科幻美术，
    素材由远程 ComfyUI 服务器（turbo 快速模型，8 步出图）生成。
    本脚本将功能性 Prompt（画风锁、构图约束、品红色键底）内置为槽位预设，
    使用者调用时只需输入纯业务内容词（机体/人物设定）。

用法示例：
    # 1. 传统用法：直接输入完整 Prompt
    python scripts/artgen/generate_asset.py "2d日式动漫，机甲半身特写" -o out.png

    # 2. 预设用法（自动注入赛璐璐画风锁 + 自动抠品红透明底 + 自动压缩）
    python scripts/artgen/generate_asset.py -p hero_mecha "特车二课英格拉姆，警车涂装" -o out.webp

    # 3. 预设演练（--dry-run）：查看装配后的提示词，不请求服务器
    python scripts/artgen/generate_asset.py -p hero_mecha "高达RX-78" --dry-run

    # 4. 查看所有预设
    python scripts/artgen/generate_asset.py --list-presets
"""

from __future__ import annotations

import argparse
import copy
import json
import random
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
TEMPLATE_PATH = Path(__file__).parent / "landing_t2i.api.json"

# ==============================================================================
# 内置 ComfyUI API 工作流模板（Turbo 8步出图 + Qwen CLIP 文本编码 + VAE 解码）
# 可选通过 --template 或本地 landing_t2i.api.json 覆盖
# ==============================================================================
DEFAULT_WORKFLOW_TEMPLATE: dict[str, Any] = {
    "599": {
        "inputs": {
            "add_noise": "enable",
            "noise_seed": ["851", 0],
            "steps": 8,
            "cfg": 1.0,
            "sampler_name": "er_sde",
            "scheduler": "simple",
            "start_at_step": 0,
            "end_at_step": 8,
            "return_with_leftover_noise": "enable",
            "model": ["859", 0],
            "positive": ["627", 0],
            "negative": ["763", 0],
            "latent_image": ["698", 0],
        },
        "class_type": "KSamplerAdvanced",
        "_meta": {"title": "1pass"},
    },
    "627": {
        "inputs": {
            "text": "2d日式动漫，1girl 25yo，3/4身立绘，红色军装白色短裙，在汇报工作，面朝右边，蓝色背景",
            "clip": ["860:755", 0],
        },
        "class_type": "CLIPTextEncode",
        "_meta": {"title": "CLIP文本编码"},
    },
    "698": {
        "inputs": {
            "width": 800,
            "height": 1200,
            "batch_size": 1,
        },
        "class_type": "EmptyLatentImage",
        "_meta": {"title": "Empty Latent Image (Base Dimensions) 初始大小"},
    },
    "763": {
        "inputs": {
            "conditioning": ["627", 0],
        },
        "class_type": "ConditioningZeroOut",
        "_meta": {"title": "条件零化"},
    },
    "829": {
        "inputs": {
            "samples": ["599", 0],
            "vae": ["860:858", 0],
        },
        "class_type": "VAEDecode",
        "_meta": {"title": "VAE解码"},
    },
    "851": {
        "inputs": {
            "seed": 638208442578987,
        },
        "class_type": "SeedNode",
        "_meta": {"title": "Seed 1ST"},
    },
    "859": {
        "inputs": {
            "lora_name": "krea2-Cc-天魔-身材.safetensors",
            "strength_model": 0.0,
            "model": ["860:761", 0],
        },
        "class_type": "LoraLoaderModelOnly",
        "_meta": {"title": "LoRA加载器（仅模型）"},
    },
    "871": {
        "inputs": {
            "anything": ["627", 0],
        },
        "class_type": "Anything Everywhere",
        "_meta": {"title": "text"},
    },
    "872": {
        "inputs": {
            "anything": ["860:761", 0],
            "anything11": ["860:755", 0],
            "anything12": ["860:858", 0],
        },
        "class_type": "Anything Everywhere",
        "_meta": {"title": "Anything Everywhere"},
    },
    "880": {
        "inputs": {
            "rgthree_comparer": {
                "images": [
                    {
                        "name": "A",
                        "selected": True,
                        "url": "/api/view?filename=rgthree.compare._temp_vsdli_00003_.png&type=temp&subfolder=&rand=0.6074284451251168",
                    }
                ]
            },
            "image_a": ["829", 0],
        },
        "class_type": "Image Comparer (rgthree)",
        "_meta": {"title": "Image Comparer (rgthree)"},
    },
    "881": {
        "inputs": {
            "filename_prefix": "ComfyUI",
            "filename_keys": "%F %H-%M-%S",
            "foldername_prefix": "",
            "foldername_keys": "ckpt_name",
            "delimiter": "-",
            "save_job_data": "disabled",
            "job_data_per_image": False,
            "job_custom_text": "",
            "save_metadata": True,
            "counter_digits": 4,
            "counter_position": "last",
            "one_counter_per_folder": True,
            "image_preview": False,
            "output_ext": ".webp",
            "quality": 75,
            "images": ["829", 0],
        },
        "class_type": "SaveImageExtended",
        "_meta": {"title": "💾 Save Image Extended"},
    },
    "860:755": {
        "inputs": {
            "clip_name": "qwen3vl_4b_fp8_scaled.safetensors",
            "type": "krea2",
            "device": "default",
        },
        "class_type": "CLIPLoader",
        "_meta": {"title": "加载CLIP"},
    },
    "860:858": {
        "inputs": {
            "vae_name": "qwen_image_vae.safetensors",
        },
        "class_type": "VAELoader",
        "_meta": {"title": "加载VAE"},
    },
    "860:761": {
        "inputs": {
            "unet_name": "museByStableYogi_v25INT8Turbo.safetensors",
            "weight_dtype": "default",
        },
        "class_type": "UNETLoader",
        "_meta": {"title": "UNet加载器"},
    },
}

# 抠图用背景色预设：追加到提示词末尾
BACKGROUND_PRESETS = {
    "none": "",
    "white": "纯白色背景，无渐变无阴影",
    "magenta": "纯品红色背景，背景无渐变无阴影，干净单一品红背景 (#FF00FF)",
}

# 轮询间隔与单次生成超时（秒）
POLL_INTERVAL = 2.0
DEFAULT_TIMEOUT = 600.0


# ==============================================================================
# 标准资产槽位预设（封装功能性 Prompt：画风锁、构图规范、背景模式）
# ==============================================================================

PRESETS: dict[str, dict[str, Any]] = {
    "hero_mecha": {
        "title": "英雄机甲半身立绘",
        "description": "落地页中央战术安全区 C 位全高机甲立柱，透明背景，2 阶硬边分色",
        "width": 800,
        "height": 1200,
        "background": "magenta",
        "has_transparency": True,
        "optimize_colors": 128,
        "optimize_quality": 80,
        "style": (
            "2d日式动漫，1990年代复古机甲赛璐璐动画，高达0083与机动警察美学，"
            "清晰黑墨线装甲刻线，凹槽分件，纯正2阶硬边色块阴影，高光切线，"
            "无3D感，无CGI，复古OVA质感"
        ),
        "framing": (
            "巨大真实系战斗机甲半身特写，正向雄伟站姿，居中对称构图，"
            "头顶天线与左右肩甲完整无裁切，四周预留安全边距，主体与背景分离"
        ),
        "negative": (
            "3d cgi render, photorealistic, blurry, messy sketch, crosshatching, "
            "paper grain, western comic, deformed hands, broken proportions"
        ),
    },
    "adjutant": {
        "title": "战术副官全息立绘",
        "description": "通讯台组件外全息立绘（48vh 等比直出）+ 视讯大头贴窗共用源图，朝向右侧屏幕",
        # 分辨率按显示端实际需求封顶：页面最大渲染 48vh@1080p = 346×518 CSS px，
        # ×2 retina = 692×1037 → 取 2:3、8 整除的贴合档 720×1080（较 800×1200 省 19% 像素，
        # turbo 出图同比例提速；1x 屏仍保有 2.08x 超采样余量）
        "width": 720,
        "height": 1080,
        "background": "magenta",
        "has_transparency": True,
        "optimize_colors": 128,
        "optimize_quality": 80,
        "style": (
            "2d日式动漫，1990年代复古动画角色赛璐璐原画，纯正手绘赛璐璐质感，"
            "清晰黑色描边，2阶阶梯硬阴影，色彩纯净清爽"
        ),
        # 构图硬约束（2026-09 定稿：半身腰部以上）。措辞纪律：
        # ① 禁用「3/4身」「立绘」等全身先验词（模板原始示例即「3/4身立绘」，是切到腰以下的主因）；
        # ② 下缘必须显式写死（腰际），否则胸口/腰部全凭模型掷骰子；
        # ③ 内容词里需要双手/道具的（如平板），与腰际裁切自洽，不再打架
        "framing": (
            "半身像，腰部以上构图，画面下缘裁切至腰际，"
            "身体微侧面朝右方，"
            "头顶与发饰完整不贴顶，单人"
        ),
        "negative": (
            "3d, cgi, photorealistic, gradient soft shading, rough sketch, "
            "extra limbs, bad anatomy, deformed eyes"
        ),
    },
    "hangar_bg": {
        "title": "格纳库全景背景底图",
        "description": "16:9 全景超广角战舰整备机库背景，科学家工程师忙碌装配，未完工巨型机甲施工架（禁止圆形圆盘）",
        "width": 1376,
        "height": 768,
        "background": "none",
        "has_transparency": False,
        "is_background": True,
        "optimize_colors": None,
        "optimize_quality": 52,
        "optimize_max_side": 960,
        "style": (
            "2d日式动漫，1990年代复古日式动画手绘背景美术，不透明水粉海报色绘制（poster color matte painting），"
            "小林七郎与美峰风格，赛璐璐质感，硬边阴影，干净深色描边，冷钢灰与工业蓝金属漆面，宇宙战舰内部巨型整备机库"
        ),
        "framing": (
            "超广角大远景（extreme wide-angle shot），宏伟开阔极高挑空的战舰内部整备大厅，强烈的一点透视纵深直达深处；"
            "远处多层高耸矩形立体检修脚手架与装配走道上，一台正在施工装配的未完工巨型机动战士固定在维修架中，"
            "骨架结构与半装配外甲外露，垂挂粗大线缆束与输能管道，多只工业液压机械臂正在焊接组装作业；"
            "多层走道与地面上，成群渺小的科学家与地勤工程师忙碌穿梭，身着研究白大褂与战术整备工装，手持数据终端，点状气焊火花飞溅；"
            "中央为平平整整的冲压防滑钢板地面与平直中轴弹射滑轨槽，黄色矩形几何停机标线，顶棚横跨黄色天车起重机桁架；"
            "平直硬朗工业构造，极具科研整备繁忙生活感，画面无任何文字无标识无涂字无水印"
        ),
        "negative": (
            "circular platform, round disc, turntable, saucer, circular pad, round ring, "
            "circular elevator, circular portal, round floor, teleporter, round stage, "
            "foreground blocking giant robot face, close-up mecha, 3d render, cgi, photorealism, "
            "blurry, crosshatching, comic book ink sketch, messy lineart, paper texture, "
            "grunge sepia, open space stars"
        ),
    },
    "unit_portrait": {
        "title": "机体档案胸像特写",
        "description": "右侧 UNIT FILE 档案卡正方形机体头部与胸甲特写",
        "width": 1024,
        "height": 1024,
        "background": "none",
        "has_transparency": False,
        "optimize_colors": 128,
        "optimize_quality": 80,
        "style": (
            "2d日式动漫赛璐璐原画，真实系机甲头部与胸像特写，"
            "装甲金属分色与精细刻线，硬边阴影，高对比工业反光"
        ),
        "framing": "正方形居中特写构图，深色工程维护暗部背景，展现机体面罩双眼与天线细节",
        "negative": "3d cgi render, photorealistic, blurry, crosshatching, deformed",
    },
    "pilot_avatar": {
        "title": "机师方形正统头像",
        "description": "顶栏与档案夹机师方形头像，身着飞行服",
        "width": 1024,
        "height": 1024,
        "background": "none",
        "has_transparency": False,
        "optimize_colors": 128,
        "optimize_quality": 80,
        "style": (
            "2d日式动漫角色赛璐璐原画，机甲王牌机师头部正方形头像，"
            "复古OVA硬朗画风，清晰黑色墨线，2阶纯色阴影"
        ),
        "framing": "正方形胸像构图，身着驾驶员特制抗压飞行服与高领护颈，神情坚定英勇，中性灰调战术背景",
        "negative": "3d cgi, photorealistic, gradient soft shade, deformed face, bad eyes",
    },
}


def assemble_prompt(
    preset: dict[str, Any], user_prompt: str, custom_bg: str | None = None
) -> tuple[str, str]:
    """拼装功能性提示词（画风+构图+背景）与业务内容词。"""
    bg_mode = custom_bg or preset.get("background", "none")
    bg_phrase = BACKGROUND_PRESETS.get(bg_mode, "")
    parts = [
        preset.get("style", "").strip("，,"),
        preset.get("framing", "").strip("，,"),
        user_prompt.strip("，,"),
    ]
    if bg_phrase:
        parts.append(bg_phrase.strip("，,"))
    positive = "，".join(p for p in parts if p)
    negative = preset.get("negative", "").strip()
    return positive, negative


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

    def submit(self, workflow: dict[str, object]) -> str:
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

    def wait(self, prompt_id: str, timeout: float = DEFAULT_TIMEOUT) -> dict[str, object]:
        """阻塞等待指定任务执行完成。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with urllib.request.urlopen(
                f"{self.base_url}/history/{prompt_id}", timeout=30
            ) as resp:
                history: dict[str, dict[str, object]] = json.load(resp)
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
) -> dict[str, dict[str, object]]:
    """基于模板生成待提交的工作流副本。"""
    workflow: dict[str, dict[str, object]] = copy.deepcopy(template)
    seed_node_id: str | None = None
    save_source: list[object] | None = None
    drop_ids: list[str] = []

    for node_id, node in workflow.items():
        inputs = node.get("inputs", {})
        class_type = str(node.get("class_type", ""))
        if class_type == "CLIPTextEncode" and "text" in inputs:
            inputs["text"] = prompt
        elif class_type == "EmptyLatentImage":
            inputs["width"] = width
            inputs["height"] = height
        elif class_type == "SeedNode":
            seed_node_id = node_id
            inputs["seed"] = seed
        elif class_type.startswith("SaveImage"):
            save_source = list(inputs.get("images", []))
            drop_ids.append(node_id)
        elif "Comparer" in class_type:
            drop_ids.append(node_id)

    if seed_node_id is None:
        for node in workflow.values():
            inputs = node.get("inputs", {})
            if "noise_seed" in inputs:
                inputs["noise_seed"] = seed

    for node_id in drop_ids:
        del workflow[node_id]

    if save_source is not None:
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
) -> list[Path]:
    """处理产物并在本地落盘。若命中预设则自动执行抠图/优化。"""
    from PIL import Image

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(BytesIO(raw_bytes))
    saved_files: list[Path] = []

    if preset and not skip_postprocess:
        import process_asset

        # 1. 自动透明抠图
        if preset.get("has_transparency"):
            try:
                key_mode = "auto" if preset.get("background") == "magenta" else preset.get("background", "auto")
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

        # 3. 自动调色板压缩优化
        try:
            scheme, payload = process_asset.optimize_image_bytes(
                image,
                colors=preset.get("optimize_colors"),
                quality=preset.get("optimize_quality", 80),
                max_side=preset.get("optimize_max_side"),
            )
            output_path.write_bytes(payload)
            saved_files.append(output_path)
            print(f"[{preset['title']}] 调色板优化完成 ({scheme}): {len(raw_bytes)/1024:.0f}KB -> {len(payload)/1024:.0f}KB")
            return saved_files
        except Exception as e:
            print(f"[警告] 调色板优化跳过，直接保存: {e}", file=sys.stderr)

    # 普通保存流程
    suffix = output_path.suffix.lower()
    if suffix == ".webp":
        image.save(output_path, "WEBP", quality=80)
    elif suffix in (".jpg", ".jpeg"):
        image.convert("RGB").save(output_path, "JPEG", quality=92)
    else:
        output_path.write_bytes(raw_bytes)
    saved_files.append(output_path)
    return saved_files


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
    skip_postprocess: bool = False,
    generate_preview: bool = False,
    template_path: Path | None = None,
) -> list[Path]:
    """核心生图 API。"""
    actual_seed = seed if seed is not None else random.randint(0, 2**48)
    preset = PRESETS.get(preset_name) if preset_name else None

    if preset:
        actual_width = width or preset["width"]
        actual_height = height or preset["height"]
        final_prompt, _ = assemble_prompt(preset, prompt, custom_bg=background)
    else:
        actual_width = width or 800
        actual_height = height or 1200
        bg_mode = background or "white"
        bg_suffix = BACKGROUND_PRESETS.get(bg_mode, "")
        final_prompt = f"{prompt}，{bg_suffix}" if bg_suffix else prompt

    # 工作流模板加载：优先使用外部指定/存在的模板文件，缺省直接回退使用内嵌字典
    if template_path and template_path.exists():
        template = json.loads(template_path.read_text(encoding="utf-8"))
    elif TEMPLATE_PATH.exists():
        try:
            template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            template = DEFAULT_WORKFLOW_TEMPLATE
    else:
        template = DEFAULT_WORKFLOW_TEMPLATE

    workflow = prepare_workflow(
        template,
        prompt=final_prompt,
        seed=actual_seed,
        width=actual_width,
        height=actual_height,
        filename_prefix=output_path.stem,
    )

    client = ComfyUIClient(server)
    tag = f"[{preset['title']}] " if preset else ""
    print(f"{tag}提交 ComfyUI 任务 · seed={actual_seed} · {actual_width}x{actual_height}...")
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
        output_path,
        preset=preset,
        skip_postprocess=skip_postprocess,
        generate_preview=generate_preview,
    )


# ==============================================================================
# CLI 入口
# ==============================================================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """命令行参数解析。"""
    parser = argparse.ArgumentParser(
        description="E.B.S.P 美术素材生成工具（支持槽位预设与自动后处理）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("prompt", nargs="?", default="", help="提示词（选用预设时为纯业务内容词）")
    parser.add_argument("-p", "--preset", choices=list(PRESETS.keys()), default=None, help="选用资产预设（自动注入画风锁、构图、背景与后处理）")
    parser.add_argument("-o", "--output", type=Path, default=None, help="输出文件路径（支持 .png / .jpg / .webp）")
    parser.add_argument("--server", default=DEFAULT_SERVER, help="ComfyUI 服务器地址")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，缺省时随机")
    parser.add_argument("--width", type=int, default=None, help="画布宽（缺省从预设读取或 800）")
    parser.add_argument("--height", type=int, default=None, help="画布高（缺省从预设读取或 1200）")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="单次生成超时（秒）")
    parser.add_argument("--background", choices=sorted(BACKGROUND_PRESETS), default=None, help="覆盖背景色预设")
    parser.add_argument("--dry-run", action="store_true", help="演练模式：仅打印装配后的提示词与规格，不调用服务器")
    parser.add_argument("--list-presets", action="store_true", help="列出所有可用预设与槽位规范")
    parser.add_argument("--skip-postprocess", action="store_true", help="跳过自动抠图与调色板优化")
    parser.add_argument("--preview", action="store_true", help="是否同时生成带 UI 遮挡框的 *_preview.webp 质检图（默认不生成）")
    parser.add_argument("--template", type=Path, default=None, help="覆盖 ComfyUI 工作流模板 JSON 路径（缺省优先使用内嵌工作流）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """脚本入口。"""
    args = parse_args(argv)

    if args.list_presets:
        print("\n" + "=" * 76)
        print("E.B.S.P 美术资产预设清单 (Asset Presets):")
        print("=" * 76)
        for key, p in PRESETS.items():
            trans = " [自动抠图]" if p.get("has_transparency") else ""
            bg_prev = " [遮挡质检]" if p.get("is_background") else ""
            print(f"• {key:<14} | {p['title']} ({p['width']}x{p['height']}){trans}{bg_prev}")
            print(f"  说明: {p['description']}")
            print()
        return 0

    if not args.prompt and not args.dry_run:
        print("错误: 请提供提示词 prompt。输入 -h 查看帮助。")
        return 1

    # 预设装配演示（Dry-Run）
    if args.dry_run:
        preset = PRESETS.get(args.preset) if args.preset else None
        if preset:
            pos, neg = assemble_prompt(preset, args.prompt, custom_bg=args.background)
            w = args.width or preset["width"]
            h = args.height or preset["height"]
            print("=" * 72)
            print(f"【DRY-RUN 预设演练】{preset['title']} ({args.preset}) · {w}x{h}")
            print("-" * 72)
            print(f"【装配后正向 Prompt】:\n  {pos}\n")
            print(f"【装配后负向 Prompt】:\n  {neg}\n")
            print("=" * 72)
        else:
            bg_mode = args.background or "white"
            bg_suffix = BACKGROUND_PRESETS.get(bg_mode, "")
            final = f"{args.prompt}，{bg_suffix}" if bg_suffix else args.prompt
            print(f"【DRY-RUN 无预设】Prompt:\n  {final}")
        return 0

    if args.output is None:
        stem = f"{args.preset or 'asset'}_{random.randint(1000, 9999)}"
        duo_assets = Path("../ebs-duo/assets")
        target_dir = duo_assets if duo_assets.exists() else Path("assets")
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
        skip_postprocess=args.skip_postprocess,
        generate_preview=args.preview,
        template_path=args.template,
    )
    for path in saved:
        print(f"产物已落盘：{path}（{path.stat().st_size / 1024:.0f} KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
