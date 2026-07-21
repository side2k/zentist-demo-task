.PHONY: test test-e2e-staging generate-demo-input run migrate-db reset-db

test:
	pytest

run:
	python3 run.py

run-docker:
	python3 run.py --config=/config.json

run-docker-debug:
	python3 run.py --config=/config.json --log-level=DEBUG

test-e2e-staging:
	pytest -m e2e_staging

generate-demo-input:
	python -m tools.generate_orangehrm_demo_input

run:
	python3 run.py

migrate-db:
	alembic upgrade head

reset-db:
	rm -f db.sqlite
	alembic upgrade head

last-reports:
	sqlite3 -header -line db.sqlite 'SELECT * FROM portal_runs WHERE id IN (SELECT MAX(id) FROM portal_runs GROUP BY portal_key) ORDER BY id DESC;'
