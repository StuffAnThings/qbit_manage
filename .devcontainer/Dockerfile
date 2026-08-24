FROM ghcr.io/bare-devcontainer/uv:trixie@sha256:cbca69c01bbe1d891b919316c277b0fe20cb731547ff9b70ed6e625b13f33961

USER root

RUN usermod -u 99 -g 100 dev \
    && mkdir -p /home/dev/.cache/uv \
    && chown -R 99:100 /home/dev \
    && chmod -R 777 /home/dev/.cache

USER dev
