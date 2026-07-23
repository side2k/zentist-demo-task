.PHONY: test test-e2e-staging generate-demo-input run migrate-db reset-db last-reports last-errors last-output

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
	python -m tools.generate_orangehrm_demo_input; \
    python -m tools.generate_saucedemo_demo_input


migrate-db:
	alembic upgrade head

reset-db:
	rm -f db.sqlite
	alembic upgrade head

last-reports:
	sqlite3 -header -line db.sqlite 'SELECT * FROM portal_runs WHERE id IN (SELECT MAX(id) FROM portal_runs GROUP BY portal_key) ORDER BY id DESC;'

last-errors:
	@for portal in orange_hrm saucedemo; do \
		last_id=$$(sqlite3 db.sqlite "SELECT MAX(id) FROM portal_runs WHERE portal_key='$$portal'"); \
		if [ -n "$$last_id" ]; then \
			echo "=== $$portal errors (run_id=$$last_id) ==="; \
			sqlite3 -header -column db.sqlite "SELECT input_item_id, error_message FROM $${portal}_errors WHERE run_id=$${last_id}"; \
		fi; \
	done

last-output:
	@for portal in orange_hrm saucedemo; do \
		last_id=$$(sqlite3 db.sqlite "SELECT MAX(id) FROM portal_runs WHERE portal_key='$$portal'"); \
		if [ -n "$$last_id" ]; then \
			echo "=== $$portal output (run_id=$$last_id) ==="; \
			case $$portal in \
				orange_hrm) cols="id, run_id, status" ;; \
				saucedemo) cols="id, run_id, order_subtotal, order_total, order_tax, order_shipping_info, order_payment_info, receipt_filename" ;; \
				*) cols="*" ;; \
			esac; \
			sqlite3 -header -column db.sqlite "SELECT $$cols FROM $${portal}_output WHERE run_id=$${last_id}"; \
		fi; \
	done
