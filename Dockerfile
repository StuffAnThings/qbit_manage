# Use a multi-stage build to minimize final image size
FROM python:3.13-alpine AS builder

ARG BRANCH_NAME=master
ENV BRANCH_NAME=${BRANCH_NAME}
ENV QBM_DOCKER=True

# Install build-time dependencies only
RUN apk add --no-cache \
    gcc \
    g++ \
    libxml2-dev \
    libxslt-dev \
    zlib-dev \
    libffi-dev \
    curl \
    bash

# Install UV (fast pip alternative)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy only dependency files first (better layer caching)
COPY pyproject.toml setup.py VERSION /app/
WORKDIR /app

# Install project in a virtual env (lightweight & reproducible)
RUN /root/.local/bin/uv pip install --system .

# Final stage: minimal runtime image
FROM python:3.13-alpine

# Build arguments
ARG APP_VERSION
ARG BUILD_DATE
ARG VCS_REF

# OCI Image Specification labels
LABEL org.opencontainers.image.title="qbit-manage"
LABEL org.opencontainers.image.description="This tool will help manage tedious tasks in qBittorrent and automate them. Tag, categorize, remove Orphaned data, remove unregistered torrents and much much more."
LABEL org.opencontainers.image.version="$APP_VERSION"
LABEL org.opencontainers.image.created="$BUILD_DATE"
LABEL org.opencontainers.image.revision="$VCS_REF"
LABEL org.opencontainers.image.authors="bobokun"
LABEL org.opencontainers.image.vendor="StuffAnThings"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.url="https://github.com/StuffAnThings/qbit_manage"
LABEL org.opencontainers.image.documentation="https://github.com/StuffAnThings/qbit_manage/wiki"
LABEL org.opencontainers.image.source="https://github.com/StuffAnThings/qbit_manage"
LABEL org.opencontainers.image.base.name="python:3.13-alpine"

ENV TINI_VERSION=v0.19.0


# Runtime dependencies (smaller than build stage)
RUN apk add --no-cache \
    tzdata \
    bash \
    curl \
    jq \
    tini \
    su-exec \
    && rm -rf /var/cache/apk/*

# Copy installed packages and scripts from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/
COPY --from=builder /app /app
COPY . /app
COPY entrypoint.sh /app/entrypoint.sh
WORKDIR /app
RUN chmod +x /app/entrypoint.sh
VOLUME /config

# Expose port 8080
EXPOSE 8080

ENTRYPOINT ["/sbin/tini", "-s", "/app/entrypoint.sh"]
CMD ["python3", "qbit_manage.py"]
