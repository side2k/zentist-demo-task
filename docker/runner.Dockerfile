FROM python:3.11-alpine AS base-image

RUN apk add make sqlite

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    POETRY_VERSION=2.4.1 \
    VIRTUAL_ENV=/venv

ENV PATH=$VIRTUAL_ENV/bin:$PATH

WORKDIR /app
FROM base-image AS builder-image

RUN pip install "poetry==${POETRY_VERSION}"

RUN python -m venv $VIRTUAL_ENV

COPY pyproject.toml .
COPY poetry.lock .

ENV POETRY_VIRTUALENVS_CREATE=false
RUN poetry install

FROM base-image AS staging

COPY --from=builder-image $VIRTUAL_ENV $VIRTUAL_ENV

COPY . .
RUN make reset-db

COPY docker/runner.entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["test"]
