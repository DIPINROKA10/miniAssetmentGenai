"""FastAPI backend: GitHub URL -> clone -> extract -> Ollama -> explanation."""
import shutil
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from repo_processor import process_repo
from llm import explain_with_ollama

app = FastAPI(title="Local GitHub Repo Explainer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ExplainRequest(BaseModel):
    repo_url: str


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/explain")
def explain(req: ExplainRequest):
    repo_url = req.repo_url.strip().rstrip("/")
    if not repo_url.startswith("https://github.com/"):
        return {"error": "Please enter a valid GitHub URL like https://github.com/username/repo"}
    repo_path = None
    try:
        result = process_repo(repo_url)
        repo_path = result["repo_path"]
        explanation = explain_with_ollama(
            result["code_text"], result["technologies"], repo_url,
            result["files"],
        )
        return {
            "repo_url": repo_url,
            "files_analyzed": result["files"],
            "technologies": result["technologies"],
            "explanation": explanation,
        }
    except ConnectionError as e:
        return {"error": str(e)}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Failed to explain repo: {e}"}
    finally:
        if repo_path:
            shutil.rmtree(repo_path, ignore_errors=True)
