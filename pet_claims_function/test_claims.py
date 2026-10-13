"""Send every sample invoice to the function and compare with the expected decision.
Usage:
  python test_claims.py                      # local: http://localhost:7071
  FUNC_URL=https://<domain>/api/process-vet-claim FUNC_KEY=<key> python test_claims.py
  (FUNC_URL / FUNC_KEY can also go in a .env file in the project root; real env vars take precedence)
  INVOICES_DIR=/path/to/sample_vet_invoices python test_claims.py
"""
import base64, csv, json, os, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load KEY=VALUE lines from .env without overriding variables already set in the shell.
env_file = os.path.join(ROOT, ".env")
if os.path.exists(env_file):
    for line in open(env_file):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

URL = os.environ.get("FUNC_URL", "http://localhost:7071/api/process-vet-claim")
KEY = os.environ.get("FUNC_KEY", "")
INVOICES = os.environ.get("INVOICES_DIR", os.path.join(ROOT, "sample_vet_invoices"))
CASES = {
    "01_Riverside_Veterinary_Clinic.pdf": "PET-10001",
    "02_Oakwood_Animal_Hospital.pdf": "PET-10004",
    "03_Greenfields_Veterinary_Hospital.pdf": "PET-10005",
    "04_Paws_and_Claws_Veterinary_Centre.pdf": "PET-10002",
    "05_St_Margarets_Veterinary_Surgery_SCANNED.pdf": "PET-10001",
    "06_Hillcrest_Veterinary_Referrals.pdf": "PET-10003",
    "07_Meadowbank_Vets.pdf": "PET-10001",
    "08_Thameside_Pet_Clinic.pdf": "PET-10004"
}
EXPECTED = {
    "01_Riverside_Veterinary_Clinic.pdf": "Auto-approved",
    "02_Oakwood_Animal_Hospital.pdf": "Auto-approved",
    "03_Greenfields_Veterinary_Hospital.pdf": "Referred",
    "04_Paws_and_Claws_Veterinary_Centre.pdf": "Auto-approved",
    "05_St_Margarets_Veterinary_Surgery_SCANNED.pdf": "Auto-approved",
    "06_Hillcrest_Veterinary_Referrals.pdf": "Referred",
    "07_Meadowbank_Vets.pdf": "Declined",
    "08_Thameside_Pet_Clinic.pdf": "Referred"
}

policies = {r["Policy Number"]: r for r in csv.DictReader(open(os.path.join(ROOT, "policies.csv")))}

for file, pol in CASES.items():
    p = policies[pol]
    with open(os.path.join(INVOICES, file), "rb") as f:
        body = {"fileContent": base64.b64encode(f.read()).decode(),
                "petName": p["Pet Name"], "policyStartDate": p["Start Date"],
                "annualLimit": float(p["Annual Limit"]), "excess": float(p["Excess"]),
                "paidToDate": float(p["Paid To Date"]), "confidenceThreshold": 0.8,
                "autoApproveLimit": 500, "waitingPeriodDays": 14}
    headers = {"Content-Type": "application/json"}
    if KEY:
        headers["x-functions-key"] = KEY
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=headers, method="POST")
    r = json.load(urllib.request.urlopen(req))
    flag = "OK  " if r.get("decision") == EXPECTED[file] else "DIFF"
    print(f"{flag} {file[:38]:<40} {r.get('decision', r.get('error')):<14} "
          f"payable {r.get('payableAmount')}  conf {r.get('confidence')}  | {r.get('decisionReasons', r.get('message'))}")
