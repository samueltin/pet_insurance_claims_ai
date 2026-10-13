"""Unit tests for the rules. No Azure needed: run with  python test_rules.py"""
from pet_claims_function.claim_rules import assess

POLICY = {"petName": "Biscuit", "startDate": "2025-11-01", "annualLimit": 4000, "excess": 99, "paidToDate": 0}
SETTINGS = {"confidenceThreshold": 0.8, "autoApproveLimit": 500, "waitingPeriodDays": 14}

def ext(lines, total, tax, conf=0.95, pet=True, date="2026-09-04"):
    return {"invoiceDate": date, "statedTotal": total, "taxAmount": tax, "confidence": conf,
            "petNameFound": pet, "lines": [{"description": d, "amount": a} for d, a in lines]}

def check(name, result, decision, payable=None):
    ok = result["decision"] == decision and (payable is None or result["payableAmount"] == payable)
    print(("PASS " if ok else "FAIL ") + name, result["decision"], result["payableAmount"], result["decisionReasons"])

check("simple claim", assess(ext([("Consultation", 58.0), ("Ear drops", 24.5), ("Tablets", 18.9)], 121.68, 20.28), POLICY, SETTINGS), "Auto-approved", 22.68)
check("low confidence", assess(ext([("Consultation", 58.0)], 69.6, 11.6, conf=0.6), POLICY, SETTINGS), "Referred")
check("pet not found", assess(ext([("Consultation", 58.0)], 69.6, 11.6, pet=False), POLICY, SETTINGS), "Referred")
check("waiting period", assess(ext([("Consultation", 158.0)], 189.6, 31.6, date="2025-11-05"), POLICY, SETTINGS), "Referred")
check("all excluded", assess(ext([("Vaccination booster", 55.0)], 66.0, 11.0), POLICY, SETTINGS), "Declined", 0.0)
check("does not reconcile", assess(ext([("Consultation", 58.0)], 99.0, 11.6), POLICY, SETTINGS), "Referred")
check("VAT inclusive", assess(ext([("Consultation", 60.0), ("Urinalysis", 48.0)], 108.0, 18.0), POLICY, SETTINGS), "Auto-approved", 9.0)
check("high value", assess(ext([("Surgery", 900.0)], 1080.0, 180.0), POLICY, SETTINGS), "Referred")
