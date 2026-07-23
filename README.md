# Demo task for RPA Principal job application at Zentist

## Purpose

This project is a set of "portal runners". Every portal runner processes a batch of input data items and outputs a status report to the database. Each processed item's result (output fields, errors) is persisted to per-portal database tables. Portal runners are managed by the root orchestrator.

## Portals

### OrangeHRM

Processes employee data updates on the [OrangeHRM demo portal](https://opensource-demo.orangehrmlive.com/). Reads existing employees, creates new ones, and updates middle names.

### SauceDemo

Automates the [SauceDemo](https://www.saucedemo.com/) e-commerce flow: logs in with the provided credentials, adds 3 random items to cart, completes checkout, and downloads the PDF receipt.

## Setting up

### Configuring

Config file name for the orchestrator is `config.json`.
Sample config is in the `config.json.example` - copy it to `config.json` to have a minimal working configuration.

See more details about config in the [reference chapter](#configuration-reference).

### Prepare environment variables

Environment variables used by OrangeHRM portal runner for secret management:

- `ORANGE_HRM_STAGING_USERNAME` - OrangeHRM portal staging username
- `ORANGE_HRM_STAGING_PASSWORD` - OrangeHRM portal staging password

Note: `staging` term is used to make it explicit that this has nothing to do with production.

As an alternative, portal runner also supports `.env` file for loading variables - rename `.env.example` from the root directory to `.env` and edit it, setting values for the variables.

SauceDemo portal does not require any environment variables.

### Building runner image with Docker

There is a `compose.yaml` file at the project root with services listed below:

- `runner` - root orchestrator and portal runners. Requires docker image built (see below) and [input data generated](#generate-input-data).
- `maildev` - simple mail server with web interface. Does not require docker build.

`runner` service can be built with:

```sh
docker compose build runner
```

### Starting maildev server

```sh
docker compose up -d maildev
```

After it was started, its UI can be accessed at http://localhost:1080

### Generate input data

Requires `runner` service to be built.

```sh
docker compose run --rm runner generate-demo-input
```

This will generate input files for all configured portals.

#### OrangeHRM

File: `input/orange_hrm.json` (see [OrangeHRM portal](#orangehrm) section). The data will consist of:

- 5 random employees with emails from OrangeHRM portal
  - 2 of them will remain unchanged (to simulate items in input data fully matching existing ones)
  - 3 of them will have updated middle name
- 10 generated new employees with random data

Note: data on `opensource-demo.orangehrmlive.com` is being changed frequently, so there are no guarantees that between the data dump and portal run the data in OrangeHRM will not change.
However, if the interval between data generation is small enough (a few minutes at most), there should be no issues with that. Also, for better testing items being unchanged, one can make two quick successive runs with the same data.

#### SauceDemo

File: `input/saucedemo.json`. Each input item contains `username`, `first_name`, `last_name`, and `postal_code`.

### Running portal runners

Prerequisites:
- `config.json` [created](#configuring)
- `runner` docker image [built](#building-runner-image-with-docker)
- input data [generated](#generate-input-data)
- if `smtp_server` in `config.json` is not empty - `maildev` should be [running](#starting-maildev-server) (assuming `maildev` is set as `smtp_server.host` - you're free to configure any accessible SMTP server that does not require authentication)

```sh
docker compose run --rm runner
```

To run only a specific portal, use the `--portal` flag:

```sh
docker compose run --rm runner python run.py --portal saucedemo
```

Other CLI options:
- `--config PATH` — config file path. Default: `config.json`.
- `--log-level {DEBUG,INFO,...}` — log level. Default: `INFO`.

### Inspecting results

The database is stored in a mounted volume, so it persists across container runs. You can inspect results both during the runs (to see live data) and after the run is finished.

To see last reports for each portal:
```sh
docker compose run --rm runner make last-reports
```

To inspect errors and output items from the last run per portal:
```sh
docker compose run --rm runner make last-errors
docker compose run --rm runner make last-output
```

## CI pipelines

Two GitHub Actions workflows run on pull requests:

- **Lint** — runs `ruff check` on the codebase.
- **Test** — builds the Docker image and runs unit tests.

## Running unit tests

```sh
docker compose run --rm runner test
```

Note that tests marked with `e2e_staging` (see E2E section below) are not being run
with that command.

## E2E staging tests

End-to-end tests that run against the [live OrangeHRM demo portal](https://opensource-demo.orangehrmlive.com/). They are excluded from the default test run and CI — they only run on explicit request.

These tests were designed to ensure OrangeHRMClient class functionality during development.

### Running

```sh
docker compose run --rm runner test-e2e-staging
```

## Adding a new portal

A portal is a Python package under `portals/<portal_key>/` that exposes `Runner`, `OutputItem`, and `ErrorItem` classes (see [PR #11](https://github.com/side2k/zentist-demo-task/pull/11) for a real example adding SauceDemo).

Steps:

1. Create [`portals/<portal_key>/`](portals/) package with `__init__.py` and `runner.py`.
2. The runner class must extend [`BasePortalRunner`](portals/base_runner.py) and implement `process_batch_item()`. Define portal-specific config ([`BasePortalRunnerConfig`](portals/base_runner.py:33) subclass), input item ([`BasePortalRunnerInputItem`](portals/base_runner.py:72) subclass), and output item ([`BaseItemProcessingResult`](portals/base_runner.py:38) subclass).
3. In `__init__.py`, alias `Runner`, `OutputItem`, `ErrorItem` (use [`PortalItemError`](portals/base_runner.py:64)).
4. Register the portal in [`db/portal_models.py`](db/portal_models.py):`installed_portals` list — this ensures Alembic auto-generates migrations for its output/error tables. Then run `alembic revision --autogenerate -m "<portal_key>_output"` to generate the migration.
5. Add the portal key to your [`config.json`](config.json.example).
6. Run `alembic upgrade head` to create the DB tables.

## Configuration reference

- `portals` - dictionary, every key is a portal key - the orchestrator will look for a portal runner in `portals.<portal_key>.Runner`. Supported portal keys: `orange_hrm`, `saucedemo`. Example usage:
```json
  "portals": {
    "orange_hrm": {},
    "saucedemo": {}
  }
```
(in the example above empty dictionaries mean the runner will use only default config)

All portals share these base config options (overridable per portal):

- `retries` — total number of processing attempts (including the first one) for recoverable item errors. Default: `10`.
- `retry_interval_seconds` — pause between retries. Default: `10`.

Portal-specific config options:

- `orange_hrm`:
  - `proxy` — HTTP proxy URL (e.g. `http://proxy:8080`). Optional.
  - `tracing_enabled` — enable aiohttp request/response content debug tracing. Default: `false`.
- `saucedemo`:
  - `headless` — run browser in headless mode. Default: `true`.
- `smtp_server` - SMTP server for sending emails. In the sample config it is set to [maildev](#starting-maildev-server). For now, SMTP authentication isn't supported. Example usage:
```json
  "smtp_server": {
    "host": "maildev",
    "port": 1025
  },
```
- `report_to` - list of email recipients to send finished runs' reports to. Example usage:
```json
  "report_to": ["someone@portalrunner.test"],
```

