"""Unit tests for the gailz-action entrypoint polling logic."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, json_body: dict, headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.headers = headers or {}
    return resp


# ---------------------------------------------------------------------------
# build_check_request
# ---------------------------------------------------------------------------

class TestBuildCheckRequest:
    def test_constructs_repo_url_from_github_repository(self) -> None:
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "my-org/my-repo", "GITHUB_SHA": "abc123"}):
            from entrypoint import build_check_request
            result = build_check_request()
        assert result == {
            "repo_url": "https://github.com/my-org/my-repo",
            "commit_sha": "abc123",
        }

    def test_raises_when_github_repository_missing(self) -> None:
        env = {"GITHUB_SHA": "abc123"}
        env.pop("GITHUB_REPOSITORY", None)
        with patch.dict(os.environ, env, clear=True):
            import importlib
            import entrypoint
            importlib.reload(entrypoint)
            with pytest.raises(SystemExit):
                from entrypoint import build_check_request
                build_check_request()


# ---------------------------------------------------------------------------
# evaluate_response
# ---------------------------------------------------------------------------

class TestEvaluateResponse:
    def test_pass_exits_0(self) -> None:
        resp = _mock_response(200, {
            "status": "pass",
            "total_technical_actions": 5,
            "not_met_count": 0,
            "partially_met_count": 0,
        })
        from entrypoint import evaluate_response
        with pytest.raises(SystemExit) as exc:
            evaluate_response(resp)
        assert exc.value.code == 0

    def test_fail_exits_1(self) -> None:
        resp = _mock_response(200, {
            "status": "fail",
            "total_technical_actions": 5,
            "not_met_count": 2,
            "partially_met_count": 1,
        })
        from entrypoint import evaluate_response
        with pytest.raises(SystemExit) as exc:
            evaluate_response(resp)
        assert exc.value.code == 1

    def test_404_exits_1(self) -> None:
        resp = _mock_response(404, {"error_code": "REPO_NOT_FOUND", "message": "repo not registered in gailz"})
        from entrypoint import evaluate_response
        with pytest.raises(SystemExit) as exc:
            evaluate_response(resp)
        assert exc.value.code == 1

    def test_403_key_invalid_exits_1(self) -> None:
        resp = _mock_response(403, {"error_code": "KEY_INVALID", "message": "invalid or revoked API key"})
        from entrypoint import evaluate_response
        with pytest.raises(SystemExit) as exc:
            evaluate_response(resp)
        assert exc.value.code == 1

    def test_403_key_not_authorised_exits_1(self) -> None:
        resp = _mock_response(403, {"error_code": "KEY_NOT_AUTHORISED", "message": "not authorised"})
        from entrypoint import evaluate_response
        with pytest.raises(SystemExit) as exc:
            evaluate_response(resp)
        assert exc.value.code == 1

    def test_409_exits_1(self) -> None:
        resp = _mock_response(409, {"error_code": "NO_CLASSIFICATION", "message": "no classification"})
        from entrypoint import evaluate_response
        with pytest.raises(SystemExit) as exc:
            evaluate_response(resp)
        assert exc.value.code == 1

    def test_503_returns_retry_after(self) -> None:
        resp = _mock_response(503, {"message": "Analysis pending"}, headers={"Retry-After": "30"})
        from entrypoint import evaluate_response
        result = evaluate_response(resp)
        assert result == 30  # retry after N seconds


# ---------------------------------------------------------------------------
# poll_gate
# ---------------------------------------------------------------------------

class TestPollGate:
    def test_returns_immediately_on_200(self) -> None:
        pass_resp = _mock_response(200, {"status": "pass", "total_technical_actions": 0,
                                        "not_met_count": 0, "partially_met_count": 0})
        with patch("requests.post", return_value=pass_resp), \
             patch("time.sleep") as mock_sleep:
            from entrypoint import poll_gate
            with pytest.raises(SystemExit) as exc:
                poll_gate(
                    api_url="https://api.example.com",
                    api_key="gailz_testkey",
                    payload={"repo_url": "https://github.com/org/repo", "commit_sha": "abc"},
                    timeout_seconds=600,
                )
            assert exc.value.code == 0
            mock_sleep.assert_not_called()

    def test_retries_on_503_then_passes(self) -> None:
        pending_resp = _mock_response(503, {"message": "pending"}, headers={"Retry-After": "1"})
        pass_resp = _mock_response(200, {"status": "pass", "total_technical_actions": 0,
                                        "not_met_count": 0, "partially_met_count": 0})
        with patch("requests.post", side_effect=[pending_resp, pass_resp]), \
             patch("time.sleep"):
            from entrypoint import poll_gate
            with pytest.raises(SystemExit) as exc:
                poll_gate(
                    api_url="https://api.example.com",
                    api_key="gailz_testkey",
                    payload={"repo_url": "https://github.com/org/repo", "commit_sha": "abc"},
                    timeout_seconds=600,
                )
            assert exc.value.code == 0

    def test_exits_1_on_timeout(self) -> None:
        pending_resp = _mock_response(503, {"message": "pending"}, headers={"Retry-After": "30"})
        with patch("requests.post", return_value=pending_resp), \
             patch("time.sleep"), \
             patch("time.monotonic", side_effect=[0, 9999]):
            from entrypoint import poll_gate
            with pytest.raises(SystemExit) as exc:
                poll_gate(
                    api_url="https://api.example.com",
                    api_key="gailz_testkey",
                    payload={"repo_url": "https://github.com/org/repo", "commit_sha": "abc"},
                    timeout_seconds=60,
                )
            assert exc.value.code == 1

    def test_exits_1_on_network_error(self) -> None:
        import requests
        with patch("requests.post", side_effect=requests.ConnectionError("refused")):
            from entrypoint import poll_gate
            with pytest.raises(SystemExit) as exc:
                poll_gate(
                    api_url="https://api.example.com",
                    api_key="gailz_testkey",
                    payload={"repo_url": "https://github.com/org/repo", "commit_sha": "abc"},
                    timeout_seconds=60,
                )
            assert exc.value.code == 1
