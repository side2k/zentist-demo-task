# Demo task for RPA Principal job application at Zentist

## Purpose

This project is a set of "portal runners". Every portal runner processes a batch of input data items and outputs a status report to the database. Portal runners are managed by the root orchestrator.

## Setting up

### Configuring

Config file name for the orchestrator is `config.json`.
Sample config is in the `config.json.example` - copy it to `config.json` to have a minimal working configuration.

See more details about config in the [reference chapter](#configuration-reference).

### Prepare environment variables

Environment variables used by portal runner for secret management:

- `ORANGE_HRM_STAGING_USERNAME` - OrangeHRM portal staging username
- `ORANGE_HRM_STAGING_PASSWORD` - OrangeHRM portal staging password

Note: `staging` term is used to make it explicit that this has nothing to do with production.

As an alternative, portal runner also supports `.env` file for loading variables - rename `.env.example` from the root directory to `.env` and edit it, setting values for the variables.

### Building runner image with Docker

There is a `compose.yaml` file at the project root with services listed below:

- `runner` - root orchestrator and portal runners. Requires docker image built (see below) and [input data generated](#generate-input-data-for-orangehrm).
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

### Generate input data for OrangeHRM

Requires `runner` service to be built.

```sh
docker compose run --rm runner generate-demo-input
```

This command will generate file `input/orange_hrm.json`. The data will consist of:

- 5 random employees with emails from OrangeHRM portal
  - 2 of them will remain unchanged (to simulate items in input data fully matching existing ones)
  - 3 of them will have updated middle name
- 10 generated new employees with random data

Note: data on `opensource-demo.orangehrmlive.com` is being changed frequently, so there are no guarantees that between the data dump and portal run the data in OrangeHRM will not change.
However, if the interval between data generation is small enough (a few minutes at most), there should be no issues with that. Also, for better testing items being unchanged, one can make two quick successive runs with the same data.

### Running portal runners

Prerequisites:
- `config.json` [created](#configuring)
- `runner` docker image [built](#building-runner-image-with-docker)
- input data [generated](#generate-input-data-for-orangehrm)
- if `smtp_server` in `config.json` is not empty - `maildev` should be [running](#starting-maildev-server) (assuming `maildev` is set as `smtp_server.host` - you're free to configure any accessible SMTP server that does not require authentication)

```sh
docker compose run --rm runner
```

### Watching live reports during run

Prerequisites: `runner` service working in the background:
- can be launched as [described above](#running-portal-runners)
- can be launched explicitly to the background with:
```sh
docker compose up -d runner
```

To see last reports, auto updating every 1 second:
```sh
watch -n 1 docker compose exec runner make last-reports
```

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

## Configuration reference

- `portals` - dictionary, every key is a portal key - the orchestrator will look for a portal runner in `portals.<portal_key>.Runner`. Example usage:
```json
  "portals": {
    "orange_hrm": {}
  }
```
(in the example above empty `orange_hrm` dictionary means `orange_hrm` runner will use only default config)
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

