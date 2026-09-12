"""
profile_app.py — Baseline Performance Profiler for Yojana Sentinel

Measures:
  1. Total request duration (ms)
  2. Number of DB queries
  3. Total DB query time (ms)
  4. Groq / LLM call count
  5. Total Groq / LLM duration (ms)
across all 12 target operations and page endpoints.
"""

import time
import json
import logging
from dotenv import load_dotenv

load_dotenv()

from approval.app import app
from db.database import get_db, DBConnection
from db.seed import ensure_approval_log_table

logging.basicConfig(level=logging.WARNING)

# Profiling collectors
db_query_count = 0
db_query_total_ms = 0.0
groq_call_count = 0
groq_call_total_ms = 0.0


def reset_metrics():
    global db_query_count, db_query_total_ms, groq_call_count, groq_call_total_ms
    db_query_count = 0
    db_query_total_ms = 0.0
    groq_call_count = 0
    groq_call_total_ms = 0.0


# Patch DBConnection adapter to measure queries
orig_execute = DBConnection.execute
orig_fetchone = DBConnection.fetchone
orig_fetchall = DBConnection.fetchall

def profiled_execute(self, sql, params=()):
    global db_query_count, db_query_total_ms
    db_query_count += 1
    t0 = time.perf_counter()
    res = orig_execute(self, sql, params)
    db_query_total_ms += (time.perf_counter() - t0) * 1000.0
    return res

def profiled_fetchone(self, sql, params=()):
    global db_query_count, db_query_total_ms
    db_query_count += 1
    t0 = time.perf_counter()
    res = orig_fetchone(self, sql, params)
    db_query_total_ms += (time.perf_counter() - t0) * 1000.0
    return res

def profiled_fetchall(self, sql, params=()):
    global db_query_count, db_query_total_ms
    db_query_count += 1
    t0 = time.perf_counter()
    res = orig_fetchall(self, sql, params)
    db_query_total_ms += (time.perf_counter() - t0) * 1000.0
    return res

DBConnection.execute = profiled_execute
DBConnection.fetchone = profiled_fetchone
DBConnection.fetchall = profiled_fetchall


# Patch Groq / LLM calls to count
try:
    import matching.other_conditions_reviewer as ocr
    import drafting.draft_writer as dw

    orig_ocr_call = ocr._call_llm
    def profiled_ocr_call(profile, condition, scheme_name):
        global groq_call_count, groq_call_total_ms
        groq_call_count += 1
        t0 = time.perf_counter()
        res = orig_ocr_call(profile, condition, scheme_name)
        groq_call_total_ms += (time.perf_counter() - t0) * 1000.0
        return res
    ocr._call_llm = profiled_ocr_call

    orig_dw_generate = dw.generate_draft_text
    def profiled_dw_generate(profile, scheme, filled_fields, unresolved_fields):
        global groq_call_count, groq_call_total_ms
        groq_call_count += 1
        t0 = time.perf_counter()
        res = orig_dw_generate(profile, scheme, filled_fields, unresolved_fields)
        groq_call_total_ms += (time.perf_counter() - t0) * 1000.0
        return res
    dw.generate_draft_text = profiled_dw_generate
except Exception as e:
    print("Could not patch LLM hooks:", e)


def profile_endpoint(name, func_or_client_call):
    reset_metrics()
    t0 = time.perf_counter()
    res = func_or_client_call()
    total_ms = (time.perf_counter() - t0) * 1000.0

    print(f"{name:<42} | Total: {total_ms:8.2f} ms | DB Qs: {db_query_count:3d} ({db_query_total_ms:7.2f} ms) | Groq Calls: {groq_call_count:2d} ({groq_call_total_ms:7.2f} ms)")
    return {
        "operation": name,
        "total_ms": round(total_ms, 2),
        "db_query_count": db_query_count,
        "db_query_ms": round(db_query_total_ms, 2),
        "groq_call_count": groq_call_count,
        "groq_call_ms": round(groq_call_total_ms, 2),
    }


def run_benchmark():
    print("=" * 115)
    print(f"{'YOJANA SENTINEL BASELINE PERFORMANCE BENCHMARK':^115}")
    print("=" * 115)
    print(f"{'Operation / Route':<42} | {'Total Time':<14} | {'DB Queries (Duration)':<25} | {'Groq Calls (Duration)':<25}")
    print("-" * 115)

    client = app.test_client()

    with get_db() as db:
        ensure_approval_log_table(db)
        row = db.fetchone("SELECT draft_id FROM application_draft LIMIT 1")
        test_draft_id = row["draft_id"] if row else "draft-d8a5b9b36937"
        scheme_row = db.fetchone("SELECT scheme_id FROM scheme LIMIT 1")
        test_scheme_id = scheme_row["scheme_id"] if scheme_row else "up-postmatric-scholarship-2026"

    results = []

    # 1. Dashboard / Pending Approvals page
    results.append(profile_endpoint("1. Dashboard GET /", lambda: client.get("/")))

    # 2. Matching Engine page
    results.append(profile_endpoint("2. Matching Engine GET /matching", lambda: client.get("/matching")))

    # 3. Monitoring & Demo page
    results.append(profile_endpoint("3. Monitoring & Demo GET /events", lambda: client.get("/events")))

    # 4. Inject & Run Pipeline
    results.append(profile_endpoint("4. POST /events/trigger", lambda: client.post("/events/trigger", data={"scheme_id": test_scheme_id, "event_type": "deadline_approaching"})))

    # 5. Re-run Matching Engine
    results.append(profile_endpoint("5. POST /matching/run", lambda: client.post("/matching/run")))

    # 6. Edit + Save
    results.append(profile_endpoint("6. POST /edit/<draft_id>", lambda: client.post(f"/edit/{test_draft_id}", data={"editor_name": "Benchmark Editor"})))

    # 7. Approve / Mark Ready to Submit
    results.append(profile_endpoint("7. POST /approve/<draft_id>", lambda: client.post(f"/approve/{test_draft_id}", data={"approver_name": "Benchmark Approver"})))

    # 8. Reject Draft
    results.append(profile_endpoint("8. POST /reject/<draft_id>", lambda: client.post(f"/reject/{test_draft_id}", data={"approver_name": "Benchmark Rejector", "reason": "Benchmark test rejection"})))

    # 9. Application Tracking
    results.append(profile_endpoint("9. Application Tracking GET /tracking", lambda: client.get("/tracking")))

    # 10. Audit History
    results.append(profile_endpoint("10. Audit History GET /history", lambda: client.get("/history")))

    # 11. Mark as Submitted
    results.append(profile_endpoint("11. POST /tracking/update (submitted)", lambda: client.post(f"/tracking/update/{test_draft_id}", data={"new_status": "submitted", "note": "Benchmark submitted"})))

    # 12. Update Status / Save Resolution
    results.append(profile_endpoint("12. POST /tracking/update (resolved)", lambda: client.post(f"/tracking/update/{test_draft_id}", data={"new_status": "resolved", "note": "Benchmark resolution"})))

    print("=" * 115)
    with open("benchmark_baseline.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Baseline benchmark results saved to benchmark_baseline.json\n")


if __name__ == "__main__":
    run_benchmark()
