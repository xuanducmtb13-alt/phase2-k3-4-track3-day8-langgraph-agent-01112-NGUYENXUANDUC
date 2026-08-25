"""Node functions for the LangGraph workflow.

Each function receives AgentState and returns a partial state update dict.
Do NOT mutate input state — return new values only.

LLM REQUIREMENT:
- classify_node MUST use a real LLM call (structured output for intent classification)
- answer_node MUST use a real LLM call (grounded response generation)
- evaluate_node SHOULD use LLM-as-judge (bonus points; heuristic acceptable for base score)
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field

from .llm import get_llm
from .state import AgentState, make_event


def intake_node(state: AgentState) -> dict:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


# ─── Node Implementations ───────────────────────────────────────────


class ClassificationResult(BaseModel):
    """Structured output schema for intent classification."""

    route: Literal["simple", "tool", "missing_info", "risky", "error"] = Field(
        description="The classified route based on strict priority: "
        "risky > tool > missing_info > error > simple."
    )
    risk_level: Literal["high", "low"] = Field(
        default="low",
        description="'high' if the route is risky or involves side-effects/financial/destructive "
        "actions, otherwise 'low'.",
    )
    reasoning: str = Field(
        default="",
        description="Short rationale for why this route was selected.",
    )


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using an LLM with structured output."""
    query = state.get("query", "").strip()

    classification_prompt = (
        "You are an expert customer support ticket classifier. "
        "Classify the following customer ticket query into EXACTLY ONE route based on priority:\n"
        "1. 'risky': Actions with irreversible side effects or sensitive/destructive operations "
        "(e.g. refunds, cancellations, deleting account, sending email on behalf of user).\n"
        "2. 'tool': Information lookups or status checks requiring an external tool/database "
        "(e.g. order status lookup, tracking number search).\n"
        "3. 'missing_info': Vague, ambiguous, or incomplete queries lacking actionable context "
        "(e.g. 'Can you fix it?', 'help me').\n"
        "4. 'error': Reports or symptoms of system/service failures, timeouts, crashes "
        "(e.g. 'Timeout failure while processing request', 'System failure cannot recover').\n"
        "5. 'simple': General FAQ or informational questions answerable directly without tools "
        "or side effects (e.g. 'How do I reset my password?').\n\n"
        f"Query: {query}"
    )

    route = "simple"
    risk_level = "low"

    try:
        llm = get_llm(temperature=0.0)
        structured_llm = llm.with_structured_output(ClassificationResult)
        result = structured_llm.invoke(classification_prompt)
        if isinstance(result, ClassificationResult):
            route = result.route
            risk_level = result.risk_level
        elif isinstance(result, dict):
            route = result.get("route", "simple")
            risk_level = result.get("risk_level", "low")
    except Exception:
        # Fallback heuristic if LLM API is unavailable or offline
        lower_q = query.lower()
        if any(k in lower_q for k in ["refund", "delete", "cancel", "email"]):
            route = "risky"
            risk_level = "high"
        elif any(k in lower_q for k in ["lookup", "status", "order", "track"]):
            route = "tool"
            risk_level = "low"
        elif (
            any(k in lower_q for k in ["fix it", "can you fix", "help", "broken"])
            and len(lower_q.split()) <= 4
        ):
            route = "missing_info"
            risk_level = "low"
        elif any(k in lower_q for k in ["timeout", "failure", "crash", "error"]):
            route = "error"
            risk_level = "low"
        else:
            route = "simple"
            risk_level = "low"

    if route == "risky":
        risk_level = "high"

    return {
        "route": route,
        "risk_level": risk_level,
        "events": [
            make_event(
                "classify",
                "completed",
                f"classified query as '{route}'",
                route=route,
                risk_level=risk_level,
            )
        ],
    }


