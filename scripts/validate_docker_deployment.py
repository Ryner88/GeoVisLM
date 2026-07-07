from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKER_DESKTOP_CLI = Path("/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe")
DOCKER_DESKTOP_WSL_CLI = Path("/mnt/c/Program Files/Docker/Docker/resources/bin/docker")
TRUSTED_DOCKER_PATHS = {
    Path("/usr/bin/docker"),
    Path("/usr/local/bin/docker"),
    Path("/snap/bin/docker"),
    DOCKER_DESKTOP_CLI,
    DOCKER_DESKTOP_WSL_CLI,
}


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


def trusted_docker_paths() -> set[Path]:
    return {path.resolve() for path in TRUSTED_DOCKER_PATHS if path.exists()}


def docker_command() -> Path:
    docker = shutil.which("docker")
    if docker:
        docker_path = Path(docker).resolve()
        if docker_path not in trusted_docker_paths():
            raise SystemExit(f"Refusing untrusted Docker executable: {docker_path}")
        return docker_path
    if DOCKER_DESKTOP_CLI.exists():
        return DOCKER_DESKTOP_CLI.resolve()
    raise SystemExit(
        "Docker CLI not found. Install Docker, enable Docker Desktop WSL integration, "
        f"or use {DOCKER_DESKTOP_CLI}."
    )


def run_docker_compose_config(docker_path: Path) -> subprocess.CompletedProcess[str]:
    if docker_path.resolve() not in trusted_docker_paths():
        raise SystemExit(f"Refusing untrusted Docker executable: {docker_path}")
    result = subprocess.run(
        ["docker", "compose", "config"],
        executable=str(docker_path),
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return result


def run_compose_config(docker_path: Path) -> None:
    result = run_docker_compose_config(docker_path)
    if result.returncode == 0:
        return

    fallback_path = DOCKER_DESKTOP_CLI.resolve()
    if docker_path != fallback_path and DOCKER_DESKTOP_CLI.exists():
        fallback = run_docker_compose_config(fallback_path)
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
    contains(compose, "${GEOVIS_AUTH_TOKEN:?set GEOVIS_AUTH_TOKEN}")
    contains(compose, "${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}")
    contains(env_example, "GEOVIS_OUTPUT_ROOT")
    contains(env_example, "GEOVIS_AUTH_TOKEN")

    if args.compose_config:
        run_compose_config(docker_command())

    print("Docker deployment scaffold validation passed.")


if __name__ == "__main__":
    main()
