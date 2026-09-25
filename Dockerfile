# Small, current, and Debian-based so pandas/numpy wheels install without a
# compiler. Slim rather than alpine: musl has no manylinux wheels.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: this layer is cached until requirements.txt changes,
# so ordinary code edits rebuild in seconds rather than minutes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY financelib ./financelib
COPY views ./views
COPY .streamlit ./.streamlit
COPY data/samples ./data/samples

# Run as a non-root user. Azure Container Apps does not require it, but an
# unprivileged container limits the blast radius if the app is ever exploited.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

# Point storage at a path that can be backed by a mounted volume or an Azure
# Files share. Without a mount, data lives in the container and is lost on
# restart — which is fine for a demo and wrong for real use.
ENV FINANCE_DATA_DIR=/data
VOLUME ["/data"]

EXPOSE 8501

# Streamlit needs these to serve correctly behind a proxy or ingress.
ENV STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=4).status==200 else 1)"

CMD ["streamlit", "run", "app.py"]
