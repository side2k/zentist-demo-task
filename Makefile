.PHONY: test test-e2e-staging generate-demo-input

test:
	poetry run pytest

test-e2e-staging:
	poetry run pytest -m e2e_staging

generate-demo-input:
	poetry run python -m tools.generate_orangehrm_demo_input
