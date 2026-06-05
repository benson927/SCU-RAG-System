import argparse
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import select

from backend.database import session_scope
from backend.models import DocumentVersion
from backend.services.document_service import (
    create_document_with_version,
    enqueue_index_job,
    publish_version,
)
from backend.services.index_worker import wake_index_worker


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = Path(os.getenv("LEGACY_DATA_DIR", PROJECT_ROOT / "data"))
DEFAULT_TITLE_MAPPING = PROJECT_ROOT / "backend" / "services" / "title_mapping.json"


def load_title_mapping(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def discover_pdfs(data_dir: Path) -> list[Path]:
    return sorted(path for path in data_dir.glob("*.pdf") if path.is_file())


def checksum_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_legacy_data(data_dir: Path, title_mapping_path: Path, publish: bool) -> dict:
    title_mapping = load_title_mapping(title_mapping_path)
    pdfs = discover_pdfs(data_dir)
    result = {"found": len(pdfs), "imported": 0, "skipped": 0, "items": []}

    with session_scope() as session:
        known_checksums = set(session.scalars(select(DocumentVersion.checksum)))

    for pdf_path in pdfs:
        checksum = checksum_file(pdf_path)
        title = title_mapping.get(pdf_path.name, pdf_path.stem)
        item = {
            "filename": pdf_path.name,
            "title": title,
            "checksum": checksum,
            "action": "skip" if checksum in known_checksums else ("publish" if publish else "dry-run"),
        }
        result["items"].append(item)
        if checksum in known_checksums:
            result["skipped"] += 1
            continue
        if not publish:
            continue

        content = pdf_path.read_bytes()
        with session_scope() as session:
            document = create_document_with_version(
                session,
                title=title,
                version_number="legacy-initial",
                effective_date=None,
                filename=pdf_path.name,
                content_type="application/pdf",
                content=content,
            )
            version = next(version for version in document.versions if version.checksum == checksum)
            publish_version(
                session,
                version.id,
                trigger="legacy_import",
                allowed_statuses={"draft"},
                enqueue_job=False,
            )
        known_checksums.add(checksum)
        result["imported"] += 1

    if result["imported"]:
        with session_scope() as session:
            enqueue_index_job(session, "legacy_import")
        wake_index_worker()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Import legacy PDFs into PostgreSQL and S3 storage.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--title-mapping", type=Path, default=DEFAULT_TITLE_MAPPING)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="List planned imports without writing (default).")
    mode.add_argument("--publish", action="store_true", help="Upload and publish missing legacy PDFs.")
    args = parser.parse_args()

    result = import_legacy_data(
        data_dir=args.data_dir,
        title_mapping_path=args.title_mapping,
        publish=args.publish,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
