# Status Tracking Limitations & Design Strategy

## 1. Why Status Tracking is Manual / Mocked in Yojana Sentinel
In the current Indian government welfare ecosystem, **there is no unified, public real-time status tracking REST API** across central and state welfare portals (e.g. UP Scholarship, PM-KISAN, PMMVY).

Attempting to fake a "live API integration" with government databases would be dishonest to hackathon judges and end users. Therefore, Yojana Sentinel adopts an **honest, human-in-the-loop tracking architecture**.

---

## 2. How Status Tracking Works in the MVP

### State Machine Lifecycle
`drafted` → `approved` → `submitted` → `pending` → `resolved` (or `rejected`)

1. **Human Confirmation (`mark_submitted`)**
   - Because the agent NEVER auto-submits applications, it has no direct way of knowing when a human physically submits the form.
   - The citizen or family member explicitly clicks **"I Have Submitted This"** in the app.

2. **Manual / Demo Status Updates (`update_status`)**
   - Operators or family members can manually update status when they receive an SMS or physical letter from the department.
   - Demo scripts can simulate status transitions to demonstrate downstream nudging.

3. **Automated Staleness Nudges (`staleness_checker.py` + `notifications.py`)**
   - If an application remains in `submitted` or `pending` state past the configured threshold (`status_stale_after_days` in `config/scope.json`, default 14 days) without any status updates:
   - The agent automatically generates a **Staleness Follow-Up Nudge** advising the family member to contact the local block office or check the portal.

---

## 3. Future Integration Roadmap
When government portals publish public open-data APIs or digilocker-integrated status webhooks:
- `tracking/status_store.py` will serve as the abstract interface layer.
- Webhook handlers can be attached directly to call `update_status()` without changing downstream notification or state machine logic.
