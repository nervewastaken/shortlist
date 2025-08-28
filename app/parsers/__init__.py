"""
Parser initialization module.
Connects document and PDF parsers with the main runner.
"""

from typing import Dict, Any, List, Optional, Protocol
import base64

class AttachmentParser(Protocol):
    """
    Interface for file parsers.
    Implementations should accept either bytes or a file path and return a dict.
    """
    def __call__(self, data: bytes | str, *, filename: str | None = None) -> Dict[str, Any]: ...

# Import parsers
from .doc_parser import parse_attachment as parse_doc_attachment
from .pdf_parser import parse_attachment as parse_pdf_attachment

def get_email_attachments(service, message_id: str) -> List[Dict[str, Any]]:
    """
    Extract attachments from an email message.
    """
    try:
        message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        attachments = []
        
        def extract_attachments_from_payload(payload, part_id=""):
            """Recursively extract attachments from message payload."""
            
            # Check if this part has an attachment
            if 'body' in payload and 'attachmentId' in payload['body']:
                filename = payload.get('filename', 'unknown')
                mime_type = payload.get('mimeType', 'application/octet-stream')
                attachment_id = payload['body']['attachmentId']
                
                # Get attachment data
                attachment = service.users().messages().attachments().get(
                    userId="me", 
                    messageId=message_id, 
                    id=attachment_id
                ).execute()
                
                attachment_data = base64.urlsafe_b64decode(attachment['data'])
                
                attachments.append({
                    'filename': filename,
                    'mime_type': mime_type,
                    'size': len(attachment_data),
                    'data': attachment_data,
                    'attachment_id': attachment_id
                })
            
            # Recursively check parts
            if 'parts' in payload:
                for i, part in enumerate(payload['parts']):
                    extract_attachments_from_payload(part, f"{part_id}.{i}" if part_id else str(i))
        
        # Start extraction from message payload
        payload = message.get('payload', {})
        extract_attachments_from_payload(payload)
        
        return attachments
        
    except Exception as e:
        print(f"Error extracting attachments: {e}")
        return []

