"""
seed_drafts_offline_fallback.py

⚠️ OFFLINE FALLBACK SEED SCRIPT FOR DEMO SAFETY ONLY ⚠️

This script is NOT the production drafting path.
The production pipeline is:
  drafting/create_draft.py → drafting/field_mapper.py + drafting/draft_writer.py (Groq LLM-backed)

This file exists ONLY as a network-independent offline fallback to populate
ApplicationDraft rows in data/yojana_sentinel.db if stage internet / Groq API quota
is unavailable during a live presentation.
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from drafting.field_mapper import map_fields

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "yojana_sentinel.db"

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

with open(ROOT / "data" / "match_results.json", "r", encoding="utf-8") as f:
    results = json.load(f)

with open(ROOT / "data" / "schemes_seed.json", "r", encoding="utf-8") as f:
    schemes = {s["scheme_id"]: s for s in json.load(f)}

with open(ROOT / "data" / "profiles_seed.json", "r", encoding="utf-8") as f:
    profiles = {p["profile_id"]: p for p in json.load(f)}

created = 0
for r in results:
    if r["match_status"] in ("strong_match", "partial_match"):
        pid = r["profile_id"]
        sid = r["scheme_id"]
        p = profiles[pid]
        s = schemes[sid]
        
        filled, unresolved = map_fields(p, s)
        
        if unresolved:
            header = "⚠️ Before this can be submitted, you still need to provide:\n"
            for u in unresolved:
                header += f"  • {u.replace('_', ' ').title()}\n"
            header += "\n"
        else:
            header = "✅ All required fields are filled. This draft is ready for your review.\n\n"
            
        cover = (
            f"To Whomsoever It May Concern,\n\n"
            f"I am applying for the {s.get('name', sid)} on behalf of {p.get('display_name')}.\n"
            f"Annual Family Income: ₹{p.get('annual_income', 'N/A')}\n"
            f"Category: {str(p.get('category', 'N/A')).upper()}\n"
            f"State of Residence: {p.get('state', 'Uttar Pradesh')}\n\n"
            f"We satisfy the eligibility requirements and request favorable processing of this application.\n\n"
            f"Regards,\n{p.get('display_name')}"
        )

        footer = (
            f"\n\n------------------------------------------------------------\n"
            f"📌 Source: {s.get('name')} — {s.get('source_url')}\n"
            f"   This is a DRAFT prepared by Yojana Sentinel. It has not been submitted anywhere.\n"
            f"   A human must review and manually submit this application."
        )
        
        draft_text = header + cover + footer
        draft_id = f"draft-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        
        conn.execute(
            """INSERT OR REPLACE INTO application_draft
               (draft_id, profile_id, scheme_id, filled_fields, unresolved_fields, draft_text, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (draft_id, pid, sid, json.dumps(filled, ensure_ascii=False), json.dumps(unresolved, ensure_ascii=False), draft_text, "drafted", now)
        )
        created += 1

conn.commit()
conn.close()
print(f"[OFFLINE FALLBACK SEED] Successfully seeded {created} drafts into {DB_PATH}")