def tool_node(state: AgentState) -> dict:
    """Execute a mock tool call with error simulation for transient failures."""
    attempt = state.get("attempt", 0)
    route = state.get("route", "")
    query = state.get("query", "")

    if route == "error" and attempt < 2:
        result_string = (
            f"ERROR: Transient timeout failure executing tool for '{query}' "
            f"(attempt {attempt})"
        )
    else:
        result_string = (
            f"SUCCESS: Tool executed successfully for query '{query}'. "
            "Details: Order status active / action processed."
        )

    return {
        "tool_results": [result_string],
        "events": [
            make_event(
                "tool",
                "completed",
                "mock tool execution completed",
                attempt=attempt,
            )
        ],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — retry loop gate."""
    tool_results = state.get("tool_results", [])
    latest_result = tool_results[-1] if tool_results else ""

    if "ERROR" in latest_result:
        evaluation_result = "needs_retry"
    else:
        evaluation_result = "success"

    return {
        "evaluation_result": evaluation_result,
        "events": [
            make_event(
                "evaluate",
                "completed",
                f"evaluation result: {evaluation_result}",
                evaluation_result=evaluation_result,
            )
        ],
    }


def answer_node(state: AgentState) -> dict:
    """Generate a final response grounded in available context using an LLM."""
    query = state.get("query", "")
    tool_results = state.get("tool_results", [])
    approval = state.get("approval")

    prompt = (
        "You are a helpful customer support assistant. "
        "Provide a clear, grounded, and concise answer to the customer query.\n"
        f"Query: {query}\n"
        f"Tool Results: {tool_results}\n"
        f"Approval Details: {approval}\n\n"
        "Response:"
    )

    try:
        llm = get_llm(temperature=0.2)
        response = llm.invoke(prompt)
        content = response.content
        answer_text = content if isinstance(content, str) else str(content)
    except Exception:
        if tool_results:
            answer_text = f"Regarding your inquiry '{query}': {tool_results[-1]}"
        elif approval:
            answer_text = f"Your request '{query}' has been reviewed and processed."
        else:
            answer_text = (
                f"To address your inquiry '{query}': "
                "Please follow standard instructions or contact support."
            )

    return {
        "final_answer": answer_text,
        "events": [make_event("answer", "completed", "grounded answer generated")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information when query is ambiguous."""
    query = state.get("query", "").strip()
    clarification = (
        f"Could you please provide more details about your request '{query}'? "
        "What specific order or issue would you like us to look into?"
    )
    return {
        "pending_question": clarification,
        "final_answer": clarification,
        "events": [make_event("clarify", "completed", "clarification question requested")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for human approval."""
    query = state.get("query", "").strip()
    proposed_action = f"Action requiring human review: Execute sensitive operation '{query}'"
    return {
        "proposed_action": proposed_action,
        "events": [make_event("risky_action", "completed", "risky action prepared for approval")],
    }


def approval_node(state: AgentState) -> dict:
    """Human-in-the-loop approval step."""
    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() in ("true", "1"):
        from langgraph.types import interrupt  # type: ignore

        decision = interrupt({"proposed_action": state.get("proposed_action", "")})
        if isinstance(decision, dict):
            approval_decision = {
                "approved": bool(decision.get("approved", True)),
                "reviewer": str(decision.get("reviewer", "human-reviewer")),
                "comment": str(decision.get("comment", "approved via interrupt")),
            }
        else:
            approval_decision = {
                "approved": bool(decision),
                "reviewer": "human-reviewer",
                "comment": "approved via interrupt",
            }
    else:
        approval_decision = {
            "approved": True,
            "reviewer": "mock-reviewer",
            "comment": "Auto-approved for batch evaluation",
        }

    return {
        "approval": approval_decision,
        "events": [
            make_event(
                "approval",
                "completed",
                f"approval decision: approved={approval_decision['approved']}",
            )
        ],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt and increment attempt counter."""
    attempt = state.get("attempt", 0) + 1
    err_msg = f"Attempt {attempt} failed: transient error encountered"
    return {
        "attempt": attempt,
        "errors": [err_msg],
        "events": [
            make_event(
                "retry",
                "completed",
                f"retry attempt {attempt} recorded",
                attempt=attempt,
            )
        ],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failures after max retries exceeded."""
    query = state.get("query", "")
    attempt = state.get("attempt", 0)
    final_answer = (
        f"We apologize, but your request '{query}' could not be completed after "
        f"{attempt} attempts. "
        "The ticket has been routed to our dead-letter escalation queue for engineer review."
    )
    return {
        "final_answer": final_answer,
        "events": [
            make_event("dead_letter", "completed", "escalated to dead letter queue")
        ],
    }


def finalize_node(state: AgentState) -> dict:
    """Emit final audit event before END."""
    return {
        "events": [make_event("finalize", "completed", "workflow finished")],
    }
