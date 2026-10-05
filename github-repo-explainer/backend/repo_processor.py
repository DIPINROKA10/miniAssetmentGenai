"""Clone + extract relevant source files from a GitHub repo."""
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from git import Repo

# Which file extensions we consider "source code"
ALLOWED_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".go", ".rb", ".php",
    ".c", ".cpp", ".h", ".hpp", ".cs",
    ".html", ".css", ".vue",
    ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg",
    ".md", ".txt", ".sql",
}

# Folders / files to always skip
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".idea", ".vscode", "dist", "build", ".next", "target",
    "coverage", ".pytest_cache",
}
SKIP_FILES = {"package-lock.json", "poetry.lock", "yarn.lock"}

MAX_FILES = 30
MAX_CHARS_PER_FILE = 3000
MAX_TOTAL_CHARS = 12000


def is_valid_github_url(url: str) -> bool:
    url = url.strip().rstrip("/")
    return url.startswith("https://github.com/") and len(url.split("/")) >= 5


def clone_repo(repo_url: str) -> str:
    """Clone to a temp folder, return the folder path."""
    tmp_base = tempfile.gettempdir()
    dest = os.path.join(tmp_base, f"repo_explainer_{uuid.uuid4().hex[:8]}")
    # depth=1 = fast shallow clone
    Repo.clone_from(repo_url, dest, depth=1)
    return dest


def collect_files(repo_path: str):
    collected = []
    repo_root = Path(repo_path)
    for root, dirs, files in os.walk(repo_path):
        # prune skipped dirs in-place
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            if f in SKIP_FILES:
                continue
            ext = Path(f).suffix.lower()
            if ext not in ALLOWED_EXTS:
                continue
            full = Path(root) / f
            try:
                rel = full.relative_to(repo_root).as_posix()
                # skip very large files (>200KB)
                if full.stat().st_size > 200 * 1024:
                    continue
                collected.append((rel, full))
            except Exception:
                continue
    # Prefer: README, main/app/server files, then shortest paths
    def sort_key(item):
        rel = item[0].lower()
        score = 10
        if "readme" in rel:
            score = 0
        elif "main" in rel or "app.py" in rel or "server" in rel or "index" in rel:
            score = 1
        elif "requirement" in rel or "package.json" in rel:
            score = 2
        return (score, len(rel))
    collected.sort(key=sort_key)
    return collected[:MAX_FILES]


def detect_technologies(file_list, repo_path: str) -> list[str]:
    techs: set[str] = set()
    exts = {Path(r).suffix.lower() for r, _ in file_list}
    if ".py" in exts:
        techs.add("Python")
    if ".js" in exts or ".jsx" in exts:
        techs.add("JavaScript")
    if ".ts" in exts or ".tsx" in exts:
        techs.add("TypeScript")
    if ".java" in exts:
        techs.add("Java")
    if ".go" in exts:
        techs.add("Go")
    if ".rb" in exts:
        techs.add("Ruby")
    if ".php" in exts:
        techs.add("PHP")
    if ".cs" in exts:
        techs.add("C#")
    if ".cpp" in exts or ".c" in exts or ".h" in exts:
        techs.add("C/C++")
    if ".html" in exts:
        techs.add("HTML")
    if ".css" in exts:
        techs.add("CSS")
    if ".sql" in exts:
        techs.add("SQL")
    if ".vue" in exts:
        techs.add("Vue")

    root = Path(repo_path)
    # framework hints
    checks = {
        "requirements.txt": ["requirements.txt"],
        "Flask": ["requirements.txt", "app.py"],
        "FastAPI": ["requirements.txt", "main.py"],
        "Django": ["manage.py"],
        "Streamlit": ["requirements.txt"],
        "React": ["package.json"],
        "SQLite": [".db", ".sqlite3"],
    }
    try:
        names = {p.name for p in root.iterdir()}
        all_text = ""
        for fname in ("requirements.txt", "package.json", "pyproject.toml"):
            fp = root / fname
            if fp.exists():
                try:
                    all_text += fp.read_text(errors="ignore")[:4000].lower() + "\n"
                except Exception:
                    pass
        if "flask" in all_text:
            techs.add("Flask")
        if "fastapi" in all_text:
            techs.add("FastAPI")
        if "django" in all_text:
            techs.add("Django")
        if "streamlit" in all_text:
            techs.add("Streamlit")
        if "react" in all_text:
            techs.add("React")
        if "sqlite" in all_text:
            techs.add("SQLite")
        if "requirements.txt" in names or "pyproject.toml" in names:
            pass
    except Exception:
        pass
    return sorted(techs)


def process_repo(repo_url: str) -> dict:
    """Full pipeline: clone -> collect -> read. Returns dict with code text."""
    if not is_valid_github_url(repo_url):
        raise ValueError("URL must look like https://github.com/username/repository")
    repo_path = clone_repo(repo_url)
    try:
        file_list = collect_files(repo_path)
        if not file_list:
            raise ValueError("No readable source files found in this repo.")

        chunks = []
        total = 0
        used_files = []
        for rel, full in file_list:
            try:
                text = full.read_text(errors="ignore")
            except Exception:
                continue
            if not text.strip():
                continue
            snippet = text[:MAX_CHARS_PER_FILE]
            block = f"\n===== FILE: {rel} =====\n{snippet}\n"
            if total + len(block) > MAX_TOTAL_CHARS:
                break
            chunks.append(block)
            total += len(block)
            used_files.append(rel)

        techs = detect_technologies(file_list, repo_path)
        return {
            "repo_path": repo_path,  # caller must cleanup
            "files": used_files,
            "code_text": "".join(chunks),
            "technologies": techs,
        }
    except Exception:
        # cleanup on failure
        shutil.rmtree(repo_path, ignore_errors=True)
        raise
