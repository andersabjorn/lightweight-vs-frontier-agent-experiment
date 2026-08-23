import json
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx
from ddgs import DDGS

from agent_experiment.config import FETCH_MAX_CHARS, SEARCH_MAX_RESULTS
from agent_experiment.metrics import MetricsLogger

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for information. Returns titles, URLs, and snippets. "
                "Use specific queries for best results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": (
                "Fetch and extract text content from a URL. "
                "Use after web_search to read full pages."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": (
                "Save a research note to working memory. "
                "Use to track findings before writing the final report."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "note": {
                        "type": "string",
                        "description": "Note content (include source URL if applicable)",
                    },
                },
                "required": ["note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_report",
            "description": (
                "Submit the final structured research report in markdown. "
                "Call this when the report is complete. This ends the agent run."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "report": {
                        "type": "string",
                        "description": "Full markdown report with sections and source URLs",
                    },
                },
                "required": ["report"],
            },
        },
    },
]


def _strip_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:FETCH_MAX_CHARS]


def web_search(query: str, max_results: int = SEARCH_MAX_RESULTS) -> str:
    max_results = min(max(max_results, 1), 10)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
    except Exception as exc:
        return json.dumps({"error": str(exc), "results": []})

    formatted = []
    for item in results:
        formatted.append(
            {
                "title": item.get("title", ""),
                "url": item.get("href", item.get("link", "")),
                "snippet": item.get("body", item.get("snippet", "")),
            }
        )
    return json.dumps({"query": query, "results": formatted}, ensure_ascii=False)


def fetch_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return json.dumps({"error": "Only http/https URLs supported", "url": url})

    try:
        with httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "AgentExperiment/1.0 (research bot)"},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "html" in content_type:
                text = _strip_html(response.text)
            else:
                text = response.text[:FETCH_MAX_CHARS]
            return json.dumps(
                {
                    "url": str(response.url),
                    "status": response.status_code,
                    "content": text,
                },
                ensure_ascii=False,
            )
    except Exception as exc:
        return json.dumps({"error": str(exc), "url": url})


class ToolExecutor:
    def __init__(self, logger: MetricsLogger) -> None:
        self.logger = logger
        self.report_submitted = False

    def execute(self, name: str, arguments: str | dict[str, Any]) -> str:
        if isinstance(arguments, str):
            try:
                args = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                args = {}
        else:
            args = arguments

        if name == "web_search":
            result = web_search(args.get("query", ""), args.get("max_results", SEARCH_MAX_RESULTS))
        elif name == "fetch_url":
            url = args.get("url", "")
            result = fetch_url(url)
            if url:
                self.logger.add_fetched_url(url)
        elif name == "save_note":
            note = args.get("note", "")
            self.logger.add_note(note)
            result = json.dumps({"status": "saved", "note_length": len(note)})
        elif name == "submit_report":
            report = args.get("report", "")
            self.logger.set_report(report)
            self.report_submitted = True
            result = json.dumps({"status": "report_submitted", "length": len(report)})
        else:
            result = json.dumps({"error": f"Unknown tool: {name}"})

        preview = result[:500] if isinstance(result, str) else str(result)[:500]
        self.logger.record_tool_call(name, args, preview)
        return result
