FROM python:3.11-slim-buster
ARG BRANCH_NAME=master
ENV BRANCH_NAME ${BRANCH_NAME}
ENV TINI_VERSION v0.19.0
ENV QBM_DOCKER True

COPY requirements.txt /

# install packages
RUN echo "**** install system packages ****" \
 && apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get install -y tzdata --no-install-recommends \
 && apt-get install -y gcc g++ libxml2-dev libxslt-dev bash curl wget jq grep sed coreutils findutils unzip p7zip ca-certificates \
 && wget -O /tini https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini-"$(dpkg --print-architecture | awk -F- '{ print $NF }')" \
 && chmod +x /tini \
 && pip3 install --no-cache-dir --upgrade --requirement /requirements.txt \
 && apt-get --purge autoremove gcc g++ libxml2-dev libxslt-dev libz-dev -y \
 && apt-get clean \
 && apt-get update \
 && apt-get check \
 && apt-get -f install \
 && apt-get autoclean \
 && rm -rf /requirements.txt /tmp/* /var/tmp/* /var/lib/apt/lists/*

COPY . /app
WORKDIR /app
VOLUME /config
ENTRYPOINT ["/tini", "-s", "python3", "qbit_manage.py", "--"]
