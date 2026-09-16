#!/usr/bin/env python3
"""Run the frozen PFD meta-repair retrieval protocol on PFD Toolkit all_reports.csv.

Only the SOURCE ADAPTER differs from scripts/build_pfd_universe.py:
- date <- date
- ref <- id
- recipient <- receiver
- health/care high-recall prefilter <- original recipient dictionary OR selected
  PFD Toolkit health/care theme flags.

The Stage-A retrieval dictionary, anti-leakage rule, seed (20260916), and
R=0 sample target (100) are unchanged.
"""
import csv, json, random, re, sys
from datetime import datetime
from pathlib import Path

SEED = 20260916
R0_SAMPLE_N = 100

RETRIEVAL_TERMS = [
    "investigation", "serious incident", "psii", "psirf", "root cause",
    "mortality review", "structured judgement review", "m&m", "datix",
    "learning", "lessons", "recommendation", "action plan",
    "implemented", "implementation", "wider learning",
    "governance", "assurance", "oversight", "audit", "review",
    "sign-off", "approval", "escalation",
    "independent investigation", "previous pfd", "previous report",
    "no investigation", "inadequate investigation", "investigation process",
    "review of investigation",
]

HEALTH_CARE_TERMS = [
    "nhs", "foundation trust", "health board", "hospital", "ambulance",
    "care quality commission", "cqc", "integrated care board", "icb",
    "department of health and social care", "dhsc", "health education england",
    "gp", "general practice", "medical practice", "clinic", "pharmacy",
    "hospice", "care home", "nursing home", "social care",
    "mental health", "maternity", "midwif", "healthcare", "health care",
]

# Source-adapter equivalent of the original broad health/care category prefilter.
HEALTH_THEME_COLUMNS = [
    "theme_sent_to_nhs_bodies",
    "theme_sent_to_health_regulators",
    "theme_access_to_care",
    "theme_ambulance_response",
    "theme_care_home_safety",
    "theme_discharge_planning",
    "theme_hospital_care",
    "theme_infection_control",
    "theme_medication_safety",
    "theme_mental_health_care",
    "theme_observation_failures",
    "theme_physical_health_in_mental_health",
    "theme_record_keeping",
    "theme_safeguarding",
    "theme_staff_shortages",
    "theme_staff_training",
    "theme_substance_misuse",
    "theme_emergency_departments",
    "theme_ambulance_services",
    "theme_primary_care",
    "theme_out_of_hours_care",
    "theme_acute_hospital_wards",
    "theme_intensive_care",
    "theme_surgical_care",
    "theme_maternity_neonatal_perinatal_care",
    "theme_mental_health_services",
    "theme_substance_use_services",
    "theme_care_homes",
    "theme_domiciliary_care",
    "theme_hospices_palliative_care",
    "theme_secure_health_settings",
    "theme_diagnostic_delay",
    "theme_sepsis_infection",
    "theme_cancer_care",
    "theme_cardiovascular_conditions",
    "theme_respiratory_conditions",
    "theme_neurological_conditions",
    "theme_diabetes_metabolic_conditions",
    "theme_falls_frailty",
    "theme_choking_aspiration",
    "theme_learning_disability",
    "theme_autism",
    "theme_cognitive_impairment",
    "theme_epilepsy_seizure_management",
    "theme_allergy_anaphylaxis",
    "theme_risk_assessment_failures",
    "theme_failure_recognise_escalate_deterioration",
    "theme_communication_failures",
    "theme_handover_failures",
    "theme_record_sharing_failures",
    "theme_referral_failures",
    "theme_follow_up_failures",
    "theme_transitions_discharge_failures",
    "theme_observation_monitoring_failures",
    "theme_test_result_management_failures",
    "theme_capacity_best_interests_failures",
    "theme_staffing_shortages_workload_pressure",
    "theme_training_competence_gaps",
    "theme_policy_procedure_failures",
    "theme_equipment_failures",
    "theme_it_digital_system_failures",
    "theme_alarm_alert_failures",
    "theme_delayed_admission",
    "theme_bed_shortages",
    "theme_safeguarding_failures",
    "theme_inter_agency_working",
    "theme_continuity_of_care",
    "theme_family_carer_concerns_not_acted_on",
    "theme_reasonable_adjustments_not_made",
    "theme_investigation_incident_review_failures",
    "theme_failure_learn_previous_deaths_incidents",
    "theme_thresholds_eligibility_barriers",
    "theme_waiting_times_delays",
]

