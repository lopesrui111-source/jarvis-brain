FROM python:3.12-slim
ENV TZ=Europe/Berlin PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py cli.py protokoll.py ./
CMD ["python", "-u", "bot.py"]
