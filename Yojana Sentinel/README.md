# 🛡️ Yojana Sentinel — AI Welfare Scheme Monitoring & Assistance System

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/framework-Flask-emerald.svg)](https://flask.palletsprojects.com/)
[![Groq API](https://img.shields.io/badge/LLM-Groq--Llama3-purple.svg)](https://groq.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Yojana Sentinel** is an AI-powered welfare-scheme monitoring and application-assistance platform designed to ensure Indian citizens never miss out on government schemes they are eligible for. It combines continuous portal differential monitoring, hard-rule eligibility scoring, LLM reasoning, pre-filled application drafting, and human-in-the-loop sign-off.

---

## 🌟 Key Features & Workflow

```
Government Portal Data 
       │
       ▼
 📡 1. Scheme Monitoring (Event Detection & Deadline Alerts)
       │
       ▼
 📊 2. Beneficiary Matching Engine (Hard Rules + Groq AI Reasoning)
       │
       ▼
 📝 3. Application Draft Generator (Field Auto-Mapping & LLM Cover Letter)
       │
       ▼
 👤 4. Human-in-the-Loop Review (Never Auto-Submits — Sign-off Required)
       │
       ▼
 🚚 5. Application Tracking & Audit History (State Machine & Permanent Trail)
```

1. **Continuous Scheme Monitoring**: Detects deadline alerts, new scheme launches, and eligibility criteria updates across government portals (e.g. NFSA, PMJAY, Kisan Credit Card).
2. **Deterministic & AI Matching Engine**: Evaluates citizen profiles against scheme criteria using a 5-step scoring pipeline (category, age, income, land, and gender hard rules) complemented by Groq LLM reasoning.
3. **Application Draft Preparation**: Automatically maps profile details to scheme application fields, flags missing parameters, and generates formal plain-language cover letters.
4. **Human Sign-Off & Staleness Policy**: **Never auto-submits to external portals.** If a scheme's rules update after a draft is written, it is automatically flagged as `STALE` and locked until re-evaluated.
5. **Futuristic Command Center UI**: Modern dark glassmorphism dashboard built with responsive CSS grid, animated match score rings, pulsing live indicators, and interactive state-machine timelines.

---

## 🚀 Quick Start Guide

### Prerequisites
- Python 3.10+ installed
- Groq API Key ([Get a key from Groq Console](https://console.groq.com))

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/yojana-sentinel.git
cd yojana-sentinel
```

### 2. Set Up Virtual Environment & Install Dependencies
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Mac/Linux:
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy the `.env.example` file to `.env` and set your Groq API key:
```bash
cp .env.example .env
```
Edit `.env`:
```env
GROQ_API_KEY=gsk_your_actual_groq_api_key_here
```

### 4. Run the Application
Launch the unified web application:
```bash
python main.py
```
Open **http://127.0.0.1:5000** in your browser.

---

## 💻 Technical Stack

- **Backend**: Python, Flask web framework
- **Database**: SQLite3 (stored in `data/yojana_sentinel.db` with WAL mode enabled)
- **AI / LLM**: Groq API (`llama-3.3-70b-versatile` / `llama-3.1-8b-instant`)
- **Frontend**: Server-side rendered Jinja2 templates (`templates/`), Vanilla CSS3 with Glassmorphism Design System (`static/css/sentinel.css`), Vanilla JS for micro-interactions & animations (`static/js/sentinel.js`)
- **Testing**: `pytest`

---

## 📁 Repository Structure

```
├── approval/               # Web application server & human action handlers
├── config/                 # Scope configuration (categories, thresholds)
├── data/                   # SQLite database & JSON fallback seeds
├── db/                     # Database schema definition & seed scripts
├── drafting/               # Application draft generator & field mapper
├── ingestion/              # Government scheme portal scrapers & normalizers
├── matching/               # Rules engine & LLM eligibility reviewer
├── monitoring/             # Portal differential engine, event log & triggers
├── static/                 # CSS design system & JavaScript micro-interactions
├── templates/              # Jinja2 HTML templates for all web routes
├── tests/                  # Automated pytest suite
├── tracking/               # Application status state machine & audit log
├── .env.example            # Environment variables template
├── .gitignore              # Files ignored by Git
├── main.py                 # Core application entrypoint
└── requirements.txt        # Python package dependencies
```

---

## 🛡️ Safety & Privacy Philosophy

- **Zero Auto-Submit Guarantee**: Yojana Sentinel prepares application drafts and evaluates eligibility locally. It **never automatically submits applications** to government portals on behalf of citizens.
- **Human Verification**: A human representative or citizen must explicitly review all generated content and execute the final submission manually.
- **Immutable Audit Logging**: Every human approval, rejection, or field modification is recorded with timestamps and actor details.

---

## 📄 License
This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
