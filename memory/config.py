"""Runtime settings, read from environment variables with local-dev defaults."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    falkordb_host: str = os.environ.get("FALKORDB_HOST", "localhost")
    falkordb_port: int = int(os.environ.get("FALKORDB_PORT", "6379"))
    # Ollama on the Ubuntu box, reached through scripts/ollama-tunnel.sh
    ollama_url: str = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11435")
    # mxbai-embed-large, the same model AI Town uses
    embedding_dim: int = int(os.environ.get("EMBEDDING_DIM", "1024"))


settings = Settings()
