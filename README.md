# Demo task for RPA Principal job application at Zentist

## Running unit tests

```
make test
```

Note that tests marked with `e2e_staging` (see E2E section below) are not being run
with that command.

## E2E staging tests

End-to-end tests that run against the [live OrangeHRM demo portal](https://opensource-demo.orangehrmlive.com/). They are excluded from the default test run and CI — they only run on explicit request.

These tests were designed to ensure OrangeHRMClient class functionality during development.

### Setup

Copy `.env.example` to `.env` and fill in the credentials:

### Running

```sh
make test-e2e-staging
```
