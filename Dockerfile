ARG BASE_TAG=latest
FROM sourcepole/qwc-uwsgi-base:alpine-$BASE_TAG

WORKDIR /srv/qwc_service
ADD pyproject.toml uv.lock ./

# Deps required of psycopg2
RUN \
    apk add --no-cache --update --virtual runtime-deps postgresql-libs && \
    apk add --no-cache --update --virtual build-deps git postgresql-dev g++ python3-dev && \
    uv sync --frozen && \
    uv cache clean && \
    apk del build-deps

ADD src /srv/qwc_service/
