import os

# Guarantee test environment isolation for all unittest / pytest runs
os.environ["TESTING"] = "1"