def parse_email_attachments(service, message_id: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse all attachments in an email for relevant information.
    
    Returns:
        Dictionary containing parsing results for all attachments
    """
    results = {
        'total_attachments': 0,
        'parsed_attachments': 0,
        'parsing_results': [],
        'overall_match_type': 'NO_MATCH',
        'summary': {
            'confirmed_matches': 0,
            'possibilities': 0,
            'partial_matches': 0,
            'errors': 0
        }
    }
    
    try:
        # Get all attachments
        attachments = get_email_attachments(service, message_id)
        results['total_attachments'] = len(attachments)
        
        if not attachments:
            return results
        
        # Parse each attachment
        for attachment in attachments:
            filename = attachment['filename']
            mime_type = attachment['mime_type']
            data = attachment['data']
            
            # Try document parser first
            doc_result = parse_doc_attachment(data, filename, mime_type, profile)
            
            # If doc parser can't handle it, try PDF parser
            if doc_result is None:
                pdf_result = parse_pdf_attachment(data, filename, mime_type, profile)
                if pdf_result is not None:
                    doc_result = pdf_result
            
            # If we got parsing results
            if doc_result is not None:
                attachment_result = {
                    'filename': filename,
                    'mime_type': mime_type,
                    'size': attachment['size'],
                    'parser_used': 'document' if 'total_rows' in doc_result else 'pdf',
                    'parsing_result': doc_result
                }
                
                results['parsing_results'].append(attachment_result)
                results['parsed_attachments'] += 1
                
                # Update summary based on results
                if 'error' in doc_result:
                    results['summary']['errors'] += 1
                else:
                    match_type = doc_result.get('match_type', 'NO_MATCH')
                    
                    # For document parser results
                    if 'confirmed_matches' in doc_result:
                        results['summary']['confirmed_matches'] += len(doc_result['confirmed_matches'])
                        results['summary']['possibilities'] += len(doc_result['possibilities'])
                        results['summary']['partial_matches'] += len(doc_result['partial_matches'])
                    # For PDF parser results
                    elif match_type in ['CONFIRMED_MATCH', 'POSSIBILITY', 'PARTIAL_MATCH']:
                        if match_type == 'CONFIRMED_MATCH':
                            results['summary']['confirmed_matches'] += 1
                        elif match_type == 'POSSIBILITY':
                            results['summary']['possibilities'] += 1
                        elif match_type == 'PARTIAL_MATCH':
                            results['summary']['partial_matches'] += 1
            else:
                # Unsupported file type
                results['parsing_results'].append({
                    'filename': filename,
                    'mime_type': mime_type,
                    'size': attachment['size'],
                    'parser_used': 'none',
                    'parsing_result': {'error': 'Unsupported file type', 'match_type': 'UNSUPPORTED'}
                })
        
        # Determine overall match type
        if results['summary']['confirmed_matches'] > 0:
            results['overall_match_type'] = 'CONFIRMED_MATCH'
        elif results['summary']['possibilities'] > 0:
            results['overall_match_type'] = 'POSSIBILITY'
        elif results['summary']['partial_matches'] > 0:
            results['overall_match_type'] = 'PARTIAL_MATCH'
        
        return results
        
    except Exception as e:
        results['error'] = f"Error parsing attachments: {str(e)}"
        return results

def generate_consolidated_report(email_matches: List[Dict], attachment_results: Dict) -> Dict[str, Any]:
    """
    Generate a consolidated report combining email content matches and attachment parsing results.
    """
    report = {
        'timestamp': '',
        'email_analysis': {
            'total_emails_analyzed': len(email_matches),
            'confirmed_matches': 0,
            'possibilities': 0,
            'partial_matches': 0
        },
        'attachment_analysis': {
            'total_attachments': attachment_results.get('total_attachments', 0),
            'parsed_attachments': attachment_results.get('parsed_attachments', 0),
            'confirmed_matches': attachment_results.get('summary', {}).get('confirmed_matches', 0),
            'possibilities': attachment_results.get('summary', {}).get('possibilities', 0),
            'partial_matches': attachment_results.get('summary', {}).get('partial_matches', 0)
        },
        'combined_summary': {
            'total_confirmed_matches': 0,
            'total_possibilities': 0,
            'total_partial_matches': 0,
            'overall_status': 'NO_MATCH'
        },
        'detailed_findings': {
            'email_matches': email_matches,
            'attachment_parsing': attachment_results
        }
    }
    
    # Count email matches
    for match in email_matches:
        match_type = match.get('match_type', 'NO_MATCH')
        if match_type == 'CONFIRMED_MATCH':
            report['email_analysis']['confirmed_matches'] += 1
        elif match_type == 'POSSIBILITY':
            report['email_analysis']['possibilities'] += 1
        elif match_type == 'PARTIAL_MATCH':
            report['email_analysis']['partial_matches'] += 1
    
    # Calculate combined totals
    report['combined_summary']['total_confirmed_matches'] = (
        report['email_analysis']['confirmed_matches'] + 
        report['attachment_analysis']['confirmed_matches']
    )
    report['combined_summary']['total_possibilities'] = (
        report['email_analysis']['possibilities'] + 
        report['attachment_analysis']['possibilities']
    )
    report['combined_summary']['total_partial_matches'] = (
        report['email_analysis']['partial_matches'] + 
        report['attachment_analysis']['partial_matches']
    )
    
    # Determine overall status
    if report['combined_summary']['total_confirmed_matches'] > 0:
        report['combined_summary']['overall_status'] = 'CONFIRMED_MATCH'
    elif report['combined_summary']['total_possibilities'] > 0:
        report['combined_summary']['overall_status'] = 'POSSIBILITY'
    elif report['combined_summary']['total_partial_matches'] > 0:
        report['combined_summary']['overall_status'] = 'PARTIAL_MATCH'
    
    return report

# Export the main functions
__all__ = [
    "AttachmentParser", 
    'parse_email_attachments',
    'generate_consolidated_report',
    'get_email_attachments'
]
