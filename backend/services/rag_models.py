import subprocess
import time
import urllib.request

from langchain_ollama import ChatOllama, OllamaEmbeddings

from backend.config import get_settings


_embeddings = None
_llm = None
_ollama_checked = False


def ensure_ollama_running() -> bool:
    ollama_url = get_settings().ollama_base_url
    try:
        with urllib.request.urlopen(ollama_url, timeout=1.0) as response:
            if response.status == 200:
                return True
    except Exception:
        print("🤖 偵測到地端 Ollama 未啟動，嘗試自動開啟 Ollama 應用程式...")
        try:
            subprocess.Popen(
                ["open", "-a", "Ollama"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _attempt in range(15):
                time.sleep(1.0)
                try:
                    with urllib.request.urlopen(ollama_url, timeout=1.0) as response:
                        if response.status == 200:
                            print("🎉 Ollama 服務已成功啟動！")
                            return True
                except Exception:
                    continue
            print("⚠️ Ollama 啟動時間較長，請稍後確認是否已在背景載入。")
        except Exception as exc:
            print(f"❌ 無法自動啟動 Ollama: {exc}。請手動開啟 Ollama 應用程式。")
    return False


def get_embeddings():
    global _embeddings, _ollama_checked
    if _embeddings is None:
        if not _ollama_checked:
            ensure_ollama_running()
            _ollama_checked = True
        settings = get_settings()
        _embeddings = OllamaEmbeddings(
            model=settings.ollama_embedding_model,
            base_url=settings.ollama_base_url,
            client_kwargs={"timeout": settings.ollama_request_timeout_seconds},
        )
    return _embeddings


def get_llm():
    global _llm, _ollama_checked
    if _llm is None:
        if not _ollama_checked:
            ensure_ollama_running()
            _ollama_checked = True
        settings = get_settings()
        _llm = ChatOllama(
            model=settings.ollama_chat_model,
            base_url=settings.ollama_base_url,
            client_kwargs={"timeout": settings.ollama_request_timeout_seconds},
            temperature=0.0,
        )
    return _llm
