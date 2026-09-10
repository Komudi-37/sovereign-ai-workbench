import argparse
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import warnings

import fitz
from PIL import Image, ImageOps

from .vision_model import (
    SourceReference,
    VisionBatchResult,
    VisionModel,
    VisionModelConfig,
)


@dataclass(frozen=True)
class ImageAnalyzerConfig:
    pdf_dpi: int = 200
    max_file_bytes: int = 100 * 1024 * 1024
    max_decoded_image_pixels: int = 40_000_000
    max_render_pixels: int = 12_000_000
    max_image_side: int = 2400
    max_visuals: int = 12
    max_reference_characters: int = 8000


@dataclass(frozen=True)
class PreparedVisual:
    source: SourceReference
    image_bytes: bytes


class ImageAnalyzer:
    IMAGE_EXTENSIONS = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
        ".tif",
        ".tiff",
    }

    SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf"}

    def __init__(
        self,
        model: VisionModel | None = None,
        config: ImageAnalyzerConfig | None = None,
    ):
        self.config = config or ImageAnalyzerConfig()

        if any(
            value <= 0
            for value in (
                self.config.pdf_dpi,
                self.config.max_file_bytes,
                self.config.max_decoded_image_pixels,
                self.config.max_render_pixels,
                self.config.max_image_side,
                self.config.max_visuals,
                self.config.max_reference_characters,
            )
        ):
            raise ValueError("All resource limits must be positive.")

        self.model = model or VisionModel()

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()

        with path.open("rb") as stream:
            for chunk in iter(
                lambda: stream.read(1024 * 1024),
                b"",
            ):
                digest.update(chunk)

        return digest.hexdigest()

    def _validate_path(self, filename: str | Path) -> Path:
        path = Path(filename).expanduser().resolve()

        if not path.is_file():
            raise FileNotFoundError(path)

        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported vision input: {path.suffix}. "
                f"Supported: {sorted(self.SUPPORTED_EXTENSIONS)}"
            )

        if path.stat().st_size > self.config.max_file_bytes:
            raise ValueError(
                f"{path.name} exceeds max_file_bytes."
            )

        return path

    def _prepare_image(
        self,
        image: Image.Image,
        *,
        path: Path,
        document_hash: str,
        page_number: int | None,
        frame_number: int | None,
        preparation_warnings: list[str] | None = None,
    ) -> PreparedVisual:
        image = ImageOps.exif_transpose(image)

        original_width, original_height = image.size
        output_warnings = list(preparation_warnings or [])

        # Composite transparent drawings onto white rather than turning
        # transparent regions black.
        if (
            image.mode in {"RGBA", "LA"}
            or "transparency" in image.info
        ):
            rgba = image.convert("RGBA")
            background = Image.new(
                "RGBA",
                rgba.size,
                "white",
            )
            image = Image.alpha_composite(
                background,
                rgba,
            ).convert("RGB")
        else:
            image = image.convert("RGB")

        if max(image.size) > self.config.max_image_side:
            image.thumbnail(
                (
                    self.config.max_image_side,
                    self.config.max_image_side,
                ),
                Image.Resampling.LANCZOS,
            )

            output_warnings.append(
                "Image was downscaled. Small labels and fine linework "
                "may require a higher-resolution crop."
            )

        buffer = BytesIO()
        image.save(buffer, format="PNG")

        suffix = (
            f"page-{page_number}"
            if page_number is not None
            else f"frame-{frame_number or 1}"
        )

        source = SourceReference(
            source_id=f"{document_hash}:{suffix}",
            file_name=path.name,
            source_path=str(path),
            page_number=page_number,
            frame_number=frame_number,
            original_width=original_width,
            original_height=original_height,
            analyzed_width=image.width,
            analyzed_height=image.height,
            warnings=output_warnings,
        )

        return PreparedVisual(
            source=source,
            image_bytes=buffer.getvalue(),
        )

    def _prepare_pdf(
        self,
        path: Path,
        document_hash: str,
        selected_pages: list[int] | None,
        remaining_visuals: int,
    ) -> list[PreparedVisual]:
        visuals = []

        with fitz.open(str(path)) as document:
            if document.needs_pass:
                raise ValueError(
                    f"{path.name} is encrypted. Provide an authorized "
                    "decrypted copy before visual analysis."
                )

            if selected_pages is None:
                page_numbers = list(
                    range(1, document.page_count + 1)
                )
            else:
                if not selected_pages:
                    raise ValueError(
                        "PDF page selection cannot be empty."
                    )

                # Remove duplicate selections while preserving order.
                page_numbers = list(dict.fromkeys(selected_pages))

            if any(
                number < 1 or number > document.page_count
                for number in page_numbers
            ):
                raise ValueError(
                    f"Invalid page selection for {path.name}. "
                    f"Valid pages: 1-{document.page_count}."
                )

            if len(page_numbers) > remaining_visuals:
                raise ValueError(
                    f"{path.name} would exceed max_visuals. "
                    "Select fewer PDF pages or increase the limit."
                )

            for page_number in page_numbers:
                page = document[page_number - 1]
                scale = self.config.pdf_dpi / 72.0

                requested_pixels = (
                    page.rect.width
                    * page.rect.height
                    * scale
                    * scale
                )

                page_warnings = [
                    "For PDF inputs, original_width and original_height "
                    "refer to the rendered image, not PDF point units."
                ]

                if requested_pixels > self.config.max_render_pixels:
                    scale *= (
                        self.config.max_render_pixels
                        / requested_pixels
                    ) ** 0.5

                    page_warnings.append(
                        "PDF render resolution was reduced to respect "
                        "max_render_pixels."
                    )

                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(scale, scale),
                    colorspace=fitz.csRGB,
                    alpha=False,
                )

                image = Image.frombytes(
                    "RGB",
                    (pixmap.width, pixmap.height),
                    pixmap.samples,
                )

                visuals.append(
                    self._prepare_image(
                        image,
                        path=path,
                        document_hash=document_hash,
                        page_number=page_number,
                        frame_number=None,
                        preparation_warnings=page_warnings,
                    )
                )

        return visuals

    def _prepare_raster(
        self,
        path: Path,
        document_hash: str,
        remaining_visuals: int,
    ) -> list[PreparedVisual]:
        visuals = []

        with warnings.catch_warnings():
            warnings.simplefilter(
                "error",
                Image.DecompressionBombWarning,
            )

            with Image.open(path) as original:
                frame_count = getattr(original, "n_frames", 1)

                if frame_count > remaining_visuals:
                    raise ValueError(
                        f"{path.name} contains {frame_count} frames "
                        "and would exceed max_visuals."
                    )

                for frame_index in range(frame_count):
                    original.seek(frame_index)

                    if (
                        original.width * original.height
                        > self.config.max_decoded_image_pixels
                    ):
                        raise ValueError(
                            f"{path.name}, frame {frame_index + 1}, "
                            "exceeds max_decoded_image_pixels. "
                            "Crop or resize it before uploading."
                        )

                    # Copy detaches this frame from the source stream.
                    image = original.copy()

                    visuals.append(
                        self._prepare_image(
                            image,
                            path=path,
                            document_hash=document_hash,
                            page_number=None,
                            frame_number=frame_index + 1,
                        )
                    )

        return visuals

    def analyze_files(
        self,
        files: list[str | Path],
        request: str,
        *,
        pdf_pages: list[int] | None = None,
        reference_context: str = "",
    ) -> VisionBatchResult:
        """
        pdf_pages:
            One-based page numbers, applied to each supplied PDF.
            None means all PDF pages, subject to max_visuals.

        Each visual is analyzed separately. Cross-page topology is not
        reconstructed automatically.
        """
        if not files:
            raise ValueError("Provide at least one image or PDF.")

        if not request.strip():
            raise ValueError("The request cannot be empty.")

        paths = [
            self._validate_path(filename)
            for filename in files
        ]

        if pdf_pages is not None and not any(
            path.suffix.lower() == ".pdf" for path in paths
        ):
            raise ValueError(
                "pdf_pages was supplied, but no PDF input was provided."
            )

        prepared = []

        # Validate and prepare all inputs before making paid API calls.
        for path in paths:
            remaining = self.config.max_visuals - len(prepared)
            document_hash = self._file_hash(path)

            if path.suffix.lower() == ".pdf":
                visuals = self._prepare_pdf(
                    path,
                    document_hash,
                    pdf_pages,
                    remaining,
                )
            else:
                visuals = self._prepare_raster(
                    path,
                    document_hash,
                    remaining,
                )

            prepared.extend(visuals)

        if not prepared:
            raise ValueError("No visual pages or frames were found.")

        batch_warnings = [
            "Each image/page was analyzed independently. "
            "Cross-page diagram connections were not verified.",
            "Visual findings require review before engineering or "
            "operational decisions.",
        ]

        if (
            len(reference_context)
            > self.config.max_reference_characters
        ):
            reference_context = reference_context[
                :self.config.max_reference_characters
            ]
            batch_warnings.append(
                "Reference context was truncated to the configured limit."
            )

        results = []

        for visual in prepared:
            # Fail explicitly if a page cannot be analyzed.
            # Do not substitute a fabricated or empty successful result.
            result = self.model.analyze(
                image_bytes=visual.image_bytes,
                source=visual.source,
                request=request,
                reference_context=reference_context,
            )
            results.append(result)

        return VisionBatchResult(
            request=request,
            results=results,
            warnings=batch_warnings,
        )


