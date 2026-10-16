"""Runtime settings, read from environment variables with local-dev defaults."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    falkordb_host: str = os.environ.get("FALKORDB_HOST", "localhost")
    falkordb_port: int = int(os.environ.get("FALKORDB_PORT", "6379"))
    # Ollama on the Ubuntu box, reached through scripts/ollama-tunnel.sh
    ollama_url: str = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11435")
    # Claim extraction runs once per finished conversation, so it can use the slower, better model.
    extract_model: str = os.environ.get("EXTRACT_MODEL", "llama3.1:8b")
    # mxbai-embed-large, the same model AI Town uses
    embed_model: str = os.environ.get("EMBED_MODEL", "mxbai-embed-large")
    embedding_dim: int = int(os.environ.get("EMBEDDING_DIM", "1024"))
    # How often failed conversations (model outage, crash) are retried from their stored transcript.
    retry_interval_s: float = float(os.environ.get("RETRY_INTERVAL_S", "60"))


settings = Settings()
