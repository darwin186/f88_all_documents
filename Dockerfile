ARG PYTHON_BASE=python:3.11-slim
FROM ${PYTHON_BASE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir whitenoise==6.6.0

COPY . .

RUN python manage.py collectstatic --noinput || true

COPY docker/entrypoint.sh /entrypoint.sh
# The repository is also developed on Windows. Strip CRLF so Linux does not
# interpret the shebang as `bash\r` when Docker builds from a Windows checkout.
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
