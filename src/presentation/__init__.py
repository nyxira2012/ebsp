"""
演出系统 (CPS - Combat Presentation System) v5.0

四层导演金字塔架构：
- L1: ODR Router (Outcome-First Routing) - 结局前置路由
- L2: Dual Bidder - 双轨独立竞标
- L3: Assembler - 原子化文本拼装
- L4: AV Dispatcher - 视听调度
"""

from .constants import VisualIntent, PresentationTag, TemplateTier, Channel
from .models import RawAttackEvent, PresentationAttackEvent, PresentationRoundEvent
from .intent_extractor import IntentExtractor
from .template import (
    ActionBone, ReactionBone,
    # PresentationTemplate 仅保留用于 T0 脚本模板
    PresentationTemplate, TemplateConditions, TemplateContent, TemplateVisuals,
)
from .registry import TemplateRegistry
from .mapper import EventMapper
from .renderer import TextRenderer, JSONRenderer

# v5.0 四层架构组件
from .router import OutcomeRouter
from .bidder import DualBidder
from .assembler import TextAssembler
from .av_dispatcher import AVDispatcher