def norm(x):
    return re.sub(r"\s+", " ", (x or "").strip().lower())

def is_true(x):
    return norm(x) in {"true","1","yes","y","t"}

def parse_date(s):
    s=(s or "").strip()
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%d/%m/%y"):
        try: return datetime.strptime(s[:10],fmt)
        except ValueError: pass
    return None

def in_period(row):
    d=parse_date(row.get("date"))
    return bool(d and d.year in (2023,2024))

def healthcare_prefilter(row):
    recipient=norm(row.get("receiver"))
    recipient_hit=any(t in recipient for t in HEALTH_CARE_TERMS)
    theme_hit=any(is_true(row.get(c)) for c in HEALTH_THEME_COLUMNS if c in row)
    return recipient_hit or theme_hit

def retrieval_flag(row):
    blob=norm(row.get("circumstances"))+" | "+norm(row.get("concerns"))
    hits=[t for t in RETRIEVAL_TERMS if t in blob]
    return bool(hits), hits

def canonical(row):
    d=parse_date(row.get("date"))
    return {
        "date_of_report": d.strftime("%Y-%m-%d") if d else "",
        "ref": (row.get("id") or "").strip(),
        "deceased_name": "",
        "coroner_name": (row.get("coroner") or "").strip(),
        "coroner_area": (row.get("area") or "").strip(),
        "category": "",
        "this_report_is_being_sent_to": (row.get("receiver") or "").strip(),
        "report_url": (row.get("url") or "").strip(),
        "circumstances": row.get("circumstances") or "",
        "concerns": row.get("concerns") or "",
        "investigation": row.get("investigation") or "",
    }

def write_csv(path, rows, fields):
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

def main(input_path):
    p=Path(input_path); outdir=p.parent
    with p.open(encoding="utf-8-sig",newline="") as f:
        raw=list(csv.DictReader(f))
    period=[r for r in raw if in_period(r)]
    hc_raw=[r for r in period if healthcare_prefilter(r)]
    enriched=[]
    for rr in hc_raw:
        x=canonical(rr)
        flag,hits=retrieval_flag(rr)
        x["retrieval_R"]="1" if flag else "0"
        x["retrieval_hits"]=" | ".join(hits)
        enriched.append(x)
    # Deduplicate conservatively by URL, falling back to ref+date.
    seen=set(); dedup=[]
    for r in enriched:
        key=r["report_url"] or (r["ref"]+"|"+r["date_of_report"])
        if key not in seen:
            seen.add(key); dedup.append(r)
    enriched=dedup
    r1=[r for r in enriched if r["retrieval_R"]=="1"]
    r0=[r for r in enriched if r["retrieval_R"]=="0"]
    rng=random.Random(SEED); sample=list(r0); rng.shuffle(sample); sample=sample[:min(R0_SAMPLE_N,len(sample))]
    fields=["date_of_report","ref","deceased_name","coroner_name","coroner_area","category","this_report_is_being_sent_to","report_url","circumstances","concerns","investigation","retrieval_R","retrieval_hits"]
    write_csv(outdir/"pfd_healthcare_2023_2024_universe.csv",enriched,fields)
    write_csv(outdir/"pfd_healthcare_2023_2024_R1_candidates.csv",r1,fields)
    write_csv(outdir/"pfd_healthcare_2023_2024_R0_pool.csv",r0,fields)
    write_csv(outdir/"pfd_healthcare_2023_2024_R0_sample_seed20260916.csv",sample,fields)
    counts={
        "source":"PFD Toolkit dataset-latest",
        "input_rows":len(raw),
        "period_2023_2024_rows":len(period),
        "healthcare_prefilter_rows_raw":len(hc_raw),
        "healthcare_prefilter_rows_deduplicated":len(enriched),
        "R1_rows":len(r1),
        "R0_rows":len(r0),
        "R0_sample_rows":len(sample),
        "seed":SEED,
        "sample_target":R0_SAMPLE_N,
        "retrieval_dictionary_changed":False,
        "source_adapter_changed":True,
    }
    (outdir/"pfd_retrieval_counts.json").write_text(json.dumps(counts,indent=2),encoding="utf-8")
    print(json.dumps(counts,indent=2))

if __name__=="__main__":
    if len(sys.argv)!=2: raise SystemExit("Usage: python build_pfd_universe_toolkit.py /path/to/all_reports.csv")
    main(sys.argv[1])
