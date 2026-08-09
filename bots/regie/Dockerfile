FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=Europe/Berlin
WORKDIR /app
# ffmpeg + ffprobe fuer Referenz-Video-Analyse (Frames extrahieren)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY higgsfield_client.py .
COPY bot.py .
CMD ["python", "bot.py"]
