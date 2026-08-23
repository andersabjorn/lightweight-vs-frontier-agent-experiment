import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
RUNS_DIR = Path(__file__).resolve().parent.parent / "runs"

# Approximate pricing per 1M tokens (USD) for cost estimation when usage.cost is absent
MODEL_PRICING: dict[str, dict[str, float]] = {
    "qwen/qwen3-30b-a3b-instruct-2507": {"input": 0.048, "output": 0.193},
    "openai/gpt-oss-20b": {"input": 0.030, "output": 0.130},
    "anthropic/claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "anthropic/claude-sonnet-4.5": {"input": 3.0, "output": 15.0},
}

LIGHTWEIGHT_MODEL = "qwen/qwen3-30b-a3b-instruct-2507"
LIGHTWEIGHT_ALT_MODEL = "openai/gpt-oss-20b"
FRONTIER_MODEL = "anthropic/claude-sonnet-4"
JUDGE_MODEL = FRONTIER_MODEL

MAX_STEPS = 15
TEMPERATURE = 0.3
FETCH_MAX_CHARS = 8000
SEARCH_MAX_RESULTS = 5


@dataclass(frozen=True)
class ModelConfig:
    slug: str
    label: str
    role: str  # lightweight | frontier | judge


MODELS = {
    "lightweight": ModelConfig(LIGHTWEIGHT_MODEL, "qwen3-30b", "lightweight"),
    "lightweight_alt": ModelConfig(LIGHTWEIGHT_ALT_MODEL, "gpt-oss-20b", "lightweight"),
    "frontier": ModelConfig(FRONTIER_MODEL, "claude-sonnet-4", "frontier"),
}


def get_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return key


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        return 0.0
    return (tokens_in * pricing["input"] + tokens_out * pricing["output"]) / 1_000_000
