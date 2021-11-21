FROM python:3.9-slim
COPY requirements.txt /
RUN echo "**** install python packages ****" \
 && pip3 install --no-cache-dir --upgrade --requirement /requirements.txt \
 && apt-get autoremove -y \
 && apt-get clean \
 && rm -rf /requirements.txt /tmp/* /var/tmp/* /var/lib/apt/lists/*
COPY . /
VOLUME /config
ENTRYPOINT ["python3","qbit_manage.py"]