"""LLM via Hugging Face Inference API (no torch needed, Render-free friendly).

Set env var HF_TOKEN with a free token from https://huggingface.co/settings/tokens
Model: Qwen/Qwen2.5-1.5B-Instruct (serverless, free tier).
Without a token, returns the structured repo summary (still from real code).
"""
import os
import re

import requests

HF_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
API_URL = f"https://router.huggingface.co/hf-inference/models/{HF_MODEL}"


def _clean_readme(code_text: str) -> str:
    m = re.search(r"===== FILE: README\.md =====\n(.*?)(?=\n===== FILE:|\Z)",
                  code_text, re.S | re.I)
    if not m:
        return ""
    txt = m.group(1)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"!\[.*?\]\(.*?\)", " ", txt)
    txt = re.sub(r"\[.*?\]\(.*?\)", " ", txt)
    txt = re.sub(r"https?://\S+", " ", txt)
    txt = re.sub(r"[#>|\-*`_~=\[\]()]+", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    txt = txt.encode("ascii", "ignore").decode()
    txt = re.sub(r"\s+", " ", txt).strip()
    sents = re.split(r"(?<=[.!])\s+", txt)
    keep = [s for s in sents if len(s.split()) >= 5][:4]
    return " ".join(keep)[:600]


def _extract_symbols(code_text: str) -> tuple[list[str], list[str]]:
    funcs = re.findall(r"^\s*(?:def|function)\s+([A-Za-z_]\w*)", code_text, re.M)
    classes = re.findall(r"^\s*class\s+([A-Za-z_]\w*)", code_text, re.M)
    funcs = list(dict.fromkeys(funcs))[:10]
    classes = list(dict.fromkeys(classes))[:10]
    return funcs, classes


def _dedup_sentences(text: str, limit: int = 8) -> str:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        s = re.sub(r"\s+", " ", p).strip(" -–\t")
        if len(s.split()) < 4:
            continue
        key = re.sub(r"[^a-z0-9 ]", "", s.lower())
        key = re.sub(r"\s+", " ", key).strip()
        if not key or key in seen:
            continue
        words = set(key.split())
        dup = any(len(words & set(k.split())) / max(len(words), 1) > 0.6
                  for k in seen)
        if dup:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= limit:
            break
    return " ".join(out)


def build_prompt(code_text: str, technologies: list[str], repo_url: str,
                 files: list[str]) -> str:
    tech_str = ", ".join(technologies) if technologies else "Python"
    readme = _clean_readme(code_text)
    funcs, classes = _extract_symbols(code_text)
    file_str = ", ".join(files[:8])
    return (
        f"This is a {tech_str} project called {repo_url.split('/')[-1]}. "
        f"Files: {file_str}. "
        + (f"About: {readme} " if readme else "")
        + (f"Functions: {', '.join(funcs)}. " if funcs else "")
        + (f"Classes: {', '.join(classes)}. " if classes else "")
        + "Explain in SIMPLE language for a beginner: "
        "1. Project Overview (1-2 sentences) "
        "2. Main features as a short list "
        "3. How it works in 3 steps. "
        "Use simple words, under 250 words."
    )[:2400]


def _call_inference_api(prompt: str) -> str:
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "HF_TOKEN is not set. Get a free token at "
            "https://huggingface.co/settings/tokens and set it as env var HF_TOKEN."
        )
    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {token}"},
        json={"inputs": prompt,
              "parameters": {"max_new_tokens": 300, "temperature": 0.7,
                             "top_p": 0.9, "repetition_penalty": 1.2,
                             "return_full_text": False}},
        timeout=120,
    )
    if resp.status_code == 503:
        raise RuntimeError("Model is warming up on HF servers, retry in ~30s.")
    if resp.status_code in (401, 403):
        raise RuntimeError("Invalid HF_TOKEN. Check your token.")
    if resp.status_code == 429:
        raise RuntimeError("HF free rate limit hit. Wait a minute and retry.")
    if resp.status_code != 200:
        raise RuntimeError(f"HF API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if isinstance(data, list) and data and "generated_text" in data[0]:
        return data[0]["generated_text"].strip()
    if isinstance(data, dict) and "generated_text" in data:
        return str(data["generated_text"]).strip()
    raise RuntimeError(f"Unexpected HF response: {str(data)[:300]}")


def explain_with_hf(code_text: str, technologies: list[str], repo_url: str,
                     files: list[str] | None = None) -> str:
    files = files or []
    tech_str = ", ".join(technologies) if technologies else "Python"
    repo_name = repo_url.rstrip("/").split("/")[-1]
    readme = _clean_readme(code_text)
    funcs, classes = _extract_symbols(code_text)

    # --- LLM part via hosted API (no local torch) ---
    prompt = build_prompt(code_text, technologies, repo_url, files)
    try:
        llm_raw = _call_inference_api(prompt)
    except Exception as e:
        llm_raw = ""
        api_error = str(e)
    else:
        api_error = ""
    llm_clean = _deduplicate(llm_raw) if llm_raw else ""

    # --- structured explanation built from REAL repo data ---
    if readme:
        overview = readme[:500]
        cut = overview.rfind(". ")
        if cut > 200:
            overview = overview[:cut + 1]
        else:
            cut = overview.rfind(" ")
            if cut > 200:
                overview = overview[:cut]
    elif "gan" in code_text.lower() or "generat" in code_text.lower():
        overview = (
            f"This project ({repo_name}) is a Generative AI experiment lab. "
            "It teaches models to create new content such as images."
        )
    else:
        overview = (
            f"This project ({repo_name}) is a {tech_str} codebase. "
            "It contains scripts that implement the features below."
        )

    feats: list[str] = []
    low = code_text.lower()
    if "nst" in low or "style transfer" in low:
        feats.append("Run neural style transfer experiments")
    if "cyclegan" in low or "gan" in low:
        feats.append("Train/test GAN-style image generation (e.g. CycleGAN)")
    if "diffusion" in low:
        feats.append("Experiment with diffusion models")
    if "transformer" in low or "attention" in low:
        feats.append("Explore transformers and attention")
    for f in funcs[:4]:
        feats.append(f"Use `{f}()` from the source code")
    feats = list(dict.fromkeys(feats))[:5]
    if not feats:
        feats = [f"Explore the code in {fn}" for fn in files[:4]]

    feats_b = [f"- {x}" for x in feats]
    tech_bullets = "\n".join(f"- {t}" for t in technologies) or "- Python"

    how = (
        "The user opens the assignment scripts.\n"
        "The scripts load data and define the model.\n"
        "Training/generation code runs in Python.\n"
        "Results (images/text) are produced from the learned model."
    )

    explanation = (
        f"Project Overview\n{overview}\n\n"
        f"The application allows users to:\n" + "\n".join(feats_b) + "\n\n"
        f"Main Technologies:\n{tech_bullets}\n\n"
        f"How it works:\n{how}"
    )
    if llm_clean and len(llm_clean.split()) >= 8:
        ai = llm_clean.encode("ascii", "ignore").decode()
        ai = re.sub(r"\s+", " ", ai).strip()[:800]
        explanation += f"\n\nAI explanation (HF {HF_MODEL}):\n{ai}"
    elif api_error:
        explanation += f"\n\n(Note: hosted AI text unavailable - {api_error})"
    return explanation


# keep old name working so main.py needs no change
def explain_with_ollama(code_text: str, technologies: list[str], repo_url: str,
                        files: list[str] | None = None) -> str:
    return explain_with_hf(code_text, technologies, repo_url, files)


def _deduplicate(text: str) -> str:
    return _dedup_sentences(text)
