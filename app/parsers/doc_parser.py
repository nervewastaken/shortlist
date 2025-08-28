"""
Document parser for Excel and CSV files.
Extracts names, registration numbers, emails, and other relevant information.
"""

import pandas as pd
import re
import io
import base64
from typing import List, Dict, Any, Optional
from pathlib import Path

# VIT reg-no pattern, e.g., 22BCE2382
REG_RE = re.compile(r"\b\d{2}[A-Z]{3}\d{4}\b", re.IGNORECASE)

# Email pattern
EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')

# Name pattern - look for sequences of 2-4 capitalized words
NAME_PATTERN = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b')

def is_likely_name(text: str) -> bool:
    """Check if text looks like a person's name."""
    if not text or pd.isna(text) or len(str(text).strip()) < 3:
        return False
    
    text = str(text).strip()
    
    # Skip if it's mostly numbers or contains common non-name patterns
    if re.search(r'^\d+$|@|\.com|\.org|http|www|\d{10,}', text, re.IGNORECASE):
        return False
    
    # Check if it matches name pattern (2-4 words, each starting with capital)
    words = text.split()
    if 2 <= len(words) <= 4:
        return all(len(word) >= 2 and word[0].isupper() and word[1:].islower() 
                  for word in words if word.isalpha())
    
    return False

def extract_reg_numbers_from_text(text: str) -> List[str]:
    """Extract registration numbers from any text."""
    if not text or pd.isna(text):
        return []
    return [match.group(0).upper() for match in REG_RE.finditer(str(text))]

def extract_emails_from_text(text: str) -> List[str]:
    """Extract email addresses from any text."""
    if not text or pd.isna(text):
        return []
    return [match.group(0).lower() for match in EMAIL_RE.finditer(str(text))]

