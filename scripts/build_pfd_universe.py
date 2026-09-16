#!/usr/bin/env python3
"""
Build the 2023–2024 health/care PFD production universe and retrieval-validation samples.

Inputs:
  reports.csv from:
  https://raw.githubusercontent.com/georgiarichards/preventabledeathstracker/refs/heads/main/src/data/reports.csv

Outputs:
  pfd_healthcare_2023_2024_universe.csv
  pfd_healthcare_2023_2024_R1_candidates.csv
  pfd_healthcare_2023_2024_R0_pool.csv
  pfd_healthcare_2023_2024_R0_sample_seed20260916.csv
  pfd_retrieval_counts.json

Important:
  - R is computed only from circumstances + concerns.
  - reply_urls / response text are never used to define R.
  - Health/care is a high-recall prefilter only; final inclusion remains manual.
  - Sampling seed is frozen at 20260916.
"""
import csv
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path

SEED = 20260916
R0_SAMPLE_N = 100

RETRIEVAL_TERMS = [
    # Investigation
    "investigation", "serious incident", "psii", "psirf", "root cause",
    "mortality review", "structured judgement review", "m&m", "datix",
    # Learning / implementation
    "learning", "lessons", "recommendation", "action plan",
    "implemented", "implementation", "wider learning",
    # Governance
    "governance", "assurance", "oversight", "audit", "review",
    "sign-off", "approval", "escalation",
    # Recursive / independence
    "independent investigation", "previous pfd", "previous report",
    "no investigation", "inadequate investigation", "investigation process",
    "review of investigation",
]

# Deliberately broad: false positives are handled by manual verification.
HEALTH_CARE_TERMS = [
    "nhs", "foundation trust", "health board", "hospital", "ambulance",
    "care quality commission", "cqc", "integrated care board", "icb",
    "department of health and social care", "dhsc", "health education england",
    "gp", "general practice", "medical practice", "clinic", "pharmacy",
    "hospice", "care home", "nursing home", "social care",
    "mental health", "maternity", "midwif", "healthcare", "health care",
]

HEALTH_CARE_CATEGORY_TERMS = [
    "hospital", "mental health", "care home", "health", "medical",
]

def norm(x):
    return re.sub(r"\s+", " ", (x or "").strip().lower())

def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None

def in_period(row):
    d = parse_date(row.get("date_of_report"))
    return bool(d and d.year in (2023, 2024))

def healthcare_prefilter(row):
    recipient = norm(row.get("this_report_is_being_sent_to"))
    category = norm(row.get("category"))
    blob = recipient + " | " + category
    return any(t in blob for t in HEALTH_CARE_TERMS) or any(t in category for t in HEALTH_CARE_CATEGORY_TERMS)

def retrieval_flag(row):
    # Frozen anti-leakage rule: only pre-response report text.
    blob = norm(row.get("circumstances")) + " | " + norm(row.get("concerns"))
    hits = [t for t in RETRIEVAL_TERMS if t in blob]
    return bool(hits), hits

def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def main(input_path):
    input_path = Path(input_path)
    outdir = input_path.parent

    with open(input_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    period = [r for r in rows if in_period(r)]
    hc = [r for r in period if healthcare_prefilter(r)]

    enriched = []
    for r in hc:
        flag, hits = retrieval_flag(r)
        x = dict(r)
        x["retrieval_R"] = "1" if flag else "0"
        x["retrieval_hits"] = " | ".join(hits)
        enriched.append(x)

    r1 = [r for r in enriched if r["retrieval_R"] == "1"]
    r0 = [r for r in enriched if r["retrieval_R"] == "0"]

    rng = random.Random(SEED)
    sample = list(r0)
    rng.shuffle(sample)
    sample = sample[:min(R0_SAMPLE_N, len(sample))]

    base_fields = list(rows[0].keys()) if rows else []
    fields = base_fields + ["retrieval_R", "retrieval_hits"]

    write_csv(outdir / "pfd_healthcare_2023_2024_universe.csv", enriched, fields)
    write_csv(outdir / "pfd_healthcare_2023_2024_R1_candidates.csv", r1, fields)
    write_csv(outdir / "pfd_healthcare_2023_2024_R0_pool.csv", r0, fields)
    write_csv(outdir / "pfd_healthcare_2023_2024_R0_sample_seed20260916.csv", sample, fields)

    counts = {
        "input_rows": len(rows),
        "period_2023_2024_rows": len(period),
        "healthcare_prefilter_rows": len(hc),
        "R1_rows": len(r1),
        "R0_rows": len(r0),
        "R0_sample_rows": len(sample),
        "seed": SEED,
        "sample_target": R0_SAMPLE_N,
    }
    with open(outdir / "pfd_retrieval_counts.json", "w", encoding="utf-8") as f:
        json.dump(counts, f, indent=2)

    print(json.dumps(counts, indent=2))

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python build_pfd_universe.py /path/to/reports.csv")
    main(sys.argv[1])
