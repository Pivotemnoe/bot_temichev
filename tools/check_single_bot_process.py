#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys


def _process_lines() -> list[tuple[int, str]]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        check=True,
        capture_output=True,
        text=True,
    )
    rows: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        rows.append((pid, command.strip()))
    return rows


def _is_bot_process(command: str) -> bool:
    normalized = " ".join(command.split())
    if "tools/check_single_bot_process.py" in normalized:
        return False
    if " -m compileall " in normalized:
        return False
    return "main.py" in normalized and ("python" in normalized or ".venv/bin/python" in normalized)


def find_bot_processes() -> list[tuple[int, str]]:
    return [(pid, command) for pid, command in _process_lines() if _is_bot_process(command)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check that only one TemichevVet bot process is running for one BOT_TOKEN."
    )
    parser.add_argument("--allow-zero", action="store_true", help="Allow zero bot processes for local CI checks.")
    parser.add_argument(
        "--allow-sandbox-skip",
        action="store_true",
        help="Allow local sandbox environments to skip when process listing is blocked.",
    )
    parser.add_argument("--expected-max", type=int, default=1, help="Maximum expected bot process count.")
    args = parser.parse_args()

    try:
        processes = find_bot_processes()
    except PermissionError as exc:
        if args.allow_sandbox_skip:
            print(f"single bot process check skipped: process list unavailable ({exc})")
            return
        raise

    count = len(processes)
    if count == 0 and args.allow_zero:
        print("single bot process check ok: 0 found")
        return
    if count == 0:
        print("No TemichevVet bot process found.", file=sys.stderr)
        raise SystemExit(1)
    if count > int(args.expected_max):
        print(f"Too many TemichevVet bot processes found: {count}", file=sys.stderr)
        for pid, command in processes:
            print(f"- pid={pid} command={command}", file=sys.stderr)
        raise SystemExit(1)

    pid, _ = processes[0]
    print(f"single bot process check ok: 1 found, pid={pid}")


if __name__ == "__main__":
    main()
