import base64, json, os, re
import azure.functions as func
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential
from pet_claims_function.claim_rules import assess

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


def extract(pdf_bytes, pet_name):
    """Read a vet invoice with the prebuilt-invoice model and return clean, typed facts."""
    client = DocumentIntelligenceClient(
        os.environ["DI_ENDPOINT"], AzureKeyCredential(os.environ["DI_KEY"]))
    result = client.begin_analyze_document(
        "prebuilt-invoice", AnalyzeDocumentRequest(bytes_source=pdf_bytes)).result()
    fields = result.documents[0].fields if result.documents else {}

    def text(name):
        f = fields.get(name)
        return (f.content if f else None), (f.confidence if f else 0.0)

    def money(name):
        f = fields.get(name)
        amount = f.value_currency.amount if f and f.value_currency else None
        return amount, (f.confidence if f else 0.0)

    def iso_date(name):
        f = fields.get(name)
        value = f.value_date.isoformat() if f and f.value_date else None
        return value, (f.confidence if f else 0.0)

    practice, c1 = text("VendorName")
    number, c2 = text("InvoiceId")
    inv_date, c3 = iso_date("InvoiceDate")
    total, c4 = money("InvoiceTotal")
    tax, _ = money("TotalTax")
    owner, _ = text("CustomerName")

    lines = []
    items = fields.get("Items")
    for item in (items.value_array if items and items.value_array else []):
        obj = item.value_object or {}
        desc, amt = obj.get("Description"), obj.get("Amount")
        lines.append({"description": desc.content if desc else "",
                      "amount": amt.value_currency.amount if amt and amt.value_currency else 0.0})

    # The pet's name is not a standard invoice field, so we verify it against the full text.
    content = result.content or ""
    pet_found = bool(pet_name) and re.search(rf"\b{re.escape(pet_name)}\b", content, re.I) is not None

    return {"practiceName": practice, "invoiceNumber": number, "invoiceDate": inv_date,
            "ownerName": owner, "statedTotal": total, "taxAmount": tax,
            "confidence": round(min(c1, c2, c3, c4), 3), "petNameFound": pet_found,
            "pageCount": len(result.pages or []), "lines": lines}


@app.route(route="process-vet-claim", methods=["POST"])
def process_vet_claim(req: func.HttpRequest) -> func.HttpResponse:
    try:
        p = json.loads(req.get_body())
        extraction = extract(base64.b64decode(p["fileContent"]), p.get("petName", ""))
        policy = {"petName": p.get("petName", ""), "startDate": p["policyStartDate"],
                  "annualLimit": p["annualLimit"], "excess": p["excess"],
                  "paidToDate": p.get("paidToDate", 0)}
        settings = {"confidenceThreshold": p.get("confidenceThreshold", 0.8),
                    "autoApproveLimit": p.get("autoApproveLimit", 500),
                    "waitingPeriodDays": p.get("waitingPeriodDays", 14)}
        decision = assess(extraction, policy, settings)
        body = {**{k: v for k, v in extraction.items() if k != "lines"}, **decision}
        return func.HttpResponse(json.dumps(body), mimetype="application/json")
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": type(e).__name__, "message": str(e)}),
                                 status_code=500, mimetype="application/json")
