# Use a multi-stage build to minimize final image size
FROM python:3.13-alpine as builder

ARG BRANCH_NAME=master
ENV BRANCH_NAME=${BRANCH_NAME}

# Install build-time dependencies only
RUN apk add --no-cache \
    gcc \
    g++ \
    libxml2-dev \
    libxslt-dev \
    zlib-dev \
    curl \
    bash

# Install UV (fast pip alternative)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy only dependency files first (better layer caching)
COPY pyproject.toml setup.py VERSION /app/
WORKDIR /app

# Install project in a virtual env (lightweight & reproducible)
RUN /root/.local/bin/uv pip install --system --no-deps -e .

# Final stage: minimal runtime image
FROM python:3.13-alpine

ENV TINI_VERSION=v0.19.0

# Runtime dependencies (smaller than build stage)
RUN apk add --no-cache \
    tzdata \
    bash \
    curl \
    jq \
    tini \
    && rm -rf /var/cache/apk/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages/ /usr/local/lib/python3.13/site-packages/
COPY --from=builder /app /app
COPY . /app
WORKDIR /app
VOLUME /config

ENTRYPOINT ["/sbin/tini", "-s", "--"]
CMD ["python3", "qbit_manage.py"]
