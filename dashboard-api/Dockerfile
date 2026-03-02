FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -sSfL https://raw.githubusercontent.com/nektos/act/master/install.sh | sh

COPY dashboard-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dashboard-api/ .

RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
