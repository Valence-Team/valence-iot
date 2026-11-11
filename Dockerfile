FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

RUN useradd --create-home --uid 1000 valence

# Dependências com torch só para CPU
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.1 torchvision==0.29.1 \
    && pip install -r requirements.txt

# Código e dados do serviço
COPY app ./app
COPY dados ./dados
RUN mkdir -p modelos .cache/huggingface && chown -R valence:valence /app

USER valence

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
