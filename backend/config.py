"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv
from .config_loader import get_council_models, get_chairman_model, load_config

load_dotenv()

# Dynamic model loading from YAML config
COUNCIL_MODELS = get_council_models()
CHAIRMAN_MODEL = get_chairman_model()
FORMATTER_MODEL = CHAIRMAN_MODEL  # Chairman also formats

# Default data directory (overridden per-council in storage.py)
DATA_DIR = "data/conversations"


def reload_runtime_config():
    """Reload runtime config variables after YAML changes."""
    global COUNCIL_MODELS, CHAIRMAN_MODEL, FORMATTER_MODEL
    COUNCIL_MODELS = get_council_models()
    CHAIRMAN_MODEL = get_chairman_model()
    FORMATTER_MODEL = CHAIRMAN_MODEL
