#!/usr/bin/env python3
"""Render the Kubernetes base with AWS ECR images and a public hostname."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def run(command: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, input=stdin, capture_output=True, text=True, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ecr-repositories-json", required=True, help="JSON from tofu output -json ecr_repository_urls")
    parser.add_argument("--hostname", required=True, help="Public DNS hostname")
    parser.add_argument("--image-tag", required=True, help="Immutable image tag, usually a Git SHA")
    args = parser.parse_args()

    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", args.hostname):
        print("Invalid public hostname", file=sys.stderr)
        return 1
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", args.image_tag):
        print("Invalid image tag", file=sys.stderr)
        return 1
    try:
        repositories = json.loads(args.ecr_repositories_json)
        if set(repositories) != {"backend", "worker", "frontend", "collab"}:
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        print("ECR repositories must be the exact OpenTofu JSON output", file=sys.stderr)
        return 1

    base = Path(__file__).resolve().parent / "base"
    rendered = run(["kubectl", "kustomize", str(base)])
    if rendered.returncode:
        print(rendered.stderr, file=sys.stderr)
        return rendered.returncode
    manifest = rendered.stdout.replace("agentspace.internal", args.hostname)
    for name, repository in repositories.items():
        manifest = manifest.replace(f"agentspace/{name}:0.1.0", f"{repository}:{args.image_tag}")
    applied = run(["kubectl", "apply", "--server-side", "-f", "-"], stdin=manifest)
    if applied.stdout:
        print(applied.stdout, end="")
    if applied.returncode:
        print(applied.stderr, file=sys.stderr)
    return applied.returncode


if __name__ == "__main__":
    raise SystemExit(main())
