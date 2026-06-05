import argparse
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def checksum_text(text: str) -> str:
    # Keep the legacy MD5 key format so existing curated faq_cache entries remain incremental.
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def clean_questions(text: str, limit: int) -> list[str]:
    questions = []
    for line in text.splitlines():
        cleaned = line.strip().lstrip("0123456789.、)-* ").strip("\"'")
        if len(cleaned) > 5:
            questions.append(cleaned)
    return questions[:limit]


def build_prompt(text: str, title: str, count: int) -> str:
    return (
        f"你是熟悉東吳大學法規的學生諮詢助手。請根據「{title}」的下列內容，"
        f"生成 {count} 個自然、口語化且可由原文完整回答的問題。"
        "涵蓋資格、期限、金額、流程或情境；每行一題，不要序號或解釋。\n\n"
        f"{text}"
    )


def generate_questions(
    prompt: str,
    *,
    provider: str,
    model: str,
    ollama_base_url: str,
    api_key: str | None,
    count: int,
) -> list[str]:
    if provider == "gemini":
        if not api_key:
            raise RuntimeError("Gemini provider requires GEMINI_API_KEY or --api-key.")
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        response = genai.GenerativeModel(model).generate_content(
            prompt,
            generation_config={"temperature": 0.6, "max_output_tokens": 768},
        )
        return clean_questions(response.text, count)

    from langchain_core.messages import HumanMessage
    from langchain_ollama import ChatOllama

    response = ChatOllama(
        model=model,
        base_url=ollama_base_url,
        temperature=0.6,
    ).invoke([HumanMessage(content=prompt)])
    return clean_questions(response.content, count)


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def generate_dataset(args: argparse.Namespace) -> None:
    loader = PyPDFDirectoryLoader(str(args.data_dir))
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    ).split_documents(loader.load())

    title_mapping = {}
    if args.title_mapping.exists():
        title_mapping = json.loads(args.title_mapping.read_text(encoding="utf-8"))
    cache = {}
    if args.output.exists():
        cache = json.loads(args.output.read_text(encoding="utf-8"))

    generated = skipped = failed = 0
    for chunk in chunks:
        text = chunk.page_content.strip()
        if len(text) < args.minimum_chars:
            continue
        checksum = checksum_text(text)
        if checksum in cache and cache[checksum].get("faqs"):
            skipped += 1
            continue

        source = Path(chunk.metadata.get("source", "")).name
        title = title_mapping.get(source, Path(source).stem)
        try:
            questions = generate_questions(
                build_prompt(text, title, args.questions_per_chunk),
                provider=args.provider,
                model=args.model,
                ollama_base_url=args.ollama_base_url,
                api_key=args.api_key,
                count=args.questions_per_chunk,
            )
        except Exception as exc:
            failed += 1
            print(f"Failed {source}: {exc}")
            continue
        if not questions:
            failed += 1
            continue

        cache[checksum] = {
            "source": source,
            "page": chunk.metadata.get("page", 0) + 1,
            "content": text,
            "faqs": questions,
        }
        generated += 1
        atomic_write_json(args.output, cache)
        if args.delay:
            time.sleep(args.delay)

    atomic_write_json(args.output, cache)
    print(f"Generated: {generated}, skipped: {skipped}, failed: {failed}, total: {len(cache)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Incrementally generate FAQ questions from project PDFs.")
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "faq_cache.json")
    parser.add_argument(
        "--title-mapping",
        type=Path,
        default=PROJECT_ROOT / "backend" / "services" / "title_mapping.json",
    )
    parser.add_argument("--provider", choices=("ollama", "gemini"), default="ollama")
    parser.add_argument("--model")
    parser.add_argument("--ollama-base-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    parser.add_argument("--api-key", default=os.getenv("GEMINI_API_KEY"))
    parser.add_argument("--questions-per-chunk", type=int, default=5)
    parser.add_argument("--chunk-size", type=int, default=400)
    parser.add_argument("--chunk-overlap", type=int, default=80)
    parser.add_argument("--minimum-chars", type=int, default=30)
    parser.add_argument("--delay", type=float, default=0)
    args = parser.parse_args()
    if args.model is None:
        args.model = "gemini-2.5-flash" if args.provider == "gemini" else "gemma3"
    generate_dataset(args)


if __name__ == "__main__":
    main()
