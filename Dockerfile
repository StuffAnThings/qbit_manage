FROM python:3.10-alpine

# install packages
RUN apk add --no-cache gcc g++ libxml2-dev libxslt-dev shadow bash curl wget jq grep sed coreutils findutils unzip p7zip ca-certificates

COPY requirements.txt /

RUN echo "**** install python packages ****" \
 && pip3 install --no-cache-dir --upgrade --requirement /requirements.txt \
 && rm -rf /requirements.txt /tmp/* /var/tmp/*

COPY . /app
WORKDIR /app
VOLUME /config
ENTRYPOINT ["python3", "qbit_manage.py"]
