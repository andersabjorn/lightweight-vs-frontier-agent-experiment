#!/usr/bin/env python3
"""
Run the agent experiment inside Composio Remote Workbench.

Uses proxy_execute for OpenRouter chat completions with tool calling.
Execute via Composio MCP COMPOSIO_REMOTE_WORKBENCH, or paste into workbench.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- Config (mirrors agent_experiment/config.py) ---
LIGHTWEIGHT_MODEL = "qwen/qwen3-30b-a3b-instruct-2507"
FRONTIER_MODEL = "anthropic/claude-sonnet-4"
MAX_STEPS = 15
TEMPERATURE = 0.3
FETCH_MAX_CHARS = 8000
SEARCH_MAX_RESULTS = 5
OUTPUT_DIR = Path("/mnt/files/agent_runs")

TASK_PROMPT = """Kartlägg lightweight agent-stacks 2026. Jämför minst 4 ramverk
(LangGraph, smolagents, OpenAI Agents SDK, och minst ett till), modellstorlekar
(7B–30B), och inference-leverantörer (OpenRouter, Together, Groq, lokal/Ollama).

Leverera en strukturerad rapport med:
1. Översikt av ramverk och deras styrkor/svagheter för lightweight agents
2. Jämförelse av modellstorlekar (7B, 14B, 20B, 30B) för agent-uppgifter
3. Kostnadsestimat per typisk research-uppgift (tokens + USD)
4. Konkret rekommendation: när räcker 20–30B vs när behövs frontier-modell?
5. Källhänvisningar (URL:er) för alla fakta du citerar

Använd verktygen för att söka och hämta information. Spara viktiga fynd med
save_note under arbetet. Avsluta med submit_report när rapporten är klar."""

SYSTEM_PROMPT = """You are a research agent. Complete the research task using tools.
1. web_search for sources 2. fetch_url for details 3. save_note for findings
4. submit_report with final markdown report. Always cite URLs. Be factual."""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web. Returns titles, URLs, snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch text content from a URL.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": "Save a research note.",
            "parameters": {
                "type": "object",
                "properties": {"note": {"type": "string"}},
                "required": ["note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_report",
            "description": "Submit final markdown report. Ends the run.",
            "parameters": {
                "type": "object",
                "properties": {"report": {"type": "string"}},
                "required": ["report"],
            },
        },
    },
]


def web_search_local(query: str, max_results: int = SEARCH_MAX_RESULTS) -> str:
    results_text, err = web_search(query)
    if err:
        return json.dumps({"error": err, "results": []})
    return json.dumps({"query": query, "results_text": results_text[:6000]})


def fetch_url_local(url: str) -> str:
    import httpx
    from html import unescape

    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            r = client.get(url, headers={"User-Agent": "AgentExperiment/1.0"})
            r.raise_for_status()
            text = re.sub(r"<[^>]+>", " ", r.text)
            text = unescape(re.sub(r"\s+", " ", text)).strip()[:FETCH_MAX_CHARS]
            return json.dumps({"url": str(r.url), "content": text})
    except Exception as exc:
        return json.dumps({"error": str(exc), "url": url})


def run_agent_composio(model: str, model_label: str, role: str) -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_DIR / f"{ts}_{model_label}"
    run_dir.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []
    report = ""
    report_submitted = False
    fetched_urls: set[str] = set()
    trace: list[dict] = []
    steps = 0
    tool_calls = 0
    tokens_in = 0
    tokens_out = 0
    total_cost = 0.0
    started = time.time()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": TASK_PROMPT},
    ]

    status = "max_steps"

    for step in range(MAX_STEPS):
        steps += 1
        body = {
            "model": model,
            "messages": messages,
            "tools": TOOL_SCHEMAS,
            "tool_choice": "auto",
            "temperature": TEMPERATURE,
            "max_tokens": 4096,
        }
        data, err = proxy_execute("POST", "/chat/completions", "openrouter", body=body)
        if err:
            status = "error"
            trace.append({"event": "error", "message": err})
            break

        usage = data.get("usage") or {}
        tokens_in += usage.get("prompt_tokens", 0)
        tokens_out += usage.get("completion_tokens", 0)
        total_cost += float(usage.get("cost") or 0)

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        finish_reason = choice.get("finish_reason")
        trace.append({"event": "llm_response", "step": step + 1, "finish_reason": finish_reason})

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.get("content")}
        if msg.get("tool_calls"):
            assistant_msg["tool_calls"] = msg["tool_calls"]
        messages.append(assistant_msg)

        if not msg.get("tool_calls"):
            if report_submitted:
                status = "success"
                break
            messages.append({
                "role": "user",
                "content": "Continue research or call submit_report with your final markdown report.",
            })
            continue

        for tc in msg["tool_calls"]:
            tool_calls += 1
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            if name == "web_search":
                result = web_search_local(args.get("query", ""), args.get("max_results", 5))
            elif name == "fetch_url":
                url = args.get("url", "")
                result = fetch_url_local(url)
                if url:
                    fetched_urls.add(url)
            elif name == "save_note":
                notes.append(args.get("note", ""))
                result = json.dumps({"status": "saved"})
            elif name == "submit_report":
                report = args.get("report", "")
                report_submitted = True
                result = json.dumps({"status": "report_submitted"})
            else:
                result = json.dumps({"error": f"Unknown tool: {name}"})

            trace.append({"event": "tool_call", "tool": name, "preview": result[:300]})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": result,
            })

            if report_submitted:
                status = "success"
                break

        if report_submitted:
            break

    wall_time = time.time() - started
    sources_cited = len(set(re.findall(r"https?://[^\s\)\]\"'<>]+", report)))

    metrics = {
        "model": model,
        "model_label": model_label,
        "task_id": "agent_landscape",
        "wall_time_sec": round(wall_time, 2),
        "steps": steps,
        "tool_calls": tool_calls,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "total_cost_usd": round(total_cost, 6),
        "completion_status": status,
        "sources_cited": sources_cited,
        "fetched_urls": len(fetched_urls),
        "notes_count": len(notes),
        "backend": "composio",
    }

    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (run_dir / "report.md").write_text(report or "(no report submitted)", encoding="utf-8")
    (run_dir / "trace.jsonl").write_text(
        "\n".join(json.dumps(t) for t in trace), encoding="utf-8"
    )
    if notes:
        (run_dir / "notes.md").write_text("\n\n---\n\n".join(notes), encoding="utf-8")

    print(f"Run complete: {model_label} -> {status}")
    print(json.dumps(metrics, indent=2))
    return {"run_dir": str(run_dir), "metrics": metrics, "role": role}


# Execute when run in Composio workbench
results = []
for model, label, role in [
    (LIGHTWEIGHT_MODEL, "qwen3-30b", "lightweight"),
    (FRONTIER_MODEL, "claude-sonnet-4", "frontier"),
]:
    results.append(run_agent_composio(model, label, role))

comparison = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "runs": results,
}
(OUTPUT_DIR / "comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
print("ALL DONE")
print(json.dumps(comparison, indent=2))
