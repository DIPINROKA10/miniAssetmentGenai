"""Streamlit frontend for Local GitHub Repo Explainer."""
import os
import requests
import streamlit as st

BACKEND = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000/api/explain")

st.set_page_config(page_title="GitHub Repo Explainer", page_icon="📦")
st.markdown(
    """
    <style>
    [data-testid="stDeployButton"] {display: none !important;}
    [data-testid="stToolbar"] {display: none !important;}
    [data-testid="stDecoration"] {display: none !important;}
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("📦 Explain this GitHub Repository")
st.write("Enter a GitHub URL. Code is cloned locally, then explained by your local LLM (Hugging Face, runs on your machine).")

url = st.text_input("GitHub repository URL", placeholder="https://github.com/username/repository")

if st.button("Explain", type="primary"):
    if not url.strip().startswith("https://github.com/"):
        st.error("Please enter a valid URL like https://github.com/username/repo")
    else:
        with st.spinner("Cloning repo + asking local LLM... (can take 30-90s first time)"):
            try:
                r = requests.post(BACKEND, json={"repo_url": url.strip()}, timeout=240)
                data = r.json()
            except Exception as e:
                st.error(f"Cannot reach backend at {BACKEND}. Is FastAPI running? Error: {e}")
                st.stop()
        if "error" in data and data["error"]:
            st.error(data["error"])
        else:
            st.success("Done!")
            if data.get("technologies"):
                st.subheader("Main Technologies")
                st.write(", ".join(data["technologies"]))
            st.subheader("Project Explanation")
            st.markdown(data.get("explanation", "No explanation returned."))
            with st.expander("Files analyzed"):
                for f in data.get("files_analyzed", []):
                    st.code(f)
