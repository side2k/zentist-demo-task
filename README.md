# Demo task for RPA Principal job application at Zentist

## E2E staging tests

End-to-end tests that run against the [live OrangeHRM demo portal](https://opensource-demo.orangehrmlive.com/). They are excluded from the default test run and CI — they only run on explicit request.

### Setup

Copy `.env.example` to `.env` and fill in the credentials:

### Running

```sh
make test-e2e-staging
```
