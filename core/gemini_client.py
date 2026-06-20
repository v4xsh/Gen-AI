import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import google.generativeai as genai
from core.config import settings

# Define Pydantic response schemas for structured extraction

class ExtractedClause(BaseModel):
    clause_type: str = Field(
        description="One of: Indemnity, Limitation of Liability, Governing Law, Termination, IP Ownership, Payment Terms, Confidentiality"
    )
    clause_text: str = Field(
        description="The exact verbatim text of the clause as found in the contract. Keep it as close to the original as possible."
    )
    risk_level: str = Field(
        description="Risk Level: Low, Medium, High"
    )
    risk_score: int = Field(
        description="Risk score from 0 (no risk) to 100 (extreme risk/poison pill)"
    )
    risk_category: str = Field(
        description="The primary risk bucket: Financial, Operational, Legal, or Reputational"
    )
    deviation: str = Field(
        description="How it compares to market standard: Favourable, Unfavourable, Unusual"
    )
    comparison_explanation: str = Field(
        description="Detailed explanation of how this clause deviates from the market standard baseline, referencing specific elements."
    )
    negotiation_tip: str = Field(
        description="Actionable, strategic tip for negotiating this clause to protect the business interests."
    )

class ExecutiveSummary(BaseModel):
    scope: str = Field(
        description="A concise plain-English explanation of what this contract covers and its scope (1-2 sentences)."
    )
    risk_allocation: str = Field(
        description="Clear explanation of how risk is allocated between the parties (who carries the burden of liability/indemnity) (2-3 sentences)."
    )
    key_commercial_terms: List[str] = Field(
        description="Bullet points of the main commercial terms (e.g. costs, fees, deliverables, schedules)."
    )
    top_negotiation_issues: List[str] = Field(
        description="Exactly three critical issues/clauses prioritized for negotiation, with a brief plain-English rationale for each."
    )

class ContractAnalysisResult(BaseModel):
    clauses: List[ExtractedClause] = Field(
        description="List of all extracted clauses representing key target areas."
    )
    executive_summary: ExecutiveSummary = Field(
        description="Plain-English 1-page summary of the contract."
    )
    overall_risk_score: int = Field(
        description="Aggregated contract risk score from 0-100 based on the severity of extracted risks."
    )


