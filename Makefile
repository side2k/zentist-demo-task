.PHONY: test test-e2e-staging

test:
	poetry run pytest

test-e2e-staging:
	poetry run pytest -m e2e_staging
