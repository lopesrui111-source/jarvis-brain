FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=Europe/Berlin
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY higgsfield_client.py .
COPY bot.py .
CMD ["python", "bot.py"]
