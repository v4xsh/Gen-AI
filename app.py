import os
import traceback
from typing import List, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from core.config import settings
from core.parser import extract_document_data
from services.analyzer import analyzer_service
from services.batch_processor import batch_processor_service

app = FastAPI(
    title="Legal Document Intelligence System",
    description="Automated contract clause extraction, risk scoring, baseline RAG comparison, and plain-English summary",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store for analyzed contracts
ANALYZED_CONTRACTS: Dict[str, Dict[str, Any]] = {}

class SettingsUpdatePayload(BaseModel):
    api_key: str = ""
    baseline: Dict[str, Any] = {}

class ComparePayload(BaseModel):
    filenames: List[str]
    clause_type: str

@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(status_code=400, content={"error": str(exc)})

@app.exception_handler(Exception)
async def general_error_handler(request, exc):
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"error": f"An unexpected error occurred: {str(exc)}"})

# ─── Settings ─────────────────────────────────────────────────────────────────
@app.get("/api/settings")
async def get_settings():
    has_key = len(settings.gemini_api_key) > 0
    key_display = f"••••••••{settings.gemini_api_key[-4:]}" if has_key and len(settings.gemini_api_key) > 4 else ""
    return {
        "api_key_configured": has_key,
        "api_key_preview": key_display,
        "baseline": settings.load_baseline()
    }

@app.post("/api/settings")
async def update_settings(payload: SettingsUpdatePayload):
    if payload.api_key and not payload.api_key.startswith("••••"):
        settings.gemini_api_key = payload.api_key
    if payload.baseline:
        if not settings.save_baseline(payload.baseline):
            raise HTTPException(status_code=500, detail="Failed to save baseline clauses.")
    return {"message": "Settings updated successfully."}

# ─── Contract Analysis ────────────────────────────────────────────────────────
@app.post("/api/analyze")
async def analyze_contract(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")
    ext = file.filename.split(".")[-1].lower()
    if ext not in ["pdf", "docx"]:
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF and DOCX are supported.")
    try:
        content = await file.read()
        analysis_result = analyzer_service.analyze_document(content, file.filename)
        ANALYZED_CONTRACTS[file.filename] = analysis_result
        return analysis_result
    except ValueError as ve:
        return JSONResponse(status_code=400, content={"error": str(ve)})
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Failed to analyze contract: {str(e)}"})

@app.get("/api/contracts")
async def get_contracts():
    return [
        {
            "filename": filename,
            "overall_risk_score": data.get("overall_risk_score", 0),
            "risk_counts": data.get("risk_counts", {}),
            "is_scanned": data.get("is_scanned", False)
        }
        for filename, data in ANALYZED_CONTRACTS.items()
    ]

@app.get("/api/contracts/{filename}")
async def get_contract_detail(filename: str):
    if filename not in ANALYZED_CONTRACTS:
        raise HTTPException(status_code=404, detail="Contract not found.")
    return ANALYZED_CONTRACTS[filename]

@app.delete("/api/contracts/{filename}")
async def delete_contract(filename: str):
    if filename in ANALYZED_CONTRACTS:
        del ANALYZED_CONTRACTS[filename]
        return {"message": f"Contract '{filename}' deleted successfully."}
    raise HTTPException(status_code=404, detail="Contract not found.")

# ─── Batch Comparison ─────────────────────────────────────────────────────────
@app.post("/api/compare")
async def compare_contracts(payload: ComparePayload):
    missing = [f for f in payload.filenames if f not in ANALYZED_CONTRACTS]
    if missing:
        return JSONResponse(
            status_code=400,
            content={"error": f"These contracts are missing from session: {', '.join(missing)}"}
        )
    contracts_to_compare = [ANALYZED_CONTRACTS[name] for name in payload.filenames]
    try:
        comparison = batch_processor_service.compare_clauses(contracts_to_compare, payload.clause_type)
        return comparison
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"Comparison failed: {str(e)}"})

