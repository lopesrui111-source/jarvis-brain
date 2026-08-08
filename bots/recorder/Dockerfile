# Offizielles Playwright-Image: Chromium + alle System-Abhaengigkeiten vorinstalliert
FROM mcr.microsoft.com/playwright/python:v1.48.0-noble
ENV PYTHONUNBUFFERED=1 TZ=Europe/Berlin
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
CMD ["python", "bot.py"]
