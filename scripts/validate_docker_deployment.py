from __future__ import annotations

from pathlib import Path
import argparse
import shutil
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKER_DESKTOP_CLI = Path("/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe")


def require_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Missing required deployment file: {path}")


def contains(path: Path, expected: str) -> None:
    text = path.read_text(encoding="utf-8")
    if expected not in text:
        raise SystemExit(f"{path} does not contain expected text: {expected}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate GeoVisLM Docker deployment scaffold.")
    parser.add_argument(
        "--compose-config",
        action="store_true",
        help="Also run 'docker compose config' when Docker Compose is available.",
    )
    return parser.parse_args()


def docker_command() -> list[str]:
    docker = shutil.which("docker")
    if docker:
        return [docker]
    if DOCKER_DESKTOP_CLI.exists():
        return [str(DOCKER_DESKTOP_CLI)]
    raise SystemExit(
        "Docker CLI not found. Install Docker, enable Docker Desktop WSL integration, "
        f"or use {DOCKER_DESKTOP_CLI}."
    )


def run_compose_config(command: list[str]) -> None:
    result = subprocess.run(
        [*command, "compose", "config"],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode == 0:
        return

    if command != [str(DOCKER_DESKTOP_CLI)] and DOCKER_DESKTOP_CLI.exists():
        fallback = subprocess.run(
            [str(DOCKER_DESKTOP_CLI), "compose", "config"],
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if fallback.returncode == 0:
            return
        raise SystemExit(fallback.stdout)

    raise SystemExit(result.stdout)


def main() -> None:
    args = parse_args()
    dockerfile = PROJECT_ROOT / "Dockerfile"
    compose = PROJECT_ROOT / "docker-compose.yml"
    env_example = PROJECT_ROOT / ".env.example"
    for path in (dockerfile, compose, env_example):
        require_file(path)

    contains(dockerfile, "uvicorn")
    contains(compose, "postgis/postgis")
    contains(compose, "worker:")
    contains(compose, "--loop")
    contains(compose, "geovis_outputs")
    contains(compose, "/readyz")
    contains(env_example, "GEOVIS_OUTPUT_ROOT")
    contains(env_example, "GEOVIS_AUTH_TOKEN")

    if args.compose_config:
        run_compose_config(docker_command())

    print("Docker deployment scaffold validation passed.")


if __name__ == "__main__":
    main()
