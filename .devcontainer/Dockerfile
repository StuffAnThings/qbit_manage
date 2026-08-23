FROM ghcr.io/bare-devcontainer/uv:trixie

USER root

RUN usermod -u 99 -g 100 dev \
    && mkdir -p /home/dev/.cache/uv \
    && chown -R 99:100 /home/dev \
    && chmod -R 777 /home/dev/.cache

USER dev