def vision_adapter(context):
    """
    Adapter for the existing orchestrator's AgentContext / AgentResult.
    """
    from agents.orchestrator.state import AgentResult

    files = [
        filename
        for filename in context.files
        if Path(filename).suffix.lower()
        in ImageAnalyzer.SUPPORTED_EXTENSIONS
    ]

    if not files:
        raise ValueError(
            "The Vision Agent requires an attached image or PDF."
        )

    reference_parts = []
    remaining_characters = 8000

    for task_id, result in context.dependencies.items():
        if remaining_characters <= 0:
            break

        # Bounded reference information; no automatic loading of
        # paths mentioned in upstream text.
        text = json.dumps(
            {
                "task_id": task_id,
                "summary": result.summary,
                "data": result.data,
            },
            ensure_ascii=False,
        )

        excerpt = text[:remaining_characters]
        reference_parts.append(excerpt)
        remaining_characters -= len(excerpt)

    model = VisionModel(
        VisionModelConfig(
            model=os.getenv(
                "VISION_MODEL",
                "gpt-4.1-mini",
            )
        )
    )

    analyzer = ImageAnalyzer(model=model)

    batch = analyzer.analyze_files(
        files=files,
        request=(
            f"User request: {context.user_request}\n\n"
            f"Assigned vision task: {context.task.instruction}"
        ),
        reference_context="\n\n".join(reference_parts),
    )

    return AgentResult(
        summary=(
            f"Analyzed {len(batch.results)} visual page(s)/frame(s). "
            "Returned source-linked findings and uncertainties."
        ),
        data=batch.model_dump(mode="json"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze images, charts, equipment photos, and P&IDs."
    )

    parser.add_argument(
        "--files",
        nargs="+",
        required=True,
    )
    parser.add_argument(
        "--request",
        required=True,
    )
    parser.add_argument(
        "--model",
        default=os.getenv("VISION_MODEL", "gpt-4.1-mini"),
    )
    parser.add_argument(
        "--pdf-pages",
        nargs="+",
        type=int,
        default=None,
        help="One-based page numbers applied to each supplied PDF.",
    )
    parser.add_argument(
        "--max-visuals",
        type=int,
        default=12,
    )
    parser.add_argument(
        "--max-image-side",
        type=int,
        default=2400,
    )
    parser.add_argument(
        "--output",
        default="outputs/vision_analysis.json",
    )

    args = parser.parse_args()

    analyzer = ImageAnalyzer(
        model=VisionModel(
            VisionModelConfig(model=args.model)
        ),
        config=ImageAnalyzerConfig(
            max_visuals=args.max_visuals,
            max_image_side=args.max_image_side,
        ),
    )

    batch = analyzer.analyze_files(
        files=args.files,
        request=args.request,
        pdf_pages=args.pdf_pages,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        batch.model_dump_json(indent=2),
        encoding="utf-8",
    )

    for result in batch.results:
        source = result.source
        location = (
            f"page {source.page_number}"
            if source.page_number is not None
            else f"frame {source.frame_number}"
        )

        print(f"\n{source.file_name} — {location}")
        print(result.analysis.summary)
        print(result.analysis.response_to_request)

        for uncertainty in result.analysis.uncertainties:
            print(f"  Uncertainty: {uncertainty}")

    print(f"\nStructured output: {output.resolve()}")


if __name__ == "__main__":
    main()
