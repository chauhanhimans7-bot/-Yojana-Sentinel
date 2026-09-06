# The Procrastination Autopsy — Hackathon Pitch & AI Writeup

> **Tagline:** Differential diagnosis for task avoidance — treating root causes, not symptoms.
> **Event:** PromptWars × Abhiyantrix 2026

---

## 1. Executive Summary & Problem Statement

Most productivity apps operate on a flawed assumption: that procrastination has one universal cause and one universal fix (*"just break it into smaller steps!"*).

In reality, task avoidance is almost always driven by one of **six distinct root causes**:
1. **Identity Threat** — Dread that failing at the task will expose personal inadequacy.
2. **Genuine Ambiguity** — Absence of a clear, physical first action.
3. **Energy/Task Mismatch** — Mismatch between cognitive demand and current mental capacity.
4. **Low Stakes / Boredom** — Absence of near consequences or meaningful tension.
5. **Values Conflict** — Quiet internal disagreement about whether the task actually matters.
6. **Scope Overwhelm** — Task size exceeds working memory capacity.

Generic advice fails because it treats the wrong disease. Giving a 5-minute timer to someone suffering from a *Values Conflict* or an *Identity Threat* doesn't unstick them — it just increases friction.

**The Procrastination Autopsy** introduces a diagnostic approach: instead of jumping to advice, it executes sequential hypothesis elimination to isolate the exact cause, show its reasoning, and prescribe a targeted cure.

---

## 2. Technical Architecture & AI Prompting Story

### 🧠 LangGraph Sequential Hypothesis Elimination Chain

Rather than calling an LLM with a single prompt (*"Why is the user procrastinating?"*), Autopsy models the interaction as a 3-node state machine:

```
[ User Input: Avoided Task ]
            │
            ▼
┌───────────────────────────────┐
│ Node 1: Initial Hypothesis     │  Identifies top 2–3 plausible causes from taxonomy.
│         & Branching Question  │  Generates Q1 + options mapped to cause keys.
└───────────────┬───────────────┘
                │ User selects Option A1
                ▼
┌───────────────────────────────┐
│ Node 2: Hypothesis Elimination│  Narrows remaining candidates down to 1–2.
│         & Follow-up Question  │  Generates Q2 + confirming/ruling-out options.
└───────────────┬───────────────┘
                │ User selects Option A2
                ▼
┌───────────────────────────────┐
│ Node 3: Confirmed Diagnosis   │  Confirms root cause, explicitly states ruled-out causes,
│         & Custom Prescription │  and provides a targeted 4-step prescription.
└───────────────────────────────┘
```

### 🎯 Key Prompting Innovations

1. **Strict Taxonomy Constraint:** Every prompt explicitly constrains the LLM to the 6 predefined taxonomy keys (`IDENTITY_THREAT`, `GENUINE_AMBIGUITY`, `ENERGY_MISMATCH`, `LOW_STAKES`, `VALUES_CONFLICT`, `SCOPE_OVERWHELM`). This prevents the model from drifting into astrological or generic self-help jargon.
2. **Sequential Ruling Out (The "Earned" Diagnosis):** The final diagnosis node must explicitly justify *why* other plausible causes were ruled out based on the user's answers. Seeing the ruled-out hypotheses builds immediate trust during a live demo.
3. **JSON Output Contracts:** Every node emits structured JSON schema enforced via strict system instructions.

---

## 3. How to Run Locally

### Prerequisites
- Python 3.10+
- Groq API Key

### Setup
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
# Ensure .env has your GROQ_API_KEY set
GROQ_API_KEY="your_groq_api_key"

# 3. Start the Flask backend server
python server.py
```

### Accessing the App
Open **`http://localhost:5000`** in your browser! Flask serves `autopsy-ui.html` directly at the root URL while handling all AI API routes at `/api/...`.

---

## 4. Live Demo Flow for Judges

1. **Input:** Type a real, raw task in the text box (e.g., *"I need to email my professor about the extension but keep putting it off"*).
2. **Step 1 Q&A:** Watch Autopsy present **Hypothesis 1 of 2** with 3–4 tailored options. Notice the top candidate chips highlight live.
3. **Step 2 Q&A:** Answer the question; watch Autopsy eliminate non-matching causes in real time (**Hypothesis 2 of 2**).
4. **Diagnosis Card:** Reveal the confirmed diagnosis, the explicit reasoning chain showing ruled-out causes, and the specific prescription.
