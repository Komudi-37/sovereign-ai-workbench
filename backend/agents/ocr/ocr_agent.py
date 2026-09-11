from __future__ import annotations
import os
import pathlib
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    import pytesseract
    from PIL import Image
    HAS_PYTESSERACT = True
except ImportError:
    HAS_PYTESSERACT = False
    logger.warning("pytesseract is not installed. OCR for scanned pages/images will not be available.")

try:
    import pymupdf
except ImportError:
    logger.error("pymupdf is not installed. PDF extraction will fail.")
    pymupdf = None

class OCRAgent:
    def __init__(self, output_dir: str = "outputs/ocr"):
        self.output_dir = pathlib.Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def process_file(self, file_path: str) -> Dict[str, Any]:
        path = pathlib.Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}"}
        
        ext = path.suffix.lower()
        if ext == ".pdf":
            return self._process_pdf(path)
        elif ext in [".png", ".jpg", ".jpeg", ".tiff"]:
            return self._process_image(path)
        elif ext in [".txt", ".md", ".log"]:
            text = path.read_text(encoding="utf-8", errors="ignore")
            return {
                "text": text,
                "pages": [{"page_number": 1, "text": text, "confidence": 1.0}],
                "tables": [],
                "document_metadata": {"filename": path.name, "size": path.stat().st_size}
            }
        else:
            return {"error": f"Unsupported file type: {ext}"}
            
    def _process_pdf(self, path: pathlib.Path) -> Dict[str, Any]:
        if not pymupdf:
            return {"error": "pymupdf is not installed."}
        
        pages = []
        full_text = []
        warnings = []
        
        try:
            doc = pymupdf.open(str(path))
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                
                # If little text, try OCR
                if len(text.strip()) < 50:
                    if HAS_PYTESSERACT:
                        try:
                            pix = page.get_pixmap()
                            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                            ocr_text = pytesseract.image_to_string(img)
                            if ocr_text:
                                text = ocr_text
                        except Exception as e:
                            warnings.append(f"OCR failed on page {page_num}: {e}")
                    else:
                        warnings.append(f"Little text on page {page_num} but pytesseract not available.")
                
                pages.append({
                    "page_number": page_num + 1,
                    "text": text,
                    "confidence": 1.0 # default confidence
                })
                full_text.append(text)
            
            doc.close()
            return {
                "text": "\n".join(full_text),
                "pages": pages,
                "warnings": warnings,
                "metadata": {"pages": len(pages)}
            }
        except Exception as e:
            return {"error": f"Error processing PDF: {e}"}

    def _process_image(self, path: pathlib.Path) -> Dict[str, Any]:
        if not HAS_PYTESSERACT:
            return {"error": "pytesseract not available for image processing."}
        
        try:
            img = Image.open(str(path))
            text = pytesseract.image_to_string(img)
            return {
                "text": text,
                "pages": [{"page_number": 1, "text": text, "confidence": 1.0}],
                "warnings": [],
                "metadata": {"format": img.format, "size": img.size}
            }
        except Exception as e:
            return {"error": f"Error processing image: {e}"}

def ocr_adapter(context):
    try:
        from agents.orchestrator.state import AgentResult
    except ImportError:
        # Fallback if orchestrator not available during standalone testing
        class AgentResult:
            def __init__(self, agent_name, status, summary, data, artifacts, warnings, errors):
                self.agent_name = agent_name
                self.status = status
                self.summary = summary
                self.data = data
                self.artifacts = artifacts
                self.warnings = warnings
                self.errors = errors
                
    files = getattr(context, 'files', [])
    
    agent = OCRAgent()
    all_text = []
    all_pages = []
    all_warnings = []
    all_errors = []
    metadata = {}
    
    if not files:
        all_warnings.append("No files to process")
        
    for file_path in files:
        res = agent.process_file(file_path)
        if "error" in res:
            all_errors.append(res["error"])
        else:
            all_text.append(res.get("text", ""))
            all_pages.extend(res.get("pages", []))
            if res.get("warnings"):
                all_warnings.extend(res["warnings"])
            
            try:
                base_name = pathlib.Path(file_path).stem
                out_file = agent.output_dir / f"{base_name}_ocr.txt"
                with open(out_file, "w", encoding="utf-8") as f:
                    f.write(res.get("text", ""))
                metadata[file_path] = res.get("metadata", {})
            except Exception as e:
                all_warnings.append(f"Failed to save output for {file_path}: {e}")
                
    full_text = "\n\n".join(all_text)
    
    return AgentResult(
        agent_name="ocr",
        status="failed" if all_errors and not all_text else "completed",
        summary=f"Processed {len(files)} files.",
        data={
            "text": full_text,
            "pages": all_pages,
            "tables": [],
            "document_metadata": metadata
        },
        artifacts=[],
        warnings=all_warnings,
        errors=all_errors
    )
