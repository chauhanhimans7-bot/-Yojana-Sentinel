# Yojana Sentinel — Complete QA Bug Report

This bug report was generated following a comprehensive end-to-end audit of the Yojana Sentinel application (live deployment & codebase) as specified in `yojana_sentinel_qa_bug_prompt.md`.

---

## Bug 1: Duplicate Application Draft Creation on Re-Running Matching Engine
**Severity:** Critical  
**Where:** `/matching` and `main.py` -> `batch_create_drafts()`  
**Steps to reproduce:**
1. Navigate to `/matching`.
2. Click "Re-run Matching Engine" once.
3. Click "Re-run Matching Engine" a SECOND time immediately after.
4. Navigate to `/` (Pending Approvals).

**Expected:**  
The draft count on Pending Approvals should remain unchanged (existing active drafts should be updated in place or skipped if unchanged).

**Actual:**  
`batch_create_drafts()` in `main.py` calls `create_draft(..., force_new=True)` unconditionally for every actionable match result. Every time matching is re-run, brand new `ApplicationDraft` records with unique UUIDs are inserted into the database, multiplying the draft count on the Pending Approvals dashboard with exact duplicates.

---

## Bug 2: Metric Card Misalignment ("Ready to Review" Includes Drafts with Missing Info)
**Severity:** Medium  
**Where:** `/` (Pending Approvals Dashboard)  
**Steps to reproduce:**
1. Load `/` with drafts that have `unresolved_fields` (missing required fields) and are not stale.
2. Check the top metric cards ("With Missing Info" vs "Ready to Review").

**Expected:**  
"Ready to Review" should only count clean drafts that are NOT stale AND have zero missing required fields (`unresolved_fields` is empty).

**Actual:**  
In `templates/index.html` line 36, "Ready to Review" is calculated as `{{ drafts | rejectattr('is_stale') | list | length }}`. A draft with missing required info is counted under BOTH "With Missing Info" and "Ready to Review", over-reporting the count of ready-to-review drafts.

---

## Bug 3: Test Fixture Entries Leaking into Production Event Log (`s-diff-101`)
**Severity:** Low  
**Where:** `/events` (Monitoring & Demo Log)  
**Steps to reproduce:**
1. Navigate to `/events`.
2. Scroll through the Monitoring Event Log table.

**Expected:**  
The event log should only contain real portal events or demo-injected scheme events targeting valid schemes from the scheme catalog.

**Actual:**  
Over 15 leftover test-fixture records with scheme ID `s-diff-101` (names like "New Agri Scheme," "Updated Scheme," "Closed Scheme") generated during automated unit testing are stored in `data/event_log.json` and rendered in the live UI feed.

---

## Bug 4: Duplicate Event Injection in Demo Injector
**Severity:** High  
**Where:** `/events` and `monitoring/demo_trigger.py`  
**Steps to reproduce:**
1. Navigate to `/events`.
2. Select target scheme "Ayushman Bharat" and event type "Deadline Approaching".
3. Click "Inject & Run Pipeline".
4. Immediately select the same scheme "Ayushman Bharat" and "Deadline Approaching" event type again and click "Inject & Run Pipeline".

**Expected:**  
Per the design specification, the pipeline should enforce event deduplication (`has_deadline_alert`) or notify the user that a deadline alert has already fired for this scheme.

**Actual:**  
`inject_event()` in `demo_trigger.py` bypasses `has_deadline_alert()` check and unconditionally appends duplicate `deadline_approaching` events to `monitoring_event` table and `event_log.json`.

---

## Bug 5: Audit History Page Does Not Display Human Edit Log Records
**Severity:** High  
**Where:** `/history` (Audit History)  
**Steps to reproduce:**
1. Edit fields on a draft via `/edit/<draft_id>`.
2. Navigate to `/history`.

**Expected:**  
All human actions (approvals, rejections, field edits, status updates) recorded in `approval_log` and `status_transition_log` show up with exact actor name, timestamp, action type, and details.

**Actual:**  
`history_view()` in `approval/app.py` only queries `application_draft` table rows and displays current draft status. It ignores `approval_log` entries, so field edit actions (`request_edit`) do not appear in `/history`.

---

## Bug 6: State Transition History Lost on Serverless / Vercel Environment
**Severity:** High  
**Where:** `/tracking` (Application Tracking)  
**Steps to reproduce:**
1. Transition an approved draft to `submitted` or `pending` on the live Vercel deployment.
2. Expand "State transition history" on the draft card.

**Expected:**  
State transition history logs show all previous status changes with timestamps and notes.

**Actual:**  
`get_transition_history(draft_id)` in `tracking/status_store.py` only reads from `data/status_transition_log.json`. Because local file writes fail gracefully on Vercel's read-only filesystem, `status_transition_log.json` is not updated in production, causing the transition history list to remain empty on serverless deployments.

---

## Bug 7: Field ID Labeling in Missing Fields Warning Box Uses Raw Column Names
**Severity:** Low  
**Where:** `/` (Pending Approvals)  
**Steps to reproduce:**
1. Open a draft with missing fields such as `pmjay_eligibility_letter_or_e` or `bank_account_number`.
2. Observe the missing fields warning bullet list.

**Expected:**  
Missing fields should display nicely formatted human-readable labels from scheme metadata (e.g., "PMJAY Eligibility Letter or E-Card").

**Actual:**  
`templates/index.html` line 113 renders `{{ fid.replace('_', ' ').title() }}`, resulting in awkward title-cased strings like "Pmjay Eligibility Letter Or E".
