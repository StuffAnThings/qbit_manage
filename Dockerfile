FROM python:3.11-alpine
ARG BRANCH_NAME=master
ENV BRANCH_NAME=${BRANCH_NAME}
ENV TINI_VERSION=v0.19.0
ENV QBM_DOCKER=True

COPY requirements.txt /

# install packages
RUN echo "**** install system packages ****" \
 && apk update \
 && apk upgrade \
 && apk add --no-cache tzdata gcc g++ libxml2-dev libxslt-dev zlib-dev bash curl wget jq grep sed coreutils findutils unzip p7zip ca-certificates tini\
 && pip3 install --no-cache-dir --upgrade --requirement /requirements.txt \
 && apk del gcc g++ libxml2-dev libxslt-dev zlib-dev \
 && rm -rf /requirements.txt /tmp/* /var/tmp/* /var/cache/apk/*

COPY . /app
WORKDIR /app
VOLUME /config
ENTRYPOINT ["/sbin/tini", "-s", "python3", "qbit_manage.py"]
