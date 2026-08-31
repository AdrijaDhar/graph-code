from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_IGNORE = [
    ".git/",
    "node_modules/",
    "dist/",
    "build/",
    "target/",
    "vendor/",
    "__pycache__/",
    ".venv/",
    "venv/",
    "*.min.js",
    ".next/",
    "data/",
]

EXTENSION_LANGUAGE = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    memgraph_uri: str = ""
    memgraph_user: str = ""
    memgraph_password: str = ""
    rocksdb_path: str = "data/rocksdb"
    database_url: str = "sqlite:///data/graphcode.db"
    max_file_bytes: int = 512 * 1024
    max_hops: int = 10
    max_call_depth: int = 5
    max_context_tokens: int = 8000
    github_client_id: str = ""
    github_client_secret: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    admin_github_ids: str = ""
    session_secret: str = "graphcode-dev-secret-change-me"
    cors_origins: str = "http://localhost:3000"
    public_base_url: str = "http://localhost:8000"

    @property
    def admin_ids(self) -> set[str]:
        return {x.strip() for x in self.admin_github_ids.split(",") if x.strip()}

    @property
    def rocks_path(self) -> Path:
        return Path(self.rocksdb_path)


settings = Settings()
