# gailz-action

GitHub Action that gates releases on compliance status from the [Gailz](https://github.com/your-org/gailz-ui) platform.

## Usage

Add to your release workflow:

```yaml
jobs:
  compliance-gate:
    runs-on: ubuntu-latest
    steps:
      - name: Compliance gate
        uses: your-org/gailz-action@v1
        with:
          api_url: ${{ secrets.GAILZ_API_URL }}
          api_key: ${{ secrets.GAILZ_API_KEY }}
```

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `api_url` | yes | — | Base URL of the gailz-ai API |
| `api_key` | yes | — | API key (create in gailz under API Keys) |
| `timeout_minutes` | no | `30` | Max minutes to wait for analysis |

## Secrets required

Add these as repository secrets (Settings → Secrets → Actions):

- `GAILZ_API_URL` — e.g. `https://api.gailz.example.com`
- `GAILZ_API_KEY` — generated in gailz admin under API Keys

## Prerequisites

1. The repo must be registered in gailz as a Use Case with the correct `github_repository_url`
2. The use case must have been classified at least once
3. An API key must be created and scoped to that use case

## Exit codes

- `0` — gate passed (no blocking compliance actions)
- `1` — gate failed, timed out, or configuration error (check logs for details)
