import json
import os

from backend.config import get_settings


_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(_CURRENT_DIR))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
MANAGED_DATA_DIR = os.path.join(DATA_DIR, "managed_documents")
MANAGED_MANIFEST_PATH = os.path.join(MANAGED_DATA_DIR, "manifest.json")
CHROMA_DIR = os.path.join(PROJECT_ROOT, "chroma_db")

_title_mapping_cache = {
    "mtime_ns": None,
    "mapping": {},
}
_faq_count_cache = {
    "signature": None,
    "count": 0,
}


def ensure_data_directory() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def reset_repository_caches() -> None:
    global _title_mapping_cache, _faq_count_cache
    _title_mapping_cache = {
        "mtime_ns": None,
        "mapping": {},
    }
    _faq_count_cache = {
        "signature": None,
        "count": 0,
    }


def get_pdf_data_dir() -> str:
    return MANAGED_DATA_DIR if get_settings().database_enabled else DATA_DIR


def get_pdf_files() -> list:
    pdf_dir = get_pdf_data_dir()
    if not os.path.exists(pdf_dir):
        return []
    return sorted(filename for filename in os.listdir(pdf_dir) if filename.endswith(".pdf"))


def get_faq_signature() -> dict | None:
    faq_cache_path = os.path.join(DATA_DIR, "faq_cache.json")
    if not os.path.exists(faq_cache_path):
        return None
    stat = os.stat(faq_cache_path)
    signature = {
        "file": "faq_cache.json",
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }
    if get_settings().database_enabled:
        if not os.path.exists(MANAGED_MANIFEST_PATH):
            signature["manifest"] = None
        else:
            manifest_stat = os.stat(MANAGED_MANIFEST_PATH)
            signature["manifest"] = {
                "mtime_ns": manifest_stat.st_mtime_ns,
                "size": manifest_stat.st_size,
            }
    return signature


def load_managed_manifest() -> dict:
    if not get_settings().database_enabled or not os.path.exists(MANAGED_MANIFEST_PATH):
        return {"version": 1, "documents": []}
    try:
        with open(MANAGED_MANIFEST_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data.get("documents"), list):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {"version": 1, "documents": []}


def get_active_source_map() -> dict:
    return {
        item.get("source_alias"): item
        for item in load_managed_manifest().get("documents", [])
        if item.get("source_alias") and item.get("filename")
    }


def iter_active_faq_entries() -> list:
    faq_cache_path = os.path.join(DATA_DIR, "faq_cache.json")
    if not os.path.exists(faq_cache_path):
        return []
    with open(faq_cache_path, "r", encoding="utf-8") as handle:
        faq_cache = json.load(handle)

    active_source_map = get_active_source_map()
    entries = []
    for entry in faq_cache.values():
        source_alias = entry.get("source", "")
        if get_settings().database_enabled:
            manifest_entry = active_source_map.get(source_alias)
            if manifest_entry is None:
                continue
            managed_filename = manifest_entry["filename"]
        else:
            managed_filename = source_alias
        entries.append((entry, managed_filename, source_alias))
    return entries


def build_db_meta(pdf_files: list) -> dict:
    return {
        "files": pdf_files,
        "faq_signature": get_faq_signature(),
    }


def is_db_meta_current(db_meta: dict, pdf_files: list) -> bool:
    return (
        db_meta.get("files", []) == pdf_files
        and db_meta.get("faq_signature") == get_faq_signature()
    )


def clean_pdf_text(text: str) -> str:
    if not text:
        return text
    replacements = {
        "\u014c": "ft",
        "\u019f": "ti",
        "\u01a9": "tt",
        "\ufb00": "ff",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\ufb03": "ffi",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    return text


def get_title_mapping() -> dict:
    global _title_mapping_cache
    mapping_paths = [
        os.path.join(os.path.dirname(__file__), "title_mapping.json"),
        os.path.join(MANAGED_DATA_DIR, "title_mapping.json"),
    ]
    signature = tuple(
        (path, os.stat(path).st_mtime_ns)
        for path in mapping_paths
        if os.path.exists(path)
    )
    if _title_mapping_cache["mtime_ns"] == signature:
        return _title_mapping_cache["mapping"]

    mapping = {}
    for mapping_path in mapping_paths:
        if not os.path.exists(mapping_path):
            continue
        try:
            with open(mapping_path, "r", encoding="utf-8") as handle:
                mapping.update(json.load(handle))
        except (OSError, ValueError, TypeError):
            continue
    _title_mapping_cache = {
        "mtime_ns": signature,
        "mapping": mapping,
    }
    return mapping


def get_faq_count() -> int:
    global _faq_count_cache
    signature = get_faq_signature()
    if _faq_count_cache["signature"] == signature:
        return _faq_count_cache["count"]

    faq_count = 0
    if signature is not None:
        try:
            for entry, _managed_filename, _source_alias in iter_active_faq_entries():
                faq_count += len(
                    [question for question in entry.get("faqs", []) if question.strip()]
                )
        except (OSError, ValueError, TypeError):
            faq_count = 0
    _faq_count_cache = {
        "signature": signature,
        "count": faq_count,
    }
    return faq_count
