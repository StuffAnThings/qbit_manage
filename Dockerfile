FROM hotio/base:alpine

RUN apk add --no-cache py3-pip
COPY --chown=hotio:users requirements.txt /
RUN echo "**** install python packages ****" \
 && pip3 install --user --no-cache-dir --upgrade --requirement /requirements.txt \
 && rm -rf /requirements.txt /tmp/* /var/tmp/*

COPY --chown=hotio:users . "${APP_DIR}"
WORKDIR ${APP_DIR}
ENTRYPOINT ["python3", "qbit_manage.py"]