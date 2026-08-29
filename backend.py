"""
backend.py — Procrastination Autopsy
LangGraph differential-diagnosis graph with 3 nodes.

Node flow:
  START → first_question → (waits for user answer) → second_question → (waits for user answer) → diagnose → END

Because LangGraph interrupts are complex to wire to HTTP, we use a Stateless design:
each API call re-runs the relevant node with the accumulated context passed in the request.
This is cleaner for a hackathon demo.
"""

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from dotenv import load_dotenv
import os, json

load_dotenv()

# ------------------------------------------------------------------
# LLM  (Groq — ultra-fast, perfect for live demo)
# ------------------------------------------------------------------
def _make_llm():
    api_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEY_2")
    if not api_key:
        raise RuntimeError("No GROQ_API_KEY found in environment.")
    return ChatGroq(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        api_key=api_key,
        temperature=0.4,
    )

llm = _make_llm()

# ------------------------------------------------------------------
# Taxonomy  (the six root causes — this is the model's reference)
# ------------------------------------------------------------------
TAXONOMY = """
01. IDENTITY_THREAT   — Failing feels like evidence about who you are. Avoidance protects self-image.
02. GENUINE_AMBIGUITY — You truly don't know the literal first physical action. No visible entry point.
03. ENERGY_MISMATCH   — The cognitive mode the task needs doesn't match your current state.
04. LOW_STAKES        — No real urgency or close consequence. No pull toward it.
05. VALUES_CONFLICT   — A quiet belief that this task doesn't actually matter to you.
06. SCOPE_OVERWHELM   — The task is too large to hold as one unit; starting triggers overload.
"""

# ------------------------------------------------------------------
# Node 1 — Generate the first diagnostic question
# ------------------------------------------------------------------
FIRST_Q_SYSTEM = f"""You are a clinical psychologist specialising in procrastination.
Your job is differential diagnosis, not advice.

The six possible root causes are:
{TAXONOMY}

The user has described a task they are avoiding. Your job at this stage is:
1. Identify the 2-3 most plausible causes from the taxonomy.
2. Write ONE sharp, clinically precise question that best separates those top causes.
   - Do NOT ask a yes/no question — ask them to pick the most accurate description.
   - Do NOT offer generic advice.
   - Keep the question to 1-2 sentences.
3. Provide 3-4 answer options (short phrases, 5-12 words each) that map to specific causes.

Respond with ONLY valid JSON in this exact shape (no markdown, no extra text):
{{
  "question": "...",
  "options": [
    {{"text": "...", "cause_key": "IDENTITY_THREAT"}},
    {{"text": "...", "cause_key": "GENUINE_AMBIGUITY"}},
    {{"text": "...", "cause_key": "LOW_STAKES"}},
    {{"text": "...", "cause_key": "SCOPE_OVERWHELM"}}
  ],
  "top_candidates": ["IDENTITY_THREAT", "GENUINE_AMBIGUITY", "LOW_STAKES", "SCOPE_OVERWHELM"]
}}
Use only cause_keys from: IDENTITY_THREAT, GENUINE_AMBIGUITY, ENERGY_MISMATCH, LOW_STAKES, VALUES_CONFLICT, SCOPE_OVERWHELM"""


def get_first_question(task_description: str) -> dict:
    """Node 1: Given the task text, produce the first diagnostic question + options."""
    messages = [
        SystemMessage(content=FIRST_Q_SYSTEM),
        HumanMessage(content=f"Task the user is avoiding:\n\"{task_description}\""),
    ]
    response = llm.invoke(messages)
    raw = response.content.strip()
    # Strip markdown fences if model wraps in ```json
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


# ------------------------------------------------------------------
# Node 2 — Generate the second (follow-up) diagnostic question
# ------------------------------------------------------------------
SECOND_Q_SYSTEM = f"""You are a clinical psychologist specialising in procrastination.
Your job is differential diagnosis using sequential hypothesis elimination.

The six possible root causes are:
{TAXONOMY}

You already know:
- The task the user is avoiding
- The first diagnostic question that was asked
- The answer the user chose (and which cause_key it maps to)
- Which causes are still candidates

Your job now:
1. Based on the answer, narrow the remaining candidates to 1-2.
2. Write ONE precise follow-up question that confirms or rules out the leading candidate.
3. Provide 2 answer options that map to specific causes.

Respond with ONLY valid JSON (no markdown, no extra text):
{{
  "question": "...",
  "options": [
    {{"text": "...", "cause_key": "IDENTITY_THREAT"}},
    {{"text": "...", "cause_key": "VALUES_CONFLICT"}}
  ],
  "remaining_candidates": ["IDENTITY_THREAT", "VALUES_CONFLICT"]
}}
Use only cause_keys from: IDENTITY_THREAT, GENUINE_AMBIGUITY, ENERGY_MISMATCH, LOW_STAKES, VALUES_CONFLICT, SCOPE_OVERWHELM"""


def get_second_question(task_description: str, q1: str, a1_text: str, a1_cause: str) -> dict:
    """Node 2: Given the task + first Q&A, produce the second diagnostic question."""
    context = (
        f"Task: \"{task_description}\"\n\n"
        f"First question asked: \"{q1}\"\n"
        f"User's answer: \"{a1_text}\" (maps to cause: {a1_cause})"
    )
    messages = [
        SystemMessage(content=SECOND_Q_SYSTEM),
        HumanMessage(content=context),
    ]
    response = llm.invoke(messages)
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


# ------------------------------------------------------------------
# Node 3 — Final diagnosis + prescription
# ------------------------------------------------------------------
DIAGNOSE_SYSTEM = f"""You are a clinical psychologist specialising in procrastination.
You have now completed a two-step differential diagnosis.

The six root causes are:
{TAXONOMY}

Your job is to deliver the final diagnosis. You must:
1. Name the confirmed root cause clearly (be direct and specific — not hedged).
2. Write 2-3 sentences of reasoning that reference what was ruled out and why (this builds trust).
3. Write a prescription matched EXACTLY to this cause — concrete, actionable, specific.
   - No generic tips. The prescription must only work for THIS cause.

Respond with ONLY valid JSON (no markdown, no extra text):
{{
  "confirmed_cause": "IDENTITY_THREAT",
  "title": "This is an identity-threat avoidance, not a difficulty problem.",
  "reasoning": "...",
  "prescription": "...",
  "ruled_out": ["GENUINE_AMBIGUITY", "LOW_STAKES", "ENERGY_MISMATCH", "VALUES_CONFLICT", "SCOPE_OVERWHELM"]
}}"""


def get_diagnosis(task_description: str, q1: str, a1_text: str, a1_cause: str,
                  q2: str, a2_text: str, a2_cause: str) -> dict:
    """Node 3: Full diagnosis based on complete Q&A chain."""
    context = (
        f"Task avoided: \"{task_description}\"\n\n"
        f"Q1: \"{q1}\"\n"
        f"A1: \"{a1_text}\" → {a1_cause}\n\n"
        f"Q2: \"{q2}\"\n"
        f"A2: \"{a2_text}\" → {a2_cause}\n\n"
        f"The final confirmed cause is: {a2_cause}"
    )
    messages = [
        SystemMessage(content=DIAGNOSE_SYSTEM),
        HumanMessage(content=context),
    ]
    response = llm.invoke(messages)
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)
