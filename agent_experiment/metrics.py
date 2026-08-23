import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_experiment.config import RUNS_DIR, estimate_cost


@dataclass
class MetricsLogger:
    model: str
    model_label: str
    task_id: str
    run_dir: Path
    started_at: float = field(default_factory=time.time)
    steps: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    total_cost_usd: float = 0.0
    completion_status: str = "running"
    report: str = ""
    notes: list[str] = field(default_factory=list)
    fetched_urls: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.trace_path = self.run_dir / "trace.jsonl"

    @classmethod
    def create(cls, model: str, model_label: str, task_id: str) -> "MetricsLogger":
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_label = re.sub(r"[^\w\-]", "_", model_label)
        run_dir = RUNS_DIR / f"{timestamp}_{safe_label}"
        return cls(model=model, model_label=model_label, task_id=task_id, run_dir=run_dir)

    def log_trace(self, event: str, data: dict[str, Any]) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **data,
        }
        with self.trace_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def record_llm_usage(self, usage: Any, model: str) -> None:
        if usage is None:
            return
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        self.tokens_in += prompt_tokens
        self.tokens_out += completion_tokens

        cost = None
        if hasattr(usage, "model_extra") and usage.model_extra:
            cost = usage.model_extra.get("cost")
        if cost is not None:
            self.total_cost_usd += float(cost)
        else:
            self.total_cost_usd += estimate_cost(model, prompt_tokens, completion_tokens)

    def record_step(self) -> None:
        self.steps += 1

    def record_tool_call(self, name: str, args: dict[str, Any], result_preview: str) -> None:
        self.tool_calls += 1
        self.log_trace(
            "tool_call",
            {"tool": name, "args": args, "result_preview": result_preview[:500]},
        )

    def add_fetched_url(self, url: str) -> None:
        self.fetched_urls.add(url)

    def add_note(self, note: str) -> None:
        self.notes.append(note)

    def set_report(self, report: str) -> None:
        self.report = report
        (self.run_dir / "report.md").write_text(report, encoding="utf-8")

    def finish(self, status: str) -> dict[str, Any]:
        self.completion_status = status
        wall_time = time.time() - self.started_at
        sources_cited = len(extract_urls(self.report))
        metrics = {
            "model": self.model,
            "model_label": self.model_label,
            "task_id": self.task_id,
            "run_dir": str(self.run_dir),
            "wall_time_sec": round(wall_time, 2),
            "steps": self.steps,
            "tool_calls": self.tool_calls,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "completion_status": self.completion_status,
            "sources_cited": sources_cited,
            "fetched_urls": len(self.fetched_urls),
            "notes_count": len(self.notes),
        }
        (self.run_dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if self.notes:
            (self.run_dir / "notes.md").write_text(
                "\n\n---\n\n".join(self.notes), encoding="utf-8"
            )
        self.log_trace("finish", metrics)
        return metrics

    def write_latest_symlink(self, role: str) -> None:
        latest = RUNS_DIR / f"latest_{role}"
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        latest.symlink_to(self.run_dir.name)


def extract_urls(text: str) -> set[str]:
    pattern = r"https?://[^\s\)\]\"'<>]+"
    return set(re.findall(pattern, text))


def count_verifiable_claims(report: str) -> int:
    """Rough count of factual-looking claims (numbers, prices, model names)."""
    patterns = [
        r"\$[\d.]+\s*/?\s*M",
        r"\d+\s*B\b",
        r"\d+\s*GB",
        r"qwen|llama|mistral|claude|gpt",
    ]
    count = 0
    for pat in patterns:
        count += len(re.findall(pat, report, re.IGNORECASE))
    return count
