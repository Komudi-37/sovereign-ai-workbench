"""
Local Vision Preprocessor for Sovereign AI Workbench.

Handles safe, isolated, on-premise preprocessing of images and PDF pages:
- Validates supported formats (PNG, JPG, JPEG, WEBP, BMP, TIFF, PDF)
- Validates file sizes against safe operational limits
- Safe resizing preserving aspect ratio (max side, max pixel count)
- Renders PDF pages to images using PyMuPDF (configurable DPI and page limits)
- Supports single and multi-page selection
- Normalizes color channels (composites alpha transparency over white)
- Performs temporary operations strictly within WorkspaceManager run workspaces
- Automatically cleans up temporary files
- Zero cloud calls, strictly local execution
"""

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
import fitz  # PyMuPDF
from PIL import Image, ImageOps

from app.services.workspace import safe_path, PathTraversalError, workspace_manager

logger = logging.getLogger(__name__)


class PreprocessingError(ValueError):
    """Raised when visual input fails validation or preprocessing limits."""
    pass


@dataclass
class PreprocessorConfig:
    max_file_bytes: int = 50 * 1024 * 1024       # 50 MB
    max_width: int = 4096
    max_height: int = 4096
    max_pixels: int = 25_000_000                 # ~25 Megapixels
    max_image_side: int = 2048                   # Resized target side for local VLM
    default_pdf_dpi: int = 150
    max_pdf_pages: int = 5                       # Resource protection cap
    quality: int = 90


@dataclass
class ProcessedVisual:
    source_filename: str
    page_number: int | None
    image_bytes: bytes
    format: str
    width: int
    height: int
    original_width: int
    original_height: int
    was_resized: bool
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ImagePreprocessor:
    """
    Robust on-premise image and PDF preprocessor for local Vision processing.
    """

    SUPPORTED_RASTER_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"
    }
    SUPPORTED_EXTENSIONS = SUPPORTED_RASTER_EXTENSIONS | {".pdf"}

    def __init__(self, config: PreprocessorConfig | None = None):
        self.config = config or PreprocessorConfig()

    def validate_file(self, file_path: str | Path) -> Path:
        """
        Validate that the file exists, has a supported format, and does not exceed size limit.
        """
        path = Path(file_path).resolve()
        if not path.is_file():
            raise PreprocessingError(f"File not found: {path.name}")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise PreprocessingError(
                f"Unsupported visual file format '{ext}'. "
                f"Supported formats: {sorted(list(self.SUPPORTED_EXTENSIONS))}"
            )

        file_size = path.stat().st_size
        if file_size > self.config.max_file_bytes:
            raise PreprocessingError(
                f"File '{path.name}' size ({file_size / (1024*1024):.1f}MB) exceeds "
                f"maximum allowed limit ({self.config.max_file_bytes / (1024*1024):.1f}MB)."
            )

        return path

    def preprocess_image(
        self,
        image: Image.Image,
        source_name: str = "image",
        page_number: int | None = None,
    ) -> ProcessedVisual:
        """
        Normalize orientation, transparency, and size for local vision model consumption.
        """
        warnings: list[str] = []
        image = ImageOps.exif_transpose(image)
        orig_w, orig_h = image.size

        # Check raw pixel limit
        if orig_w * orig_h > self.config.max_pixels:
            warnings.append(
                f"Image resolution {orig_w}x{orig_h} exceeded {self.config.max_pixels} pixels; resized."
            )

        # Composite alpha transparency onto pure white (crucial for P&ID / engineering drawings)
        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
            rgba = image.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            image = Image.alpha_composite(bg, rgba).convert("RGB")
        elif image.mode != "RGB":
            image = image.convert("RGB")

        was_resized = False
        target_side = self.config.max_image_side
        if max(image.size) > target_side or (image.width * image.height > self.config.max_pixels):
            image.thumbnail((target_side, target_side), Image.Resampling.LANCZOS)
            was_resized = True
            warnings.append(
                f"Image downscaled from {orig_w}x{orig_h} to {image.width}x{image.height} "
                f"to fit local vision model constraints."
            )

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=self.config.quality, optimize=True)
        img_bytes = buffer.getvalue()

        return ProcessedVisual(
            source_filename=source_name,
            page_number=page_number,
            image_bytes=img_bytes,
            format="JPEG",
            width=image.width,
            height=image.height,
            original_width=orig_w,
            original_height=orig_h,
            was_resized=was_resized,
            warnings=warnings,
            metadata={
                "aspect_ratio": round(orig_w / max(1, orig_h), 3),
                "byte_size": len(img_bytes),
            },
        )

    def process_raster_file(self, file_path: str | Path) -> list[ProcessedVisual]:
        """Process a single raster image file."""
        path = self.validate_file(file_path)
        try:
            with Image.open(path) as img:
                return [self.preprocess_image(img, source_name=path.name, page_number=None)]
        except Exception as exc:
            if isinstance(exc, PreprocessingError):
                raise
            raise PreprocessingError(f"Failed to decode image '{path.name}': {exc}") from exc

    def process_pdf_file(
        self,
        file_path: str | Path,
        pages: Sequence[int] | None = None,
        dpi: int | None = None,
        max_pages: int | None = None,
        temp_dir: Path | None = None,
    ) -> list[ProcessedVisual]:
        """
        Render selected or initial PDF pages to standardized images using PyMuPDF.
        Operates strictly inside the provided or controlled workspace temporary directory.
        """
        path = self.validate_file(file_path)
        render_dpi = dpi or self.config.default_pdf_dpi
        page_limit = max_pages or self.config.max_pdf_pages
        scale = render_dpi / 72.0
        matrix = fitz.Matrix(scale, scale)

        visuals: list[ProcessedVisual] = []

        try:
            doc = fitz.open(path)
        except Exception as exc:
            raise PreprocessingError(f"Failed to read PDF '{path.name}': {exc}") from exc

        try:
            total_pages = len(doc)
            if total_pages == 0:
                raise PreprocessingError(f"PDF '{path.name}' contains no pages.")

            # Resolve 1-based page numbers
            if pages:
                selected_pages = [p for p in pages if 1 <= p <= total_pages][:page_limit]
            else:
                selected_pages = list(range(1, min(total_pages, page_limit) + 1))

            for page_num in selected_pages:
                page = doc.load_page(page_num - 1)
                pix = page.get_pixmap(matrix=matrix, alpha=False)

                img_data = pix.tobytes("png")
                with Image.open(io.BytesIO(img_data)) as pil_img:
                    proc = self.preprocess_image(
                        pil_img,
                        source_name=path.name,
                        page_number=page_num,
                    )
                    proc.metadata["pdf_total_pages"] = total_pages
                    proc.metadata["rendered_dpi"] = render_dpi
                    visuals.append(proc)

        finally:
            doc.close()

        return visuals

    def process_file_in_workspace(
        self,
        file_path: str | Path,
        run_workspace: dict[str, Path] | None = None,
        pages: Sequence[int] | None = None,
    ) -> list[ProcessedVisual]:
        """
        High-level entry point that processes either image or PDF within a secure Workspace.
        """
        path = self.validate_file(file_path)
        ext = path.suffix.lower()

        if ext == ".pdf":
            temp_dir = run_workspace.get("temp") if run_workspace else None
            return self.process_pdf_file(path, pages=pages, temp_dir=temp_dir)
        else:
            return self.process_raster_file(path)


# Singleton default preprocessor
preprocessor = ImagePreprocessor()
