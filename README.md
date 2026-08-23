# Lightweight vs Frontier Agent Experiment

Benchmark comparing lightweight (20–30B) and frontier LLMs on the same research agent task, routed through **Composio → OpenRouter**.

## What this repo contains

- **Experiment harness** — minimal Python agent loop with tool calling (`web_search`, `fetch_url`, `save_note`, `submit_report`)
- **Full experiment report** — all runs, metrics, fact-check, and conclusions: [`runs/FULL_REPORT.md`](runs/FULL_REPORT.md)
- **Individual model reports** — Qwen3-30B, Claude Sonnet 4 (10-step), manual baseline

## Key result (headline)

| Model | Steps | Status | Cost | Delivered report? |
|-------|-------|--------|------|-------------------|
| Qwen3-30B | 5 | success | **$0.0014** | Yes |
| Claude Sonnet 4 | 5 | max_steps | $0.029 | No |
| gpt-oss-20b | 5 | max_steps | $0.0002 | No |
| Claude Sonnet 4 | 10 | success | $0.115 | Yes (no URLs cited) |

**Takeaway:** For structured research with tools, a strong 30B model often finishes faster and cheaper. Frontier models need more step budget to complete agent loops.

## Quick start (local, optional)

Requires `OPENROUTER_API_KEY` in `.env` (or run via Composio MCP as we did).

```bash
cp .env.example .env
pip install -r requirements.txt
python verify_setup.py
python run_experiment.py
python evaluate.py runs/latest_lightweight runs/latest_frontier
```

## Reports

| File | Description |
|------|-------------|
| [`runs/FULL_REPORT.md`](runs/FULL_REPORT.md) | Complete shareable report (start here) |
| [`runs/INDEX.md`](runs/INDEX.md) | Index of all artifacts |
| [`runs/qwen3-30b-experiment-report.md`](runs/qwen3-30b-experiment-report.md) | Qwen3-30B autonomous report |
| [`runs/claude-sonnet-4-10step-report.md`](runs/claude-sonnet-4-10step-report.md) | Claude Sonnet 4 report (10 steps) |
| [`runs/manual-research-report.md`](runs/manual-research-report.md) | Manual Cursor-agent baseline |

## License

MIT
