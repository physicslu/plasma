#!/usr/bin/env python3
from __future__ import annotations
import csv, json
from pathlib import Path

HERE=Path(__file__).resolve().parent
LOCK=HERE/"st-estore-active-exact-coverage-lock-v1.4.json"
CSV=HERE/"st-estore-v13-family-coverage-v1.4.csv"

def req(ok,msg):
    if not ok: raise ValueError(msg)

def main():
    lock=json.loads(LOCK.read_text(encoding="utf-8"))
    req(lock["audit_id"]=="st-estore-active-exact-coverage-lock-v1.4","audit drift")
    req(lock["production_exact_total"]==2683,"production drift")
    req(lock["estore_active_exact_denominator"]==4550,"active denominator drift")
    req(lock["production_current_active_intersection"]==2604,"intersection drift")
    req(lock["active_exact_missing_from_production"]==1946,"gap drift")
    req(lock["production_not_current_active"]==79,"not-active drift")
    req(lock["production_now_nrnd"]==1 and lock["production_not_estore_listed"]==78,"lifecycle split drift")
    req(abs(lock["estore_active_catalog_coverage_percent"]-57.2308)<1e-9,"coverage drift")
    req(lock["catalog_identity_candidate_count"]==1946,"candidate drift")
    req(lock["production_write_authorized"] is False and
        lock["removal_of_79_non_active_authorized"] is False and
        lock["all_1946_are_backend_ready"] is False and
        lock["all_1946_are_physical_verified"] is False,"scope overclaim")
    with CSV.open(newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    req(len(rows)==28,"family row count drift")
    active=sum(int(r["estore_active_exact"]) for r in rows)
    inter=sum(int(r["production_active_intersection"]) for r in rows)
    missing=sum(int(r["active_missing_from_production"]) for r in rows)
    not_active=sum(int(r["production_not_current_active"]) for r in rows)
    req((active,inter,missing,not_active)==(4550,2604,1946,79),"family totals drift")
    req(all(int(r["estore_active_exact"]) ==
            int(r["production_active_intersection"])+int(r["active_missing_from_production"])
            for r in rows),"family set math invalid")
    print("ST_ESTORE_ACTIVE_COVERAGE_LOCK_V14_PASS")
    print(f"Active={active} intersection={inter} missing={missing} coverage=57.2308% not_active={not_active}")
if __name__=="__main__":
    main()
