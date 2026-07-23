#!/bin/sh
export PATH=/venv/bin:$PATH
cd /app

if [ "$1" = 'test' ]; then
    exec make test
fi

if [ "$1" = 'test-e2e-staging' ]; then
    exec make test-e2e-staging
fi

if [ "$1" = 'run' ]; then
    exec make run-docker
fi

if [ "$1" = 'run-debug' ]; then
    exec make run-docker-debug
fi

if [ "$1" = 'generate-demo-input' ]; then
    exec make generate-demo-input
fi

if [ "$1" = 'last-output' ]; then
    exec make last-output
fi

if [ "$1" = 'last-errors' ]; then
    exec make last-errors
fi

exec "$@"
