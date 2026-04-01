# ── Stage 1: install Python deps ───────────────────────────────────────────
FROM python:3.12-slim AS deps

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: install Playwright browsers ───────────────────────────────────
FROM deps AS playwright

# Install system libraries required by Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
        libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
        libgbm1 libasound2 libpangocairo-1.0-0 libpango-1.0-0 \
        libcairo2 libatspi2.0-0 libgtk-3-0 libx11-xcb1 \
    && rm -rf /var/lib/apt/lists/*

RUN playwright install chromium

# ── Stage 3: final image ────────────────────────────────────────────────────
FROM playwright AS final

WORKDIR /app
COPY . .

# Non-root user for better security
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

# Output volume for CSV files
VOLUME ["/app/output"]

EXPOSE 8000

CMD ["python", "main.py", "--serve"]
