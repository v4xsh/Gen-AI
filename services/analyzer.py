import re
from typing import Dict, Any, List
from core.parser import extract_document_data
from core.gemini_client import gemini_client, ContractAnalysisResult

def find_clause_position(full_text: str, clause_text: str) -> Dict[str, int]:
    """
    Finds the character offsets of the clause text in the full document text.
    Uses progressive fallbacks (exact, prefix/suffix, normalized whitespace) for matching.
    """
    if not clause_text or not full_text:
        return {"start": -1, "end": -1}
        
    # 1. Try exact match
    start = full_text.find(clause_text)
    if start != -1:
        return {"start": start, "end": start + len(clause_text)}
        
    # 2. Try matching with normalized spaces (common for OCR text mismatches)
    normalized_full = re.sub(r'\s+', ' ', full_text)
    normalized_clause = re.sub(r'\s+', ' ', clause_text)
    
    norm_start = normalized_full.find(normalized_clause)
    if norm_start != -1:
        # Map the normalized start/end back to the original text
        # Since spaces could differ, we can approximate
        clause_len = len(normalized_clause)
        # Find corresponding position in full_text
        match_ratio = len(full_text) / max(len(normalized_full), 1)
        approx_start = int(norm_start * match_ratio)
        approx_end = min(len(full_text), approx_start + len(clause_text))
        return {"start": approx_start, "end": approx_end}
        
    # 3. Try matching based on a smaller subset (first 40 characters and last 40 characters)
    if len(clause_text) > 80:
        prefix = clause_text[:45].strip()
        suffix = clause_text[-45:].strip()
        
        # Strip punctuation for fuzzy match
        prefix_clean = re.escape(re.sub(r'[^\w\s]', '', prefix))
        suffix_clean = re.escape(re.sub(r'[^\w\s]', '', suffix))
        
        try:
            pref_match = re.search(prefix_clean, full_text, re.IGNORECASE)
            suff_match = re.search(suffix_clean, full_text, re.IGNORECASE)
            
            if pref_match and suff_match:
                start = pref_match.start()
                end = suff_match.end()
                if start < end:
                    return {"start": start, "end": end}
        except Exception:
            pass
            
    return {"start": -1, "end": -1}

class ContractAnalyzerService:
    def analyze_document(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Coordinates document parsing, calls Gemini API to extract and score clauses,
        maps clause locations, and constructs a detailed analysis payload.
        """
        # Parse document
        doc_data = extract_document_data(file_bytes, filename)
        
        # Get analysis from Gemini
        analysis: ContractAnalysisResult = gemini_client.analyze_contract(
            full_text=doc_data["full_text"],
            is_scanned=doc_data["is_scanned"],
            file_bytes=file_bytes if doc_data["is_scanned"] else None
        )
        
        # Convert analysis to dict for serialization
        result_dict = analysis.dict()
        
        # Map character offsets of extracted clauses in full text
        for clause in result_dict["clauses"]:
            pos = find_clause_position(doc_data["full_text"], clause["clause_text"])
            clause["position"] = pos
            
        result_dict["filename"] = doc_data["filename"]
        result_dict["is_scanned"] = doc_data["is_scanned"]
        result_dict["full_text"] = doc_data["full_text"]
        result_dict["elements"] = doc_data["elements"]
        result_dict["hierarchy"] = doc_data["hierarchy"]
        
        # Aggregate Risk Counts
        risk_counts = {"Low": 0, "Medium": 0, "High": 0}
        category_risks = {"Financial": 0, "Operational": 0, "Legal": 0, "Reputational": 0}
        
        for clause in result_dict["clauses"]:
            risk_level = clause["risk_level"]
            risk_counts[risk_level] = risk_counts.get(risk_level, 0) + 1
            
            category = clause["risk_category"]
            if category in category_risks:
                category_risks[category] = max(category_risks[category], clause["risk_score"])
                
        result_dict["risk_counts"] = risk_counts
        result_dict["category_risks"] = category_risks
        
        return result_dict

analyzer_service = ContractAnalyzerService()
