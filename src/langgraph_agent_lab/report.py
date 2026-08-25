"""Report generation helper.

TODO(student): implement report rendering using MetricsReport data
and the template in reports/lab_report_template.md.
"""

from __future__ import annotations

from pathlib import Path

from .metrics import MetricsReport


def render_report(metrics: MetricsReport) -> str:
    """Render a complete lab report from metrics data."""
    scenario_rows = []
    for item in metrics.scenario_metrics:
        status_str = "✅ Pass" if item.success else "❌ Fail"
        scenario_rows.append(
            f"| `{item.scenario_id}` | `{item.expected_route}` | `{item.actual_route}` | "
            f"{status_str} | {item.retry_count} | {item.interrupt_count} |"
        )
    scenario_table = "\n".join(scenario_rows)

    report_lines = [
        "# Day 08 Lab Report — LangGraph Agentic Orchestration",
        "",
        "## 1. Team / student",
        "",
        "- **Student Name**: Nguyen Xuan Duc",
        "- **Student ID**: 2A202601112",
        "- **Track**: Phase 2 - Track 3 - Day 08",
        "- **Date**: 2026-08-25",
        "",
        "## 2. Architecture",
        "",
        "The orchestration graph implements an adaptive, stateful customer support workflow:",
        "",
        "```text",
        "START ──► intake ──► classify ──► [route_after_classify]",
        "                       │",
        "                       ├── simple       ──► answer ──► finalize ──► END",
        "                       │",
        "                       ├── tool         ──► tool ──► evaluate ──► [route_after_evaluate]",
        "                       │                               │            "
        "├── success     ──► answer ──► finalize ──► END",
        "                       │                               │            "
        "└── needs_retry ──► retry ──► [route_after_retry]",
        "                       │                                                           "
        "       │          ├── attempt < max  ──► tool",
        "                       │                                                           "
        "       │          └── attempt >= max ──► dead_letter ──► finalize ──► END",
        "                       │",
        "                       ├── missing_info ──► clarify ──► finalize ──► END",
        "                       │",
        "                       ├── risky        ──► risky_action ──► approval ──► "
        "[route_after_approval]",
        "                       │                                         │            "
        "├── approved ──► tool ──► evaluate ──► ...",
        "                       │                                         │            "
        "└── rejected ──► clarify ──► finalize ──► END",
        "                       │",
        "                       └── error        ──► retry ──► [route_after_retry] ──► ...",
        "```",
        "",
        "### Registered Nodes (11 nodes):",
        "1. `intake`: Normalizes incoming user query.",
        "2. `classify`: Uses LLM with structured output (`ClassificationResult`).",
        "3. `tool`: Executes tool lookup with simulated error handling for retry loops.",
        "4. `evaluate`: Evaluates tool execution results (retry loop gate).",
        "5. `answer`: Uses LLM to synthesize final response grounded in tool context and query.",
        "6. `clarify`: Formulates targeted clarification requests for ambiguous queries.",
        "7. `risky_action`: Prepares sensitive operations for human review.",
        "8. `approval`: Handles human-in-the-loop (HITL) approval (mock or `interrupt()`).",
        "9. `retry`: Increments attempt counter and logs transient failure errors.",
        "10. `dead_letter`: Handles terminal escalation when retry attempts are exhausted.",
        "11. `finalize`: Emits final audit log event before terminating at `END`.",
        "",
        "## 3. State schema",
        "",
        "| Field | Reducer | Why |",
        "|---|---|---|",
        "| `thread_id` | Overwrite | Unique identifier per session/thread |",
        "| `scenario_id` | Overwrite | Scenario identifier tracking |",
        "| `query` | Overwrite | Original customer inquiry string |",
        "| `route` | Overwrite | Current classified route (`simple`, `tool`, `risky`, etc.) |",
        "| `risk_level` | Overwrite | Safety indicator (`high` or `low`) |",
        "| `attempt` | Overwrite | Current retry attempt counter |",
        "| `max_attempts` | Overwrite | Maximum retry limit before escalation |",
        "| `final_answer` | Overwrite | Final synthesized response for customer |",
        "| `evaluation_result` | Overwrite | Tool evaluation status (`success` or `needs_retry`) |",
        "| `pending_question` | Overwrite | Clarification question when input is ambiguous |",
        "| `proposed_action` | Overwrite | Description of high-risk operation |",
        "| `approval` | Overwrite | HITL approval decision object |",
        "| `messages` | Append | Audit history of message exchanges |",
        "| `tool_results` | Append | Historical record of tool execution results |",
        "| `errors` | Append | Accumulated errors across retries |",
        "| `events` | Append | Complete node traversal audit log |",
        "",
        "## 4. Scenario results",
        "",
        "### Metrics Summary:",
        f"- **Total Scenarios**: {metrics.total_scenarios}",
        f"- **Success Rate**: {metrics.success_rate:.2%}",
        f"- **Average Nodes Visited**: {metrics.avg_nodes_visited:.2f}",
        f"- **Total Retries**: {metrics.total_retries}",
        f"- **Total Interrupts/Approvals**: {metrics.total_interrupts}",
        "",
        "### Detailed Scenario Results:",
        "",
        "| Scenario | Expected route | Actual route | Success | Retries | Interrupts |",
        "|---|---|---|---:|---:|---:|",
        scenario_table,
        "",
        "## 5. Failure analysis",
        "",
        "1. **Transient Tool Failure & Bounded Retry**:",
        "   - *Risk*: API timeouts can cause infinite loops without retry bounds.",
        "   - *Mitigation*: `route_after_retry` bounds attempts before dead letter.",
        "2. **Unapproved High-Risk Operations**:",
        "   - *Risk*: Destructive actions executed without human oversight.",
        "   - *Mitigation*: `risky` queries route to `approval` before tool execution.",
        "",
        "## 6. Persistence / recovery evidence",
        "",
        "- The system supports in-memory (`MemorySaver`) and SQLite (`SqliteSaver`) checkpointers.",
        "- Each scenario run specifies a unique `thread_id` via run_config.",
        "- SQLite checkpoints are stored with WAL mode (`PRAGMA journal_mode=WAL;`).",
        "",
        "## 7. Extension work",
        "",
        "- **SQLite Persistent Checkpointer**: Implemented in `persistence.py` with WAL mode.",
        "- **LLM Structured Output**: `ClassificationResult` schema with structured output.",
        "- **Human-in-the-Loop (HITL) Interrupt**: Support for `LANGGRAPH_INTERRUPT=true`.",
        "",
        "## 8. Improvement plan",
        "",
        "1. **Streaming Telemetry**: Integrate OpenTelemetry or LangSmith for latency tracking.",
        "2. **Parallel Tool Execution**: Use `Send()` API to execute tool checks concurrently.",
        "",
    ]
    return "\n".join(report_lines)


def write_report(metrics: MetricsReport, output_path: str | Path) -> None:
    """Write the rendered report to a file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(metrics), encoding="utf-8")
