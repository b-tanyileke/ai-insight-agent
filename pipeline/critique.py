"""Critique drafted insights against their validated evidence.

The critic has one narrow job: determine whether an insight is specific,
actionable, and supported before the pipeline considers publishing it.
"""

from pipeline.llm_client import call_gemini_raw, parse_json_response


CRITIC_SYSTEM_INSTRUCTION = """You are a strict editor for a business AI
insight publication. Review one drafted insight against its verified claims and
source excerpts.

Approve only when the draft is supported by the evidence, names a concrete
business workflow or role, proposes a realistic action, and avoids promotional
or unsupported value claims. Choose revise when one focused rewrite can fix it.
Choose reject when the evidence is too weak or the development is not a useful
business insight.

Return ONLY a JSON object with exactly this schema:
{
  "decision": "approve" | "revise" | "reject",
  "scores": {
    "grounding": 1,
    "specificity": 1,
    "actionability": 1,
    "value_claim_safety": 1
  },
  "feedback": "one concise instruction for the writer or reason for rejection"
}

Scores are integers from 1 (poor) to 5 (strong). Do not introduce facts beyond
the supplied evidence."""

VALID_DECISIONS = {"approve", "revise", "reject"}
SCORE_NAMES = {"grounding", "specificity", "actionability", "value_claim_safety"}


def build_critic_prompt(insight, evidence):
    """Format only validated evidence and the draft for the critic model."""
    claims = "\n".join(
        f"- Claim: {claim['claim']}\n  Excerpt: {claim['excerpt']}"
        for claim in evidence["claims"]
    )
    draft = "\n".join(
        f"{field}: {insight.get(field, '')}"
        for field in (
            "what_it_is",
            "business_use_case",
            "estimated_value",
            "implementation",
            "reasoning",
        )
    )
    return f"Verified evidence:\n{claims}\n\nDraft insight:\n{draft}"


def validate_critique(result):
    """Return a safe critique record or None when the model breaks the contract."""
    if not isinstance(result, dict) or result.get("decision") not in VALID_DECISIONS:
        return None
    scores = result.get("scores")
    if not isinstance(scores, dict) or set(scores) != SCORE_NAMES:
        return None
    if any(not isinstance(score, int) or not 1 <= score <= 5 for score in scores.values()):
        return None
    feedback = result.get("feedback")
    if not isinstance(feedback, str) or not feedback.strip():
        return None
    return {"decision": result["decision"], "scores": scores, "feedback": feedback.strip()}


def critique_insight(insight, evidence):
    """Ask the critic to evaluate a draft and validate its structured response."""
    raw_response = call_gemini_raw(
        CRITIC_SYSTEM_INSTRUCTION,
        build_critic_prompt(insight, evidence),
        temperature=0.0,
    )
    return validate_critique(parse_json_response(raw_response))