# Client interface class
class GeminiClient:
    def __init__(self):
        self._configured_api_key = None

    def _get_model(self) -> genai.GenerativeModel:
        api_key = settings.gemini_api_key
        if not api_key:
            raise ValueError("Gemini API Key is not set. Please set it in the Settings panel.")
            
        if self._configured_api_key != api_key:
            genai.configure(api_key=api_key)
            self._configured_api_key = api_key
            
        return genai.GenerativeModel(settings.default_model)

    def analyze_contract(
        self, 
        full_text: str, 
        is_scanned: bool = False, 
        file_bytes: Optional[bytes] = None
    ) -> ContractAnalysisResult:
        """
        Extracts clauses, conducts market standard comparison, generates risk scores,
        and provides an executive summary for a single contract.
        """
        model = self._get_model()
        baseline_data = settings.load_baseline()
        
        # Build baseline description for the prompt
        baseline_desc = ""
        for key, val in baseline_data.items():
            baseline_desc += f"\n- **{val['title']}** (Market Standard):\n  Standard: {val['standardText']}\n  Ideal risk profile: {val['idealRisk']}\n"

        prompt = f"""
You are a senior commercial lawyer and a top-tier legal document intelligence agent.
Analyze the following contract. Your goal is to extract the core clauses, evaluate them against our market-standard baseline, flag risks, and synthesize a high-quality plain-English executive summary.

Here is the baseline market standard for the clauses you must extract:
{baseline_desc}

For each of the target clauses (Indemnity, Limitation of Liability, Governing Law, Termination, IP Ownership, Payment Terms, Confidentiality):
1. Locate the clause in the text.
2. Classify it.
3. Compare it to the market standard. 
4. If a clause contains any "poison pills" (e.g. unlimited liability, uncapped indemnity, non-mutual IP assignments, unreasonable payment penalties, unilateral termination without cause, choice of jurisdiction in an unfavorable region, etc.), give it a High Risk Level, high risk score (80-100), and mark it as Unfavourable or Unusual.
5. Provide a comparison explanation and negotiation recommendation.

If the contract does not contain a specific clause, do not generate a mock clause for it (only extract clauses that are actually present).

Provide a plain-English 1-page executive summary that is comprehensible to non-legal stakeholders.
Calculate an overall risk score (0-100) representing the collective risk of the contract (low is safe, high is high-risk).

Return the output in the strict schema provided.
"""
        
        contents = []
        uploaded_file = None
        if is_scanned and file_bytes:
            # Use Gemini's File API to handle massive PDFs (stress test ready)
            import tempfile
            import os
            import time
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
                
            try:
                # Upload the document to Google's servers for processing (supports up to 2GB files)
                uploaded_file = genai.upload_file(path=tmp_path, mime_type="application/pdf")
                
                # Wait for the file to be processed
                while True:
                    file_info = genai.get_file(uploaded_file.name)
                    if file_info.state.name == "ACTIVE":
                        break
                    elif file_info.state.name == "FAILED":
                        raise ValueError("Gemini failed to process the document.")
                    time.sleep(2)
                
                contents.append(uploaded_file)
                contents.append(prompt)
            finally:
                os.remove(tmp_path)
        else:
            # Use extracted text
            contents.append(f"{prompt}\n\n--- CONTRACT TEXT ---\n{full_text}")

        try:
            # Request structured JSON matching our Pydantic schema
            response = model.generate_content(
                contents,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=ContractAnalysisResult,
                    temperature=0.1
                )
            )
            
            # Parse output
            resp_text = response.text.strip()
            if resp_text.startswith("```json"):
                resp_text = resp_text[7:]
            elif resp_text.startswith("```"):
                resp_text = resp_text[3:]
            if resp_text.endswith("```"):
                resp_text = resp_text[:-3]
            return ContractAnalysisResult.parse_raw(resp_text.strip())
        finally:
            if uploaded_file:
                try:
                    genai.delete_file(uploaded_file.name)
                except Exception:
                    pass

    def compare_clauses_batch(self, contracts_data: List[Dict[str, Any]], clause_type: str) -> Dict[str, Any]:
        """
        Compares the same clause type across multiple contracts side-by-side.
        """
        model = self._get_model()
        baseline_data = settings.load_baseline()
        
        # Normalize key
        clause_key = clause_type.lower().replace(" ", "_")
        baseline_info = baseline_data.get(clause_key, {
            "title": clause_type,
            "standardText": "No standard baseline defined."
        })

        prompt = f"""
You are a senior due-diligence lawyer.
Compare the '{clause_type}' clause across the following {len(contracts_data)} contracts.
Our market standard baseline for this clause is:
"{baseline_info.get('standardText')}"

Here is the data for each contract (including filename and the extracted text/content related to this clause):
"""
        for idx, contract in enumerate(contracts_data):
            prompt += f"\n--- CONTRACT #{idx+1}: {contract['filename']} ---\n{contract.get('clause_text', 'Clause not found / not present.')}\n"

        prompt += f"""
Perform a deep comparative analysis. Provide your response as a JSON object matching this structure:
{{
  "clause_type": "{clause_type}",
  "baseline_standard": "{baseline_info.get('standardText')}",
  "comparisons": [
    {{
      "filename": "contract_filename.pdf",
      "clause_text": "verbatim text or 'Not Found'",
      "risk_level": "Low/Medium/High",
      "risk_score": 45,
      "deviation": "Favourable/Unfavourable/Unusual/Standard",
      "summary_analysis": "Brief analysis of this contract's clause."
    }}
  ],
  "due_diligence_summary": "Overall synthesis comparing all contracts. Rank them from most favorable to least favorable, highlighting critical deviations and advising on M&A/due-diligence impact."
}}
"""
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.2
            )
        )
        
        return json.loads(response.text)

gemini_client = GeminiClient()
