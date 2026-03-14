from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=check,
        text=True,
        capture_output=True,
    )


def wait_for_api(base_url: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    smoke_command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "smoke_check.py"),
        "--base-url",
        base_url,
        "--email",
        "admin@retainai.local",
        "--password",
        "retainai-demo",
    ]
    while time.time() < deadline:
        result = run(smoke_command, check=False)
        if result.returncode == 0:
            print(result.stdout.strip())
            return
        time.sleep(5)
    raise RuntimeError("Compose smoke check timed out before the API became healthy.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bring up the local Compose stack and run a RetainAI smoke check.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL to smoke-check after startup.")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds to wait for the stack to become healthy.")
    parser.add_argument("--skip-build", action="store_true", help="Skip image rebuilds when starting Compose.")
    parser.add_argument("--keep-running", action="store_true", help="Leave the Compose stack up after the smoke check.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    up_command = ["docker", "compose", "up", "-d"]
    if not args.skip_build:
        up_command.append("--build")

    print("Starting RetainAI Compose stack...")
    up = run(up_command, check=False)
    if up.returncode != 0:
        print(up.stdout)
        print(up.stderr, file=sys.stderr)
        raise RuntimeError("docker compose up failed.")

    try:
        wait_for_api(args.base_url, args.timeout)
    finally:
        if not args.keep_running:
            down = run(["docker", "compose", "down", "-v"], check=False)
            if down.returncode != 0:
                print(down.stdout)
                print(down.stderr, file=sys.stderr)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
