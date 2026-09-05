# Yojana Sentinel — 3-Minute Live Demo Script

**Target Time:** 2 minutes 45 seconds (15-second buffer for judges' questions)  
**Setup:** Offline execution ready, terminal open at project root, web browser at `http://localhost:5050`  
**Target Persona:** Ramkali Devi (38, widow & farmer in Sitapur, UP), managed by her son Vikram.  
**Target Scheme:** UP Post-Matric OBC Scholarship (`up-scholarship-obc-2026`).

---

## ⏱ Timed Script Breakdown

### 0:00 – 0:20 | The Problem & Context
> *"Over 1,000 government welfare schemes exist in India, but millions of eligible citizens miss out every year simply because they don't know deadlines are approaching or find application forms overwhelming.*
>
> *Existing tools like Yojana Matcher or 'Am I Eligible' are one-shot lookup tools — you search once, get a static list, and you're on your own. They don't **monitor** deadlines, they don't **draft** forms, and they don't **follow up**. Meet **Yojana Sentinel** — an autonomous welfare agent that monitors, matches, drafts, and tracks on behalf of citizens and their families."*

---

### 0:20 – 1:00 | Live Trigger — Autonomous Vigilance
> *(Action: Run command in terminal)*
> ```bash
> python -m monitoring.demo_trigger --scheme up-scholarship-obc-2026 --event deadline_approaching
> ```
> *"Watch what happens live. Our continuous monitoring engine detects a deadline alert on the UP Welfare Portal for the OBC Scholarship scheme. Without Ramkali Devi or her son Vikram doing any manual search, the agent notices the deadline change, logs the event, and immediately re-evaluates Ramkali's family profile."*

---

### 1:00 – 1:40 | Deterministic Matching & LLM Review
> *"The engine runs our 7-dimensional rule matcher — age, state, category, income, land, gender, occupation — completely deterministically with zero LLM hallucination. For ambiguous free-text rules, it queries Groq's LLM to evaluate nuanced criteria.*
>
> *In under two seconds, the system calculates a 66.7% match score with status `partial_match`. Ramkali qualifies on all demographic rules, but is missing two specific paperwork items: her daughter's previous marksheet and institution enrollment certificate."*

---

### 1:40 – 2:20 | Human-in-the-Loop Approval (The Trust Surface)
> *(Action: Switch to browser at `http://localhost:5050` and refresh page)*
> *"Here is what Ramkali's son Vikram sees on his phone. Plain language copy: 'You may qualify — some information is missing.'*
>
> *Notice three critical design choices:*
> 1. *Clear plain-language match explanation (sourced directly from rules).*
> 2. *Pre-filled application cover note with any inferred values clearly marked `[DRAFT]`.*
> 3. *Explicit yellow warning box listing the missing documents so Vikram knows exactly what paperwork to collect before making a trip.*
>
> *Crucially: the approval button says **'Mark Ready to Submit'**, NEVER 'Submit'. Yojana Sentinel **never** submits forms automatically to any government portal. A human always makes the final decision."*

---

### 2:20 – 2:50 | Post-Submission Nudging (Closing the Loop)
> *(Action: Click 'Mark Ready to Submit', then highlight notification feed)*
> *"Once Vikram manually submits Ramkali's application, Yojana Sentinel keeps watching. If an application stays pending past 14 days without an update, the staleness checker automatically fires a follow-up nudge: 'Consider calling the local block office.'*
>
> *That completes the full autonomous lifecycle: **Monitor → Match → Draft → Approve → Track**."*

---

### 2:50 – 3:00 | Roadmap & Close
> *"Today we run in UP for Education, Agriculture, and Health. Next on our roadmap: multi-state expansion and DigiLocker integration. Thank you!"*

---

## 🎯 Designated Live Approval Beat
- **Live Draft Target:** `draft_id` for **Ramkali Devi** × `up-scholarship-obc-2026`.
- **Trust Moment:** The live demo intentionally highlights the **yellow warning box** (2 missing documents) to build judge trust by proving the system never conceals missing requirements.

---

## ✂️ Emergency Cut Plan (If Running Long)
If the timer passes **2:15** while at the approval screen:
- **Cut:** Skip the live demonstration of the staleness notification (Section 2:20 – 2:50).
- **Say instead:** *"And after approval, our tracking module alerts the family if a submitted application stalls past 14 days."* (Jump directly to 2:50 close).
