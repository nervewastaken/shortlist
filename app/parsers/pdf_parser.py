"""
PDF parser for extracting names, registration numbers, and emails from PDF attachments.
"""

import re
import io
from typing import List, Dict, Any, Optional

# Try to import PyPDF2, fallback gracefully if not available
try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    PyPDF2 = None

# VIT reg-no pattern, e.g., 22BCE2382
REG_RE = re.compile(r"\b\d{2}[A-Z]{3}\d{4}\b", re.IGNORECASE)

# Email pattern
EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')

# Name patterns - look for lines that might contain names
NAME_PATTERNS = [
    re.compile(r'(?:name|student|candidate|applicant)[\s:]+([A-Za-z\s]+)', re.IGNORECASE),
    re.compile(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', re.MULTILINE),  # Capitalized names
    re.compile(r'([A-Za-z]+\s+[A-Za-z]+(?:\s+[A-Za-z]+)?)\s+\d{2}[A-Z]{3}\d{4}', re.IGNORECASE)  # Name before reg number
]

def extract_text_from_pdf(pdf_data: bytes) -> str:
    """
    Extract text content from PDF data.
    """
    if not PYPDF2_AVAILABLE:
        return "PyPDF2 not available. Install with: pip install PyPDF2"
    
    try:
        pdf_file = io.BytesIO(pdf_data)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        text = ""
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text += page.extract_text() + "\n"
        
        return text
    
    except Exception as e:
        return f"Error extracting PDF text: {str(e)}"

def extract_reg_numbers_from_text(text: str) -> List[str]:
    """Extract registration numbers from text."""
    if not text:
        return []
    return [match.group(0).upper() for match in REG_RE.finditer(text)]

def extract_emails_from_text(text: str) -> List[str]:
    """Extract email addresses from text."""
    if not text:
        return []
    return [match.group(0).lower() for match in EMAIL_RE.finditer(text)]

def extract_names_from_text(text: str) -> List[str]:
    """Extract potential names from text using various patterns."""
    if not text:
        return []
    
    names = set()
    
    for pattern in NAME_PATTERNS:
        matches = pattern.findall(text)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0] if match else ""
            
            # Clean the name
            cleaned_name = re.sub(r'\s+', ' ', match.strip())
            cleaned_name = re.sub(r'[^\w\s]', ' ', cleaned_name)
            cleaned_name = ' '.join(word.capitalize() for word in cleaned_name.split() if word.isalpha())
            
            # Filter valid names (2-4 words, each word 2+ chars)
            words = cleaned_name.split()
            if 2 <= len(words) <= 4 and all(len(word) >= 2 for word in words):
                names.add(cleaned_name)
    
    return list(names)

def check_name_match(profile_name: str, extracted_name: str) -> bool:
    """Check if extracted name matches profile name."""
    if not profile_name or not extracted_name:
        return False
    
    profile_words = set(profile_name.lower().split())
    extracted_words = set(extracted_name.lower().split())
    
    # Check if all profile words are in extracted name or vice versa
    return (profile_words.issubset(extracted_words) or 
            extracted_words.issubset(profile_words))

def evaluate_text_match(text: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate if text content matches the user's profile.
    """
    # Extract all information from text
    extracted_regs = extract_reg_numbers_from_text(text)
    extracted_emails = extract_emails_from_text(text)
    extracted_names = extract_names_from_text(text)
    
    profile_name = profile.get("name", "")
    profile_reg = profile.get("registration_number", "")
    profile_gmail = profile.get("gmail_address", "")
    profile_personal = profile.get("personal_email", "")
    
    # Check matches
    name_matches = []
    for name in extracted_names:
        if check_name_match(profile_name, name):
            name_matches.append(name)
    
    reg_match = profile_reg.upper() in [reg.upper() for reg in extracted_regs] if profile_reg else False
    
    email_matches = []
    for email in extracted_emails:
        if email.lower() in [profile_gmail.lower(), profile_personal.lower()]:
            email_matches.append(email)
    
    # Determine match type
    match_type = "NO_MATCH"
    if name_matches and (reg_match or email_matches):
        match_type = "CONFIRMED_MATCH"
    elif name_matches:
        match_type = "POSSIBILITY"
    elif reg_match or email_matches:
        match_type = "PARTIAL_MATCH"
    
    return {
        "match_type": match_type,
        "extracted_names": extracted_names,
        "extracted_regs": extracted_regs,
        "extracted_emails": extracted_emails,
        "matching_names": name_matches,
        "matching_reg": reg_match,
        "matching_emails": email_matches,
        "text_preview": text[:500] + "..." if len(text) > 500 else text
    }

def parse_pdf_content(pdf_data: bytes, profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse PDF content and return analysis.
    """
    if not PYPDF2_AVAILABLE:
        return {
            "error": "PyPDF2 not installed. Install with: pip install PyPDF2",
            "match_type": "ERROR"
        }
    
    try:
        # Extract text from PDF
        text = extract_text_from_pdf(pdf_data)
        
        if text.startswith("Error"):
            return {"error": text, "match_type": "ERROR"}
        
        # Evaluate matches
        results = evaluate_text_match(text, profile)
        results["pdf_text_length"] = len(text)
        results["extraction_success"] = True
        
        return results
        
    except Exception as e:
        return {
            "error": f"Failed to parse PDF: {str(e)}",
            "match_type": "ERROR"
        }

def parse_attachment(attachment_data: bytes, filename: str, mime_type: str, profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parse PDF attachment and return analysis.
    
    Args:
        attachment_data: Raw attachment data
        filename: Name of the attachment
        mime_type: MIME type of the attachment
        profile: User profile for matching
    
    Returns:
        Dictionary with parsing results or None if file type not supported
    """
    filename_lower = filename.lower()
    
    # Check if it's a PDF file
    if filename_lower.endswith('.pdf') or 'pdf' in mime_type.lower():
        return parse_pdf_content(attachment_data, profile)
    
    return None  # Unsupported file type

if __name__ == "__main__":
    # Test with sample text
    sample_profile = {
        "name": "Krish Verma",
        "registration_number": "22BCE2382",
        "gmail_address": "krish.verma2022@vitstudent.ac.in",
        "personal_email": "krishverma2004@gmail.com"
    }
    
    sample_text = """
    Student Information Sheet
    
    Name: Krish Verma
    Registration Number: 22BCE2382
    Email: krish.verma2022@vitstudent.ac.in
    Department: Computer Science and Engineering
    
    Other students:
    John Doe - 21CSE1234
    Jane Smith - 22ECE5678 - jane.smith@vitstudent.ac.in
    """
    
    results = evaluate_text_match(sample_text, sample_profile)
    print("PDF text parsing results:")
    print(f"Match type: {results['match_type']}")
    print(f"Extracted names: {results['extracted_names']}")
    print(f"Extracted regs: {results['extracted_regs']}")
    print(f"Extracted emails: {results['extracted_emails']}")
    print(f"Matching names: {results['matching_names']}")
    print(f"Matching reg: {results['matching_reg']}")
    print(f"Matching emails: {results['matching_emails']}")
