FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && ARCH=$(uname -m) \
    && ACT_ARCH=$(case "$ARCH" in x86_64) echo "x86_64" ;; aarch64|arm64) echo "arm64" ;; *) echo "x86_64" ;; esac) \
    && curl -sSfL "https://github.com/nektos/act/releases/latest/download/act_Linux_${ACT_ARCH}.tar.gz" | tar xz -C /usr/local/bin act \
    && chmod +x /usr/local/bin/act \
    && act --version

COPY dashboard-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dashboard-api/ .

RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
