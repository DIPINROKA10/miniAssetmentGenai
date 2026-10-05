FROM python:3.11-slim

# git is required by GitPython to clone repos
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 7860

CMD ["bash", "start.sh"]
