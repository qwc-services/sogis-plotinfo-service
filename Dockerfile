# WSGI service environment

FROM sourcepole/qwc-uwsgi-base:alpine-v2024.01.16

ADD requirements.txt /srv/qwc_service/requirements.txt

# postgresql-dev g++ python3-dev: Required for psycopg2-binary
RUN \
    apk add --no-cache --update --virtual runtime-deps postgresql-libs && \
    apk add --no-cache --update --virtual build-deps postgresql-dev g++ python3-dev && \
    pip3 install --no-cache-dir -r /srv/qwc_service/requirements.txt && \
    apk del build-deps

ADD src /srv/qwc_service/
