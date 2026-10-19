from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "production_backup_restore_drill.sh"
)


def test_scratch_output_volume_is_populated_and_verified_in_containers():
    script = SCRIPT.read_text(encoding="utf-8")

    assert "RESTORE_OUTPUT_PATH=" not in script
    assert 'tar -C "${RESTORE_OUTPUT_PATH}"' not in script
    assert 'python3 "${VERIFY_SCRIPT}" manifest "${RESTORE_OUTPUT_PATH}"' not in script
    assert 'python3 "${VERIFY_SCRIPT}" validate "${RESTORE_OUTPUT_PATH}"' not in script
    assert (
        'type=volume,source=${RESTORE_OUTPUT_VOLUME},target=/restore/outputs"'
        in script
    )
    assert "tar -C /restore/outputs -xzf /restore/outputs.tar.gz" in script
    assert "restore_output_helper readonly python /restore-verify.py manifest" in script
    assert "restore_output_helper readonly python /restore-verify.py validate" in script


def test_systemd_keeps_docker_volume_host_paths_read_only():
    unit = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "systemd"
        / "geovis-offhost-backup.service"
    ).read_text(encoding="utf-8")

    assert "ReadOnlyPaths=/var/lib/docker/volumes" in unit
    assert "ReadWritePaths=/var/lib/docker/volumes" not in unit
