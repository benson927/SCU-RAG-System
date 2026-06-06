import argparse
import io
import json
from pathlib import Path

import fitz
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "frontend" / "public" / "SCU_RAG_Business_Analysis.pdf"
DEFAULT_OUTPUT = PROJECT_ROOT / "frontend" / "public" / "slides"
DEFAULT_METADATA = PROJECT_ROOT / "scripts" / "presentation_metadata.json"


def convert_presentation(
    source: Path,
    output_dir: Path,
    *,
    max_width: int = 1920,
    max_height: int = 1080,
    quality: int = 82,
    metadata_path: Path | None = DEFAULT_METADATA,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    document = fitz.open(source)
    try:
        for index, page in enumerate(document, start=1):
            scale = min(max_width / page.rect.width, max_height / page.rect.height)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")
            destination = output_dir / f"slide_{index}.webp"
            image.save(destination, "WEBP", quality=quality, method=6)
            generated.append(destination)
    finally:
        document.close()

    expected = {path.name for path in generated}
    for stale_path in output_dir.glob("slide_*.*"):
        if stale_path.name not in expected:
            stale_path.unlink()

    metadata = {}
    if metadata_path and metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    slide_titles = metadata.get("slide_titles", [])
    if slide_titles and len(slide_titles) != len(generated):
        raise ValueError(
            f"{metadata_path} defines {len(slide_titles)} slide titles, "
            f"but {source} contains {len(generated)} pages."
        )

    slides = []
    for index, destination in enumerate(generated, start=1):
        title = slide_titles[index - 1] if slide_titles else f"Slide {index}"
        slides.append(
            {
                "src": f"/slides/{destination.name}",
                "title": title,
                "shortTitle": title,
            }
        )

    manifest = {
        "title": metadata.get("title", source.stem),
        "version": metadata.get("version", "1"),
        "slideCount": len(slides),
        "slides": slides,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return generated


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the project presentation as optimized WebP slides.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-width", type=int, default=1920)
    parser.add_argument("--max-height", type=int, default=1080)
    parser.add_argument("--quality", type=int, default=82)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    args = parser.parse_args()

    generated = convert_presentation(
        args.source,
        args.output_dir,
        max_width=args.max_width,
        max_height=args.max_height,
        quality=args.quality,
        metadata_path=args.metadata,
    )
    print(f"Generated {len(generated)} slides in {args.output_dir}")


if __name__ == "__main__":
    main()
