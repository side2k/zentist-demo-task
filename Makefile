.PHONY: test test-e2e-staging generate-demo-input run migrate-db reset-db

test:
	poetry run pytest

test-e2e-staging:
	poetry run pytest -m e2e_staging

generate-demo-input:
	poetry run python -m tools.generate_orangehrm_demo_input

run:
	poetry run python run.py

migrate-db:
	poetry run alembic upgrade head

reset-db:
	rm -f db.sqlite
	poetry run alembic upgrade head
