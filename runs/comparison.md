# Lightweight vs Frontier — Composio Test Run (Round 1)

Generated: 2026-08-23 via Composio → OpenRouter (`proxy_execute`)

**Setup:** 5 max steps, same prompt, same tools (web_search, fetch_url, save_note, submit_report)

## Metrics

| Model | Status | Steps | Tool calls | Tokens (in/out) | Cost (USD) | Time (s) | Sources |
|-------|--------|-------|------------|-----------------|------------|----------|---------|
| Qwen3-30B (lightweight) | **success** | 5 | 9 | 14,170 / 1,588 | **$0.0014** | 32.6 | 5 |
| Claude Sonnet 4 (frontier) | max_steps | 5 | 5 | 7,835 / 397 | **$0.029** | 24.4 | 0 |

## Cost efficiency

- Frontier cost **21.8×** lightweight ($0.029 vs $0.0014)
- Round 1 experiment cost: **~$0.031**

## Key insight

**Lightweight won decisively.** Qwen3-30B completed with a cited report at ~1/20th the cost. Claude Sonnet 4 used 5 steps on web_search only and never called `submit_report`.

## Judge scores (Qwen report)

| Dimension | Score (1–5) |
|-----------|-------------|
| Coverage | 4 |
| Facts | 4 |
| Sources | 3 |
| Recommendation | 5 |
| Limitations | 3 |

Frontier: no report submitted.

See [FULL_REPORT.md](./FULL_REPORT.md) for all runs including 10-step Claude and gpt-oss-20b baseline.
