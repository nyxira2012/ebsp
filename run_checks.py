from tests.presentation.utils import display_event_table
from src.presentation.mapper import EventMapper
from src.presentation.registry import TemplateRegistry
from src.presentation.assembler import TextAssembler
from src.presentation.router import OutcomeRouter
from src.presentation.loader import TemplateLoader
from src.presentation.av_dispatcher import AVDispatcher
from src.presentation.event_builder import AttackEventBuilder

import json

# Let us check if there are test files we can run to verify the overall pipeline functionality
