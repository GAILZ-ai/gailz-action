#!/usr/bin/env python3
"""Entrypoint for the gailz compliance release gate GitHub Action.

Reads GITHUB_REPOSITORY and GITHUB_SHA from the environment (injected by
GitHub Actions), then polls POST /release-gate/check until analysis is
complete or the timeout is reached.
"""

from __future__ import annotations

import os
import sys
import time

import requests


# ---------------------------------------------------------------------------
# Public helpers (imported in tests)
# ---------------------------------------------------------------------------

def build_check_request() -> dict:
    """Build the request payload from GitHub environment variables.

    Returns:
        Dict with repo_url and commit_sha.

    Raises:
        SystemExit: If required environment variables are missing.
    """
    repo = os.environ.get("GITHUB_REPOSITORY")
    sha = os.environ.get("GITHUB_SHA")
    if not repo or not sha:
        print("ERROR: GITHUB_REPOSITORY and GITHUB_SHA must be set.", file=sys.stderr)
        sys.exit(1)
    return {
        "repo_url": f"https://github.com/{repo}",
        "commit_sha": sha,
    }


def evaluate_response(resp: requests.Response) -> int | None:
    """Evaluate a response from the gate API.

    Returns:
        int: Retry-After seconds if the response is 503 (caller should sleep).
        None is never returned for terminal responses — they raise SystemExit.

    Raises:
        SystemExit(0): Analysis complete, gate passed.
        SystemExit(1): Analysis complete, gate failed or unrecoverable error.
    """
    if resp.status_code == 200:
        data = resp.json()
        gate_status = data.get("status")
        total = data.get("total", 0)
        outstanding = data.get("outstanding", 0)
        overrides = data.get("overrides", {})
        accepted = overrides.get("accepted", 0)
        false_positive = overrides.get("false_positive", 0)
        if gate_status == "pass":
            print(f"Compliance gate: PASS ({total} technical actions, all met or overridden)")
            sys.exit(0)
        else:
            print(
                f"Compliance gate: FAIL — {outstanding} outstanding actions "
                f"(of {total} total; {accepted} accepted, {false_positive} false positive). "
                f"Review findings in gailz."
            )
            sys.exit(1)

    if resp.status_code == 503:
        retry_after = int(resp.headers.get("Retry-After", "30"))
        print(f"Analysis pending — retrying in {retry_after}s...")
        return retry_after

    if resp.status_code == 404:
        print("ERROR: Repo not registered in gailz. Add a use case with this repo URL.", file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 403:
        error_code = resp.json().get("error_code", "")
        if error_code == "KEY_NOT_AUTHORISED":
            print("ERROR: API key is not authorised for this repo's use case.", file=sys.stderr)
        else:
            print("ERROR: Invalid or revoked API key.", file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 409:
        print(
            "ERROR: Use case has no classification yet. "
            "Run a classification in gailz before using the release gate.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"ERROR: Unexpected response from gailz API: {resp.status_code}", file=sys.stderr)
    sys.exit(1)


def poll_gate(
    api_url: str,
    api_key: str,
    payload: dict,
    timeout_seconds: int,
) -> None:
    """Poll the gate endpoint until a terminal result or timeout.

    Args:
        api_url: Base URL of the gailz-ai API.
        api_key: Bearer API key.
        payload: Request body (repo_url + commit_sha).
        timeout_seconds: Maximum total seconds to wait.

    Raises:
        SystemExit(0): Gate passed.
        SystemExit(1): Gate failed, error, or timeout.
    """
    deadline = time.monotonic() + timeout_seconds
    url = f"{api_url.rstrip('/')}/release-gate/check"
    headers = {"Authorization": f"Bearer {api_key}"}

    while True:
        if time.monotonic() >= deadline:
            print(
                f"ERROR: Analysis did not complete within {timeout_seconds // 60} minutes.",
                file=sys.stderr,
            )
            sys.exit(1)

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
        except requests.RequestException as exc:
            print(f"ERROR: Could not reach gailz API at {url}: {exc}", file=sys.stderr)
            sys.exit(1)

        retry_after = evaluate_response(resp)
        if retry_after is not None:
            time.sleep(retry_after)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    api_url = os.environ.get("GAILZ_API_URL", "")
    api_key = os.environ.get("GAILZ_API_KEY", "")
    timeout_minutes = int(os.environ.get("GAILZ_TIMEOUT_MINUTES", "30"))

    if not api_url or not api_key:
        print("ERROR: GAILZ_API_URL and GAILZ_API_KEY must be set.", file=sys.stderr)
        sys.exit(1)

    payload = build_check_request()
    poll_gate(
        api_url=api_url,
        api_key=api_key,
        payload=payload,
        timeout_seconds=timeout_minutes * 60,
    )