# ─── Demo Data ────────────────────────────────────────────────────────────────
@app.get("/api/demo")
async def get_demo():
    return {
        "filename": "Acme_SaaS_Agreement_v3.pdf",
        "is_scanned": False,
        "overall_risk_score": 78,
        "risk_counts": {"Low": 1, "Medium": 2, "High": 4},
        "category_risks": {"Financial": 90, "Operational": 75, "Legal": 70, "Reputational": 55},
        "full_text": "SAAS SUBSCRIPTION AGREEMENT\n\nThis Software as a Service Subscription Agreement is entered into as of January 1, 2025 between Acme Corp (Provider) and the Client...",
        "clauses": [
            {
                "clause_type": "Indemnity",
                "clause_text": "Client shall indemnify, defend, and hold harmless Provider and its officers, directors, employees, agents, successors, and assigns from and against any and all claims, damages, losses, costs, and expenses (including reasonable attorneys' fees) arising out of or relating to Client's use of the Services, breach of this Agreement, or violation of any applicable law.",
                "risk_level": "High",
                "risk_score": 82,
                "risk_category": "Financial",
                "deviation": "Unfavourable",
                "comparison_explanation": "One-sided indemnity requiring Client to indemnify Provider without any reciprocal obligation. Market standard requires mutual indemnification limited to each party's own negligence and wilful misconduct.",
                "negotiation_tip": "Replace with a mutual indemnity clause. Each party should only indemnify the other for losses arising directly from its own breach, gross negligence or wilful misconduct.",
                "position": {"start": 1200, "end": 1600}
            },
            {
                "clause_type": "Limitation of Liability",
                "clause_text": "IN NO EVENT SHALL PROVIDER'S TOTAL LIABILITY EXCEED $500 OR ONE MONTH OF FEES PAID, WHICHEVER IS LESS. THIS LIMITATION APPLIES TO ALL CLAIMS REGARDLESS OF THE FORM OF ACTION.",
                "risk_level": "High",
                "risk_score": 91,
                "risk_category": "Financial",
                "deviation": "Unfavourable",
                "comparison_explanation": "Provider's liability cap of $500 or 1 month fees is commercially unreasonable and far below the market standard of 12 months' aggregate fees paid.",
                "negotiation_tip": "Demand a mutual liability cap of at least 12 months of fees paid, with standard carve-outs for fraud, wilful misconduct, and data breaches.",
                "position": {"start": 2100, "end": 2400}
            },
            {
                "clause_type": "Termination",
                "clause_text": "Provider may terminate this Agreement immediately without notice and without liability for any reason at its sole discretion. Client may terminate only upon 180-day written notice and payment of all remaining fees for the contract term.",
                "risk_level": "High",
                "risk_score": 88,
                "risk_category": "Operational",
                "deviation": "Unfavourable",
                "comparison_explanation": "Extremely asymmetric termination rights. Provider can exit instantly with zero liability, while Client is locked in for 180 days and must pay remaining fees.",
                "negotiation_tip": "Negotiate mutual 90-day termination for convenience and a 30-day cure period before any termination for cause.",
                "position": {"start": 3000, "end": 3400}
            },
            {
                "clause_type": "IP Ownership",
                "clause_text": "All work product, deliverables, modifications, improvements, and derivative works created by Provider in connection with this Agreement, including those created using Client Data, shall be the exclusive property of Provider.",
                "risk_level": "High",
                "risk_score": 74,
                "risk_category": "Legal",
                "deviation": "Unfavourable",
                "comparison_explanation": "Provider claims ownership of all deliverables including those derived from Client's own data, which deviates significantly from market standard where client-specific deliverables belong to the client.",
                "negotiation_tip": "Ensure the agreement clearly states Client owns all deliverables created specifically for it and any work product built using Client Data.",
                "position": {"start": 4200, "end": 4600}
            },
            {
                "clause_type": "Payment Terms",
                "clause_text": "All fees are due and payable within 15 days of invoice date. Late payments will incur interest at 24% per annum. Provider may suspend services with 24 hours notice for any overdue payment.",
                "risk_level": "Medium",
                "risk_score": 58,
                "risk_category": "Financial",
                "deviation": "Unusual",
                "comparison_explanation": "15-day payment terms are shorter than the market standard 30 days. 24% interest is punitive. Service suspension at 24 hours is aggressive compared to standard 30-60 day grace periods.",
                "negotiation_tip": "Extend to Net-30 terms, cap late interest at 1.5% per month (18% p.a.), and require at least a 15-day grace period before service suspension.",
                "position": {"start": 5100, "end": 5400}
            },
            {
                "clause_type": "Confidentiality",
                "clause_text": "Client agrees to maintain the confidentiality of Provider's information in perpetuity. Provider's obligations to maintain Client's confidential information expire 12 months after contract termination.",
                "risk_level": "Medium",
                "risk_score": 62,
                "risk_category": "Reputational",
                "deviation": "Unfavourable",
                "comparison_explanation": "Perpetual confidentiality obligation on Client while Provider's reciprocal obligation expires after only 12 months. Market standard is mutual 3-5 year survival.",
                "negotiation_tip": "Replace with a mutual 3-year post-termination confidentiality obligation for both parties.",
                "position": {"start": 5900, "end": 6200}
            },
            {
                "clause_type": "Governing Law",
                "clause_text": "This Agreement shall be governed by the laws of the State of Delaware, without regard to its conflict of law provisions. Any disputes shall be resolved exclusively in the courts of New Castle County, Delaware.",
                "risk_level": "Low",
                "risk_score": 18,
                "risk_category": "Legal",
                "deviation": "Favourable",
                "comparison_explanation": "Delaware governing law is commercially standard for US technology contracts. No material deviation.",
                "negotiation_tip": "No immediate revision necessary unless the Client is based outside the US and objects to travel for litigation.",
                "position": {"start": 6800, "end": 7100}
            }
        ],
        "executive_summary": {
            "scope": "This is a SaaS Subscription Agreement between Acme Corp (Provider) and the Client for enterprise software services, covering a 3-year term with annual fee escalation.",
            "risk_allocation": "The Client bears the overwhelming majority of contractual risk. The Provider has secured nearly unlimited indemnity protection, a $500 liability cap, unilateral termination rights, and IP ownership of all deliverables — creating a profoundly one-sided commercial arrangement.",
            "key_commercial_terms": [
                "3-year fixed term with 180-day termination notice required from Client",
                "Annual fee escalation at Provider's discretion with no cap",
                "Payment due within 15 days (vs. 30-day market standard)",
                "Provider retains all IP including custom deliverables built on Client Data",
                "Delaware governing law with exclusive jurisdiction in New Castle County"
            ],
            "top_negotiation_issues": [
                "Liability Cap ($500): A $500 liability cap means the Provider has virtually no financial accountability for any failures, outages, or data breaches — demand a mutual 12-month fee cap.",
                "One-Sided Termination: Provider can shut down service instantly with zero notice while you're locked in for 180 days — negotiate mutual 90-day convenience termination.",
                "IP Ownership Grab: Any custom development built using your data becomes Provider's property — insist on Client ownership of all bespoke deliverables."
            ]
        }
    }

# ─── Static Files ─────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_index():
    index_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "LexAI API running. Static files not found."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)
