from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Phase 3 smoke check against a RetainAI deployment.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL for the RetainAI API.")
    parser.add_argument("--email", help="User email for an authenticated smoke check.")
    parser.add_argument("--password", help="User password for an authenticated smoke check.")
    parser.add_argument("--timeout", type=float, default=15.0, help="Per-request timeout in seconds.")
    return parser.parse_args()


def require_ok(response: httpx.Response, label: str) -> Any:
    if response.status_code >= 400:
        raise RuntimeError(f"{label} failed with status {response.status_code}: {response.text}")
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        return response.json()
    return response.text


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")

    summary: dict[str, Any] = {}
    headers: dict[str, str] = {"X-Request-ID": "phase3-smoke-check"}

    with httpx.Client(timeout=args.timeout, follow_redirects=True) as client:
        summary["health"] = require_ok(client.get(f"{base_url}/health", headers=headers), "health")
        summary["readyz"] = require_ok(client.get(f"{base_url}/readyz", headers=headers), "readyz")

        metrics_response = client.get(f"{base_url}/metrics", headers=headers)
        metrics_text = require_ok(metrics_response, "metrics")
        if "retainai_http_requests_total" not in metrics_text:
            raise RuntimeError("metrics endpoint did not include retainai_http_requests_total")
        summary["metrics"] = {"sampled": True, "content_length": len(metrics_text)}

        if args.email and args.password:
            login = require_ok(
                client.post(
                    f"{base_url}/api/v1/auth/login",
                    json={"email": args.email, "password": args.password},
                    headers=headers,
                ),
                "auth.login",
            )
            token = login["access_token"]
            auth_headers = {**headers, "Authorization": f"Bearer {token}"}
            summary["auth_me"] = require_ok(client.get(f"{base_url}/api/v1/auth/me", headers=auth_headers), "auth.me")
            summary["runtime_status"] = require_ok(
                client.get(f"{base_url}/api/v1/ops/runtime-status", headers=auth_headers),
                "ops.runtime-status",
            )
            summary["worker_health"] = require_ok(
                client.get(f"{base_url}/api/v1/ops/worker-health", headers=auth_headers),
                "ops.worker-health",
            )
            summary["logout"] = require_ok(
                client.post(f"{base_url}/api/v1/auth/logout", headers=auth_headers),
                "auth.logout",
            )

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
