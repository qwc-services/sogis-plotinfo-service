ARG BASE_TAG=latest
FROM sourcepole/qwc-uwsgi-base:alpine-$BASE_TAG

ARG UPDATE_DEPS=false

WORKDIR /srv/qwc_service

COPY pyproject.toml uv.lock ./

# Deps required of psycopg2
RUN \
    apk add --no-cache --update --virtual runtime-deps postgresql-libs && \
    apk add --no-cache --update --virtual build-deps git postgresql-dev g++ python3-dev && \
    if [ "${UPDATE_DEPS}" = "true" ]; then \
        uv lock --upgrade; \
    fi && \
    uv sync --frozen && \
    uv cache clean && \
    apk del build-deps

COPY src /srv/qwc_service/
