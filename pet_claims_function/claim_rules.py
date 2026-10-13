"""Pet insurance claim rules. Pure Python, no Azure imports, so it can be unit tested locally."""
from datetime import date, timedelta

# Keyword (lower case) -> reason. Routine and preventive care is commonly excluded.
EXCLUSION_KEYWORDS = {
    "vaccin": "Routine vaccination",
    "booster": "Routine vaccination",
    "flea": "Preventive treatment",
    "worm": "Preventive treatment",
    "microchip": "Routine care",
    "neuter": "Elective procedure",
    "spay": "Elective procedure",
    "castrat": "Elective procedure",
    "scale and polish": "Routine dental care",
    "grooming": "Not veterinary treatment",
}

TOLERANCE = 0.05  # pounds, for rounding differences


def exclusion_reason(description):
    text = (description or "").lower()
    for keyword, reason in EXCLUSION_KEYWORDS.items():
        if keyword in text:
            return reason
    return None


def assess(extraction, policy, settings):
    """Decide a claim.

    extraction: invoiceDate (ISO str or None), statedTotal, taxAmount, confidence,
                petNameFound (bool), lines [{description, amount}]
    policy:     petName, startDate (ISO), annualLimit, excess, paidToDate
    settings:   confidenceThreshold, autoApproveLimit, waitingPeriodDays
    """
    reasons, refer = [], False

    # 1. Extraction quality
    if extraction["confidence"] < settings["confidenceThreshold"]:
        refer = True
        reasons.append(f"Low extraction confidence ({extraction['confidence']:.2f})")
    if not extraction["petNameFound"]:
        refer = True
        reasons.append(f"Pet name '{policy['petName']}' not found on invoice")

    # 2. Waiting period
    inv_date = extraction.get("invoiceDate")
    if not inv_date:
        refer = True
        reasons.append("Invoice date not read")
    else:
        start = date.fromisoformat(policy["startDate"][:10])
        if date.fromisoformat(inv_date[:10]) < start + timedelta(days=int(settings["waitingPeriodDays"])):
            refer = True
            reasons.append(f"Treatment within {settings['waitingPeriodDays']}-day waiting period")

    # 3. Line exclusions
    lines, eligible_net = [], 0.0
    for line in extraction["lines"]:
        amount = float(line.get("amount") or 0)
        reason = exclusion_reason(line.get("description"))
        lines.append({"description": line.get("description", ""), "amount": round(amount, 2),
                      "excluded": reason is not None, "exclusionReason": reason or ""})
        if reason is None:
            eligible_net += amount
    excluded = [l for l in lines if l["excluded"]]
    if excluded:
        reasons.append(f"{len(excluded)} line(s) excluded: " +
                       ", ".join(sorted({l['exclusionReason'] for l in excluded})))

    # 4. Reconciliation: lines (+ VAT if added separately) must match the stated total
    lines_total = round(sum(l["amount"] for l in lines), 2)
    stated = extraction.get("statedTotal")
    tax = extraction.get("taxAmount") or 0.0
    if stated is None:
        refer = True
        reasons.append("Invoice total not read")
        vat_ratio = 1.0
    else:
        vat_added = abs(lines_total + tax - stated) <= TOLERANCE
        vat_inclusive = abs(lines_total - stated) <= TOLERANCE
        if not (vat_added or vat_inclusive):
            refer = True
            reasons.append(f"Lines ({lines_total:.2f}) do not reconcile to total ({stated:.2f})")
        vat_ratio = stated / lines_total if lines_total else 1.0

    # 5. Payable = eligible (incl. VAT) - excess, capped at remaining annual limit
    eligible = round(eligible_net * vat_ratio, 2)
    remaining = max(float(policy["annualLimit"]) - float(policy["paidToDate"]), 0.0)
    after_excess = max(eligible - float(policy["excess"]), 0.0)
    payable = round(min(after_excess, remaining), 2)
    if after_excess > remaining:
        reasons.append(f"Capped at remaining annual limit ({remaining:.2f})")

    decline = False
    if payable <= 0 and not refer:
        decline = True
        reasons.append("Annual limit reached" if remaining <= 0
                       else "Eligible amount does not exceed the excess")
    if payable > float(settings["autoApproveLimit"]):
        refer = True
        reasons.append(f"Payable above auto-approve limit ({settings['autoApproveLimit']})")

    decision = "Referred" if refer else ("Declined" if decline else "Auto-approved")
    return {"decision": decision, "decisionReasons": "; ".join(reasons),
            "linesTotal": lines_total, "eligibleAmount": eligible,
            "payableAmount": payable, "lines": lines}
