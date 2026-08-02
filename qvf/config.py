"""Runtime configuration for QVF experiments.

All settings are environment-variable driven so experiment scripts can sweep
them without code edits:

- QVF_ADAPTER_MODEL    model id for the Semantic Adapter   (default claude-opus-5)
- QVF_GENERATOR_MODEL  model id for answer generation      (default claude-opus-5)
- QVF_JUDGE_MODEL      model id for LLM-as-judge scoring   (default claude-opus-5)
- QVF_MOCK             "1" to run everything without API calls (plumbing tests)
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Pick up ANTHROPIC_API_KEY etc. from the project-local .env file.
load_dotenv()

DEFAULT_ADAPTER_MODEL = os.environ.get("QVF_ADAPTER_MODEL", "claude-opus-5")
DEFAULT_GENERATOR_MODEL = os.environ.get("QVF_GENERATOR_MODEL", "claude-opus-5")
DEFAULT_JUDGE_MODEL = os.environ.get("QVF_JUDGE_MODEL", "claude-opus-5")

# max_tokens caps thinking + visible output together on Claude Opus 5
# (thinking is on by default), so leave generous headroom everywhere.
ADAPTER_MAX_TOKENS = int(os.environ.get("QVF_ADAPTER_MAX_TOKENS", "16000"))
GENERATOR_MAX_TOKENS = int(os.environ.get("QVF_GENERATOR_MAX_TOKENS", "16000"))
JUDGE_MAX_TOKENS = int(os.environ.get("QVF_JUDGE_MAX_TOKENS", "16000"))


def mock_mode() -> bool:
    return os.environ.get("QVF_MOCK", "0") == "1"
