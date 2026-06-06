FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/backend/requirements.txt

COPY . /app
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home app \
    && mkdir -p /app/chroma_db /app/data/managed_documents \
    && chmod +x /app/backend/entrypoint.sh \
    && chown -R app:app /app

USER app

EXPOSE 8000

ENTRYPOINT ["/app/backend/entrypoint.sh"]
