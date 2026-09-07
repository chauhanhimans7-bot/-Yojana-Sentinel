"""
api/index.py — Vercel Serverless Entry Point for Yojana Sentinel

Exposes the Flask WSGI application instance `app` for @vercel/python.
"""

import sys
from pathlib import Path

# Add project root directory to python path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import the Flask WSGI application instance
from approval.app import app

# Vercel entrypoint WSGI handles
app = app
handler = app
