#!/usr/bin/env python3
"""Fail closed on mutable Actions pins and persisted checkout credentials."""
from __future__ import annotations

import re
import sys
from pathlib import Path

USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*(\S+?)(?:\s+#.*)?\s*$")
IMAGE_RE = re.compile(r"^\s*image:\s*(\S+?)(?:\s+#.*)?\s*$")
ACTION_SHA_RE = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*@[0-9a-fA-F]{40}$"
)
DOCKER_DIGEST_RE = re.compile(r"^docker://\S+@sha256:[0-9a-fA-F]{64}$")
OCI_DIGEST_RE = re.compile(r"^\S+@sha256:[0-9a-fA-F]{64}$")
STEP_START_RE = re.compile(r"^(\s*)-\s*(?:name:|uses:)")
CHECKOUT_USE_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*actions/checkout@")
PERSIST_RE = re.compile(r"^\s*persist-credentials:\s*(\S+)\s*(?:#.*)?$")


def find_unpinned_actions(text: str, filename: str = "<memory>") -> list[str]:
    """Return one diagnostic per unpinned external action reference."""
    problems: list[str] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        match = USES_RE.match(raw_line)
        if not match:
            continue

        reference = match.group(1)
        if reference.startswith(("./", "../")):
            continue
        if reference.startswith("docker://"):
            if DOCKER_DIGEST_RE.fullmatch(reference):
                continue
            problems.append(
                f"{filename}:{line_number}: Docker action must be pinned by sha256 digest: {reference}"
            )
            continue
        if ACTION_SHA_RE.fullmatch(reference):
            continue
        problems.append(
            f"{filename}:{line_number}: external action must use a full 40-character commit SHA: {reference}"
        )
    return problems


def find_unpinned_images(text: str, filename: str = "<memory>") -> list[str]:
    """Require every workflow image reference to use an immutable OCI digest."""
    problems: list[str] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        match = IMAGE_RE.match(raw_line)
        if not match:
            continue
        reference = match.group(1).strip("'\"")
        if OCI_DIGEST_RE.fullmatch(reference):
            continue
        problems.append(
            f"{filename}:{line_number}: container image must be pinned by sha256 digest: {reference}"
        )
    return problems


def find_checkout_steps_without_persist_credentials(
    text: str, filename: str = "<memory>"
) -> list[str]:
    """Require every actions/checkout step to opt out of storing the token in git config."""
    lines = text.splitlines()
    starts = [
        index for index, line in enumerate(lines)
        if STEP_START_RE.match(line)
    ]
    problems: list[str] = []

    for start in starts:
        start_match = STEP_START_RE.match(lines[start])
        assert start_match is not None
        step_indent = len(start_match.group(1))
        end = len(lines)
        for index in range(start + 1, len(lines)):
            candidate = lines[index]
            if not candidate.strip() or candidate.lstrip().startswith("#"):
                continue
            indent = len(candidate) - len(candidate.lstrip())
            if indent == step_indent and candidate.lstrip().startswith("- "):
                end = index
                break

        block = lines[start:end]
        if not any(CHECKOUT_USE_RE.match(line) for line in block):
            continue

        persist = next(
            (match for line in block if (match := PERSIST_RE.match(line))),
            None,
        )
        if persist is None or persist.group(1).strip("'\"").lower() != "false":
            line_number = start + 1
            problems.append(
                f"{filename}:{line_number}: actions/checkout must set persist-credentials: false"
            )
    return problems


def audit_workflows(workflow_root: Path) -> list[str]:
    files = sorted(
        path for path in workflow_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}
    )
    if not files:
        return [f"No workflow YAML files found under {workflow_root}"]

    problems: list[str] = []
    for path in files:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            problems.append(f"{path}: unable to read workflow: {exc}")
            continue
        problems.extend(find_unpinned_actions(content, str(path)))
        problems.extend(find_unpinned_images(content, str(path)))
        problems.extend(find_checkout_steps_without_persist_credentials(content, str(path)))
    return problems


def main() -> int:
    repository_root = Path(__file__).resolve().parents[1]
    workflow_root = repository_root / ".github" / "workflows"
    problems = audit_workflows(workflow_root)
    if problems:
        print("Workflow security policy violations detected:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1

    count = sum(
        1 for path in workflow_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}
    )
    print(
        f"PASS: Actions pins, container digests and checkout credential hygiene verified in {count} workflow files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
