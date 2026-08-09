FROM node:20-bookworm-slim
ENV TZ=Europe/Berlin
WORKDIR /app

# System-Abhaengigkeiten fuer Chromium (Remotion rendert ueber Headless-Chrome)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libgbm1 libasound2 libatspi2.0-0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libxkbcommon0 libpango-1.0-0 \
    libcairo2 libx11-6 libxcb1 libxext6 libglib2.0-0 \
    fonts-liberation fonts-dejavu-core \
    curl ca-certificates unzip fontconfig \
    && rm -rf /var/lib/apt/lists/*

COPY package.json .
RUN npm install --no-audit --no-fund

# Geist-Schrift (Büroflow-Font) systemweit installieren, damit Remotion sie rendert
RUN mkdir -p /usr/share/fonts/geist && \
    curl -sL "https://github.com/vercel/geist-font/releases/latest/download/Geist.zip" -o /tmp/geist.zip 2>/dev/null && \
    (cd /tmp && unzip -o -q geist.zip -d geist_extract 2>/dev/null || true) && \
    (find /tmp/geist_extract -name "*.ttf" -exec cp {} /usr/share/fonts/geist/ \; 2>/dev/null || true) && \
    (find /tmp/geist_extract -name "*.otf" -exec cp {} /usr/share/fonts/geist/ \; 2>/dev/null || true) && \
    fc-cache -f 2>/dev/null || true

# Remotion braucht einen Chromium-Download (Chrome Headless Shell)
RUN npx remotion browser ensure || true

COPY remotion.config.js .
COPY src ./src
# custom-Ordner sicherstellen (wird zur Laufzeit per Volume ueberlagert)
RUN mkdir -p /app/src/custom
COPY render_server.js .
# Logos als statische Dateien fuer Remotion (staticFile sucht in public/)
COPY brand ./public/brand

CMD ["node", "render_server.js"]