def scan_dataframe_for_values(df: pd.DataFrame, profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scan entire DataFrame for names, registration numbers, and emails without assuming column names.
    """
    results = {
        'total_rows': len(df),
        'confirmed_matches': [],
        'possibilities': [],
        'partial_matches': [],
        'all_names': set(),
        'all_regs': set(),
        'all_emails': set(),
        'scan_summary': {
            'cells_scanned': 0,
            'names_found': 0,
            'regs_found': 0,
            'emails_found': 0
        }
    }
    
    profile_name = profile.get("name", "").lower().strip()
    profile_reg = profile.get("registration_number", "").upper().strip()
    profile_gmail = profile.get("gmail_address", "").lower().strip()
    profile_personal = profile.get("personal_email", "").lower().strip()
    
    # Process each row
    for row_idx, row in df.iterrows():
        row_data = {
            'row_index': row_idx,
            'raw_data': {},
            'extracted_names': [],
            'extracted_regs': [],
            'extracted_emails': [],
            'matching_cells': []
        }
        
        # Scan every cell in the row
        for col_idx, (col_name, cell_value) in enumerate(row.items()):
            if pd.notna(cell_value):
                text = str(cell_value).strip()
                row_data['raw_data'][col_name] = text
                results['scan_summary']['cells_scanned'] += 1
                
                # Extract registration numbers from this cell
                regs = extract_reg_numbers_from_text(text)
                if regs:
                    row_data['extracted_regs'].extend(regs)
                    results['all_regs'].update(regs)
                    results['scan_summary']['regs_found'] += len(regs)
                    
                    # Check if any match profile
                    if profile_reg and profile_reg in [r.upper() for r in regs]:
                        row_data['matching_cells'].append({
                            'column': col_name,
                            'type': 'registration',
                            'value': text,
                            'match': profile_reg
                        })
                
                # Extract emails from this cell
                emails = extract_emails_from_text(text)
                if emails:
                    row_data['extracted_emails'].extend(emails)
                    results['all_emails'].update(emails)
                    results['scan_summary']['emails_found'] += len(emails)
                    
                    # Check if any match profile
                    for email in emails:
                        if email in [profile_gmail, profile_personal]:
                            row_data['matching_cells'].append({
                                'column': col_name,
                                'type': 'email',
                                'value': text,
                                'match': email
                            })
                
                # Check if this cell contains a name-like value
                if is_likely_name(text):
                    row_data['extracted_names'].append(text)
                    results['all_names'].add(text.lower())
                    results['scan_summary']['names_found'] += 1
                    
                    # Check if it matches profile name
                    if check_name_match(profile_name, text):
                        row_data['matching_cells'].append({
                            'column': col_name,
                            'type': 'name',
                            'value': text,
                            'match': profile_name
                        })
        
        # Evaluate match for this row
        match_type = evaluate_row_match_flexible(row_data, profile_name, profile_reg, profile_gmail, profile_personal)
        
        if match_type == "CONFIRMED_MATCH":
            results['confirmed_matches'].append(row_data)
        elif match_type == "POSSIBILITY":
            results['possibilities'].append(row_data)
        elif match_type == "PARTIAL_MATCH":
            results['partial_matches'].append(row_data)
    
    # Convert sets to lists for JSON serialization
    results['all_names'] = list(results['all_names'])
    results['all_regs'] = list(results['all_regs'])
    results['all_emails'] = list(results['all_emails'])
    
    return results

def check_name_match(profile_name: str, extracted_name: str) -> bool:
    """Check if extracted name matches profile name."""
    if not profile_name or not extracted_name:
        return False
    
    profile_words = set(profile_name.lower().split())
    extracted_words = set(extracted_name.lower().split())
    
    # Check if all profile words are in extracted name or vice versa (flexible matching)
    return (profile_words.issubset(extracted_words) or 
            extracted_words.issubset(profile_words) or
            len(profile_words.intersection(extracted_words)) >= len(profile_words) * 0.8)

def evaluate_row_match_flexible(row_data: Dict, profile_name: str, profile_reg: str, profile_gmail: str, profile_personal: str) -> str:
    """
    Evaluate if a row matches the user's profile using flexible matching.
    """
    name_match = False
    reg_match = False
    email_match = False
    
    # Check matching cells found during scanning
    for cell in row_data['matching_cells']:
        if cell['type'] == 'name':
            name_match = True
        elif cell['type'] == 'registration':
            reg_match = True
        elif cell['type'] == 'email':
            email_match = True
    
    # Apply matching logic
    if name_match and (reg_match or email_match):
        return "CONFIRMED_MATCH"
    elif name_match:
        return "POSSIBILITY"
    elif reg_match or email_match:
        return "PARTIAL_MATCH"
    else:
        return "NO_MATCH"

def parse_csv_content(content: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """Parse CSV content and return analysis."""
    try:
        df = pd.read_csv(io.StringIO(content))
        return scan_dataframe_for_values(df, profile)
    except Exception as e:
        return {"error": f"Failed to parse CSV: {str(e)}"}

def parse_excel_content(content: bytes, profile: Dict[str, Any]) -> Dict[str, Any]:
    """Parse Excel content and return analysis."""
    try:
        # Try to read Excel file
        excel_file = io.BytesIO(content)
        
        # Read all sheets
        all_sheets = pd.read_excel(excel_file, sheet_name=None)
        
        combined_results = {
            'total_rows': 0,
            'confirmed_matches': [],
            'possibilities': [],
            'partial_matches': [],
            'all_names': set(),
            'all_regs': set(),
            'all_emails': set(),
            'sheets_analyzed': list(all_sheets.keys()),
            'scan_summary': {
                'cells_scanned': 0,
                'names_found': 0,
                'regs_found': 0,
                'emails_found': 0
            }
        }
        
        # Parse each sheet
        for sheet_name, df in all_sheets.items():
            sheet_results = scan_dataframe_for_values(df, profile)
            
            # Combine results
            combined_results['total_rows'] += sheet_results['total_rows']
            combined_results['confirmed_matches'].extend(sheet_results['confirmed_matches'])
            combined_results['possibilities'].extend(sheet_results['possibilities'])
            combined_results['partial_matches'].extend(sheet_results['partial_matches'])
            combined_results['all_names'].update(sheet_results['all_names'])
            combined_results['all_regs'].update(sheet_results['all_regs'])
            combined_results['all_emails'].update(sheet_results['all_emails'])
            
            # Combine scan summaries
            for key in combined_results['scan_summary']:
                combined_results['scan_summary'][key] += sheet_results['scan_summary'][key]
        
        # Convert sets back to lists for JSON serialization
        combined_results['all_names'] = list(combined_results['all_names'])
        combined_results['all_regs'] = list(combined_results['all_regs'])
        combined_results['all_emails'] = list(combined_results['all_emails'])
        
        return combined_results
        
    except Exception as e:
        return {"error": f"Failed to parse Excel: {str(e)}"}

def parse_attachment(attachment_data: bytes, filename: str, mime_type: str, profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parse document attachment and return analysis.
    
    Args:
        attachment_data: Raw attachment data
        filename: Name of the attachment
        mime_type: MIME type of the attachment
        profile: User profile for matching
    
    Returns:
        Dictionary with parsing results or None if file type not supported
    """
    filename_lower = filename.lower()
    
    # Determine file type and parse accordingly
    if filename_lower.endswith('.csv') or 'csv' in mime_type:
        try:
            content = attachment_data.decode('utf-8')
            return parse_csv_content(content, profile)
        except UnicodeDecodeError:
            return {"error": "Failed to decode CSV file"}
    
    elif (filename_lower.endswith(('.xlsx', '.xls')) or 
          'spreadsheet' in mime_type or 
          'excel' in mime_type):
        return parse_excel_content(attachment_data, profile)
    
    else:
        return None  # Unsupported file type

if __name__ == "__main__":
    # Test with sample data
    sample_profile = {
        "name": "Krish Verma",
        "registration_number": "22BCE2382",
        "gmail_address": "krish.verma2022@vitstudent.ac.in",
        "personal_email": "krishverma2004@gmail.com"
    }
    
    # Test CSV parsing with flexible scanning
    sample_csv = """Student_Name,Reg_Number,Contact_Email,Department,Random_Data
Krish Verma,22BCE2382,krish.verma2022@vitstudent.ac.in,Computer Science,Some data
John Doe,21CSE1234,john.doe@vitstudent.ac.in,Computer Science,Other data
Jane Smith,22ECE5678,jane.smith@vitstudent.ac.in,Electronics,More data
Krish Verma Student,22BCE2382,different@email.com,CS,Mixed data"""
    
    results = parse_csv_content(sample_csv, sample_profile)
    print("CSV parsing results (flexible scanning):")
    print(f"Confirmed matches: {len(results.get('confirmed_matches', []))}")
    print(f"Possibilities: {len(results.get('possibilities', []))}")
    print(f"Partial matches: {len(results.get('partial_matches', []))}")
    print(f"Scan summary: {results.get('scan_summary', {})}")
    print(f"All names found: {results.get('all_names', [])}")
    print(f"All regs found: {results.get('all_regs', [])}")
    print(f"All emails found: {results.get('all_emails', [])}")
    
    # Show detailed match information
    for i, match in enumerate(results.get('confirmed_matches', [])):
        print(f"\nConfirmed Match {i+1}:")
        print(f"  Row: {match['row_index']}")
        print(f"  Matching cells: {match['matching_cells']}")
        print(f"  Raw data: {match['raw_data']}")
