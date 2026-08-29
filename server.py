"""
server.py — Procrastination Autopsy Flask API
Exposes 3 endpoints that the HTML frontend calls via fetch().

POST /api/begin      { task } → { question, options, top_candidates }
POST /api/followup   { task, q1, a1_text, a1_cause } → { question, options, remaining_candidates }
POST /api/diagnose   { task, q1, a1_text, a1_cause, q2, a2_text, a2_cause } → { confirmed_cause, title, reasoning, prescription, ruled_out }
"""

import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from backend import get_first_question, get_second_question, get_diagnosis

app = Flask(__name__)
CORS(app)  # Allow the HTML file to call us from any origin


@app.route("/", methods=["GET"])
def index():
    """Serve the Autopsy UI HTML directly at the root URL."""
    ui_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "autopsy-ui.html"))
    return send_file(ui_path)


@app.route("/api/begin", methods=["POST"])
def begin():
    """Step 1: User submits the task they're avoiding → get first question."""
    data = request.get_json() or {}
    task = data.get("task", "").strip()
    if not task:
        return jsonify({"error": "Task description is required."}), 400
    try:
        res = get_first_question(task)
        return jsonify(res)
    except Exception as e:
        print(f"Error in /api/begin: {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/followup", methods=["POST"])
def followup():
    """Step 2: User answered Q1 → get second question (sequential elimination)."""
    data = request.get_json() or {}
    task = data.get("task", "").strip()
    q1 = data.get("q1", "").strip()
    a1_text = data.get("a1_text", "").strip()
    a1_cause = data.get("a1_cause", "").strip()

    if not (task and q1 and a1_text and a1_cause):
        return jsonify({"error": "Missing required fields for followup."}), 400

    try:
        res = get_second_question(task, q1, a1_text, a1_cause)
        return jsonify(res)
    except Exception as e:
        print(f"Error in /api/followup: {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/diagnose", methods=["POST"])
def diagnose():
    """Step 3: User answered Q2 → finalize diagnosis, ruled out causes, and prescription."""
    data = request.get_json() or {}
    task = data.get("task", "").strip()
    q1 = data.get("q1", "").strip()
    a1_text = data.get("a1_text", "").strip()
    a1_cause = data.get("a1_cause", "").strip()
    q2 = data.get("q2", "").strip()
    a2_text = data.get("a2_text", "").strip()
    a2_cause = data.get("a2_cause", "").strip()

    if not (task and q1 and a1_text and a1_cause and q2 and a2_text and a2_cause):
        return jsonify({"error": "Missing required fields for diagnosis."}), 400

    try:
        res = get_diagnosis(task, q1, a1_text, a1_cause, q2, a2_text, a2_cause)
        return jsonify(res)
    except Exception as e:
        print(f"Error in /api/diagnose: {e}", flush=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "app": "Procrastination Autopsy"})


if __name__ == "__main__":
    print("🔬 Autopsy backend running at http://127.0.0.1:5000", flush=True)
    app.run(host="0.0.0.0", port=5000, debug=False)
