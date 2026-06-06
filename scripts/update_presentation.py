import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from convert_presentation import (
    DEFAULT_METADATA,
    DEFAULT_OUTPUT,
    PROJECT_ROOT,
    convert_presentation,
)


DEFAULT_PPTX = PROJECT_ROOT / "presentation" / "SCU_RAG_Business_Analysis.pptx"
DEFAULT_PDF = PROJECT_ROOT / "frontend" / "public" / "SCU_RAG_Business_Analysis.pdf"


def refresh_pdf(pptx: Path, pdf: Path) -> bool:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return False

    with tempfile.TemporaryDirectory(prefix="scu-rag-presentation-") as temp_dir:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", temp_dir, str(pptx)],
            check=True,
        )
        converted = Path(temp_dir) / f"{pptx.stem}.pdf"
        if not converted.exists():
            raise RuntimeError("LibreOffice completed without producing the expected PDF.")
        pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(converted, pdf)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh the embedded presentation PDF, WebP slides, and manifest."
    )
    parser.add_argument("--pptx", type=Path, default=DEFAULT_PPTX)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--quality", type=int, default=82)
    parser.add_argument(
        "--skip-pdf-refresh",
        action="store_true",
        help="Use the existing PDF even when LibreOffice is installed.",
    )
    args = parser.parse_args()

    if not args.pptx.exists():
        raise FileNotFoundError(f"Presentation source not found: {args.pptx}")

    refreshed = False
    if not args.skip_pdf_refresh:
        refreshed = refresh_pdf(args.pptx, args.pdf)
    if not args.pdf.exists():
        raise FileNotFoundError(
            f"PDF source not found: {args.pdf}. Install LibreOffice or export the PPTX as PDF once."
        )

    generated = convert_presentation(
        args.pdf,
        args.output_dir,
        quality=args.quality,
        metadata_path=args.metadata,
    )
    source_note = "refreshed from PPTX" if refreshed else "existing PDF used"
    print(
        f"Presentation updated: {len(generated)} slides, manifest generated, {source_note}."
    )


if __name__ == "__main__":
    main()
