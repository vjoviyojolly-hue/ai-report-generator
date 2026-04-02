"""
DOCUMENT EXTRACTOR MODULE
Extracts text from PDF and image documents, then uses GPT to extract structured data
"""

import os
import json
from PyPDF2 import PdfReader
import pdfplumber
from PIL import Image
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize OpenAI client (will use OPENAI_API_KEY from environment)
client = None
try:
    api_key = os.getenv('OPENAI_API_KEY')
    if api_key:
        client = OpenAI(api_key=api_key)
except Exception as e:
    print(f"Warning: OpenAI client not initialized: {e}")


def extract_text_from_pdf(file_path):
    """
    Extract text from PDF file

    Args:
        file_path (str): Path to PDF file

    Returns:
        str: Extracted text
    """
    text = ""

    try:
        # Try using pdfplumber first (better for tables and complex layouts)
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"
    except Exception as e:
        print(f"pdfplumber failed, trying PyPDF2: {e}")

        # Fallback to PyPDF2
        try:
            reader = PdfReader(file_path)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"
        except Exception as e2:
            print(f"PyPDF2 also failed: {e2}")
            text = ""

    return text.strip()


def extract_text_from_image(file_path):
    """
    Extract text from image file using OCR
    For MVP, we'll return a placeholder since pytesseract requires additional setup

    Args:
        file_path (str): Path to image file

    Returns:
        str: Extracted text or placeholder
    """
    # For MVP, we'll handle images as best-effort
    # Full OCR would require pytesseract and tesseract-ocr installation
    try:
        img = Image.open(file_path)
        return f"[Image file detected: {os.path.basename(file_path)}. For full OCR support, pytesseract setup required]"
    except Exception as e:
        return f"[Unable to process image: {e}]"


def extract_text_from_document(file_path):
    """
    Extract text from various document types

    Args:
        file_path (str): Path to document

    Returns:
        str: Extracted text
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.pdf':
        return extract_text_from_pdf(file_path)
    elif ext in ['.jpg', '.jpeg', '.png']:
        return extract_text_from_image(file_path)
    elif ext in ['.doc', '.docx']:
        # For Word documents, we could use python-docx
        return "[Word document - extraction not yet implemented]"
    else:
        return "[Unsupported file type]"


def extract_shipping_data_with_gpt(document_texts):
    """
    Use GPT to extract structured shipping data from document texts

    Args:
        document_texts (dict): Dictionary of {document_type: extracted_text}

    Returns:
        dict: Extracted structured data
    """
    if not client:
        return {
            'error': 'OpenAI API not configured. Please set OPENAI_API_KEY environment variable.',
            'extracted': False
        }

    # Combine all document texts
    combined_text = ""
    for doc_type, text in document_texts.items():
        combined_text += f"\n\n=== {doc_type.upper()} ===\n{text}"

    # Create extraction prompt
    prompt = f"""You are a marine surveyor assistant tasked with extracting shipping information from documents.

Extract the following information from the provided shipping documents:

REQUIRED FIELDS:
- case_reference: Generate a case reference in format ISA/YYYY/COUNTRY/XXXX if not found
- container_number: Container number (e.g., TCLU4567890)
- bl_number: Bill of Lading number
- goods_description: Description of goods/cargo
- shipper: Shipper company name and country
- consignee: Consignee company name and country

DOCUMENT TEXT:
{combined_text[:8000]}

Return ONLY a valid JSON object with the extracted data. Use "N/A" for fields you cannot find.
Example format:
{{
  "case_reference": "ISA/2024/CHN/0001",
  "container_number": "TCLU1234567",
  "bl_number": "MEDU123456789",
  "goods_description": "Electronic Equipment",
  "shipper": "ABC Trading Co., China",
  "consignee": "XYZ Distribution Ltd., South Africa"
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a precise data extraction assistant. Extract shipping document data and return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=500
        )

        # Extract JSON from response
        content = response.choices[0].message.content.strip()

        # Try to parse as JSON
        try:
            data = json.loads(content)
            data['extracted'] = True
            return data
        except json.JSONDecodeError:
            # If not valid JSON, try to extract JSON from markdown code blocks
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
                data = json.loads(json_str)
                data['extracted'] = True
                return data
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
                data = json.loads(json_str)
                data['extracted'] = True
                return data
            else:
                raise

    except Exception as e:
        return {
            'error': f'GPT extraction failed: {str(e)}',
            'extracted': False
        }


def process_uploaded_documents(upload_folder, document_files):
    """
    Process all uploaded documents and extract data

    Args:
        upload_folder (str): Path to upload folder
        document_files (dict): Dictionary of {document_type: filename}

    Returns:
        dict: Extracted data
    """
    # Extract text from all documents
    document_texts = {}

    for doc_type, filename in document_files.items():
        if filename:
            file_path = os.path.join(upload_folder, f"{doc_type}_{filename}")
            if os.path.exists(file_path):
                text = extract_text_from_document(file_path)
                if text and not text.startswith("["):
                    document_texts[doc_type] = text

    # If we have extracted text, use GPT to extract structured data
    if document_texts:
        return extract_shipping_data_with_gpt(document_texts)
    else:
        return {
            'error': 'No text could be extracted from uploaded documents',
            'extracted': False
        }
