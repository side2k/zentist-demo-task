FROM python:3.11-slim AS base-image

RUN apt-get update && apt-get upgrade -y

RUN apt-get install -y make sqlite3

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    POETRY_VERSION=2.4.1 \
    VIRTUAL_ENV=/venv

ENV PATH=$VIRTUAL_ENV/bin:$PATH

WORKDIR /app
FROM base-image AS builder-minimal

RUN pip install "poetry==${POETRY_VERSION}"

RUN python -m venv $VIRTUAL_ENV

COPY pyproject.toml .
COPY poetry.lock .

ENV POETRY_VIRTUALENVS_CREATE=false
RUN poetry install --only main

FROM builder-minimal AS builder-tests

RUN poetry install --only test

FROM builder-minimal AS builder-saucedemo
# SauceDeemo portal requires playwright, which has a quite heavy dependency tree (~1.2G)
# We do not need it for the CI (especially free tier) to run unit tests, at least for now

RUN poetry install --only saucedemo

FROM base-image AS app-minimal

COPY . .
COPY docker/runner.entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh


ENTRYPOINT ["/entrypoint.sh"]
FROM app-minimal AS app-tests

COPY --from=builder-tests $VIRTUAL_ENV $VIRTUAL_ENV

CMD ["test"]
FROM app-minimal AS staging

COPY --from=builder-saucedemo $VIRTUAL_ENV $VIRTUAL_ENV

RUN playwright install-deps
RUN playwright install chromium

RUN make reset-db
CMD ["run"]
