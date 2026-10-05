#!/bin/bash
# Backend on :8000, Streamlit on :7860 (Spaces forwards to 7860)
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --app-dir /app/backend &
BACK_PID=$!
python -m streamlit run /app/frontend/app.py \
  --server.port 7860 --server.address 0.0.0.0 --server.headless true
kill $BACK_PID
