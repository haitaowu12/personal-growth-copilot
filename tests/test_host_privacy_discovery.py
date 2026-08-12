from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import host_privacy_discovery  # noqa: E402
import release_evidence  # noqa: E402
import release_packet  # noqa: E402


CANDIDATE = "a" * 40
FIXED_TIME = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def runner(
    encryption: bytes = b"FileVault is On.\n",
    backup: bytes = b"tmutil: No destinations configured.\n",
    acl: bytes = b"drwx------  2 owner  staff  64 Aug 12 12:00 private-storage\n",
    *,
    encryption_exit: int = 0,
    acl_exit: int = 0,
) -> host_privacy_discovery.CommandRunner:
    def run(command_id: str, _: object) -> host_privacy_discovery.CommandResult:
        if command_id == "filevault_status":
            return host_privacy_discovery.CommandResult(
                command_id, encryption_exit, encryption, b""
            )
        if command_id == "time_machine_destination":
            return host_privacy_discovery.CommandResult(command_id, 1, b"", backup)
        if command_id in {"storage_acl", "output_parent_acl"}:
            return host_privacy_discovery.CommandResult(
                command_id, acl_exit, acl, b""
            )
        raise AssertionError(command_id)

    return run


class HostPrivacyDiscoveryTests(unittest.TestCase):
    def root(self, parent: Path, name: str = "private-storage") -> Path:
        path = parent / name
        path.mkdir(mode=0o700)
        os.chmod(path, 0o700)
        return path

    def discover(
        self,
        storage_root: Path,
        *,
        sync_roots: list[Path] | None = None,
        sync_inventory_complete: bool = True,
        command_runner: host_privacy_discovery.CommandRunner | None = None,
    ) -> dict[str, object]:
        return host_privacy_discovery.discover(
            storage_root=storage_root,
            named_host="restricted-local-host",
            environment_id="pgc-private-evaluation-001",
            sync_roots=sync_roots or [],
            sync_inventory_complete=sync_inventory_complete,
            source_identity=lambda _: CANDIDATE,
            clock=lambda: FIXED_TIME,
            runner=command_runner or runner(),
            platform_system=lambda: "Darwin",
            platform_release=lambda: "25.6.0",
            platform_machine=lambda: "arm64",
            home_root=lambda: storage_root.parent,
        )

    def checks(self, report: dict[str, object]) -> dict[str, dict[str, object]]:
        return {
            item["check_id"]: item
            for item in report["checks"]  # type: ignore[index,union-attr]
        }

    def test_discovery_is_hash_bound_and_never_authorizes_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            parent = Path(directory_name).resolve()
            storage = self.root(parent)
            sync = self.root(parent, "declared-sync")
            report = self.discover(storage, sync_roots=[sync])
            checks = self.checks(report)
            self.assertEqual(checks["storage_map"]["status"], "PASS")
            self.assertEqual(checks["encryption"]["status"], "PASS")
            self.assertEqual(checks["no_sync"]["status"], "PASS")
            self.assertEqual(checks["backup_restore"]["status"], "FAIL")
            for check_id in (
                "correction_export_deletion",
                "bounded_retention",
                "incident_response",
            ):
                self.assertEqual(checks[check_id]["status"], "UNKNOWN")
            self.assertEqual(report["status"], "NOT_READY")
            self.assertFalse(report["privacy_gate_ready"])
            self.assertFalse(report["persistent_adapter_authorized"])
            self.assertEqual(
                report["report_sha256"],
                release_evidence.object_hash(report, "report_sha256"),
            )
            self.assertEqual(
                release_evidence.schema_errors(report, "host_privacy_discovery"),
                [],
            )
            self.assertEqual(host_privacy_discovery.verify_report(report), [])
            duplicate = json.loads(json.dumps(report))
            duplicate["checks"][1]["check_id"] = "storage_map"
            self.assertTrue(
                release_evidence.schema_errors(
                    duplicate, "host_privacy_discovery"
                )
            )
            self.assertTrue(host_privacy_discovery.verify_report(duplicate))
            tampered = json.loads(json.dumps(report))
            tampered["named_host"] = "other-host"
            self.assertIn(
                "host discovery report self-hash mismatch",
                host_privacy_discovery.verify_report(tampered),
            )
            serialized = release_evidence.canonical_bytes(report)
            self.assertNotIn(b"FileVault is On", serialized)
            self.assertNotIn(b"No destinations configured", serialized)

    def test_no_sync_fails_on_overlap_and_stays_unknown_without_complete_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            parent = Path(directory_name).resolve()
            sync = self.root(parent, "sync")
            storage = self.root(sync, "storage")
            overlap = self.discover(storage, sync_roots=[sync])
            self.assertEqual(self.checks(overlap)["no_sync"]["status"], "FAIL")
            nested_sync = self.root(storage, "nested-sync")
            nested = self.discover(storage, sync_roots=[nested_sync])
            self.assertEqual(self.checks(nested)["no_sync"]["status"], "FAIL")
            unknown = self.discover(
                storage,
                sync_roots=[],
                sync_inventory_complete=False,
            )
            self.assertEqual(self.checks(unknown)["no_sync"]["status"], "UNKNOWN")
            unavailable = self.discover(
                storage,
                sync_roots=[parent / "missing-sync-root"],
                sync_inventory_complete=True,
            )
            unavailable_check = self.checks(unavailable)["no_sync"]
            self.assertEqual(unavailable_check["status"], "UNKNOWN")
            self.assertIn(
                "DECLARED_SYNC_ROOT_UNAVAILABLE",
                unavailable_check["reason_codes"],
            )

    def test_unobservable_or_disabled_encryption_never_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            storage = self.root(Path(directory_name).resolve())
            unavailable = self.discover(
                storage,
                command_runner=runner(
                    b"", b"No destinations configured", encryption_exit=1
                ),
            )
            self.assertEqual(
                self.checks(unavailable)["encryption"]["status"], "UNKNOWN"
            )
            disabled = self.discover(
                storage,
                command_runner=runner(b"FileVault is Off.\n"),
            )
            self.assertEqual(self.checks(disabled)["encryption"]["status"], "FAIL")

    def test_storage_permissions_symlinks_and_source_repository_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            parent = Path(directory_name).resolve()
            storage = self.root(parent)
            os.chmod(storage, 0o755)
            broad = self.discover(storage)
            self.assertEqual(self.checks(broad)["storage_map"]["status"], "FAIL")
            os.chmod(storage, 0o700)
            alias = parent / "alias"
            alias.symlink_to(storage, target_is_directory=True)
            linked = self.discover(alias)
            self.assertEqual(self.checks(linked)["storage_map"]["status"], "FAIL")

            original_root = host_privacy_discovery.ROOT
            try:
                host_privacy_discovery.ROOT = parent
                inside = self.discover(storage)
            finally:
                host_privacy_discovery.ROOT = original_root
            self.assertEqual(self.checks(inside)["storage_map"]["status"], "FAIL")

    def test_storage_and_output_acl_boundaries_fail_closed(self) -> None:
        acl_output = (
            b"drwx------+ 2 owner staff 64 Aug 12 12:00 private-storage\n"
            b" 0: everyone allow list,search,readattr,file_inherit,directory_inherit\n"
        )
        with tempfile.TemporaryDirectory() as directory_name:
            parent = Path(directory_name).resolve()
            storage = self.root(parent)
            exposed = self.discover(
                storage,
                command_runner=runner(acl=acl_output),
            )
            storage_check = self.checks(exposed)["storage_map"]
            self.assertEqual(storage_check["status"], "FAIL")
            self.assertIn("STORAGE_ROOT_ACL_PRESENT", storage_check["reason_codes"])
            output_parent = self.root(parent, "output")
            with self.assertRaisesRegex(
                host_privacy_discovery.HostDiscoveryError,
                "access control list",
            ):
                host_privacy_discovery.validate_private_output(
                    output_parent / "report.json",
                    runner=runner(acl=acl_output),
                    system="Darwin",
                )
            unknown = self.discover(
                storage,
                command_runner=runner(acl_exit=1),
            )
            unknown_check = self.checks(unknown)["storage_map"]
            self.assertEqual(unknown_check["status"], "FAIL")
            self.assertIn(
                "STORAGE_ROOT_ACL_UNOBSERVABLE",
                unknown_check["reason_codes"],
            )

    def test_discovery_output_is_private_create_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            parent = Path(directory_name).resolve()
            storage = self.root(parent)
            output_parent = self.root(parent, "evidence")
            report = self.discover(storage)
            output = output_parent / "host-discovery.json"
            host_privacy_discovery.validate_private_output(output)
            release_packet.write_private_new(output, report)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(json.loads(output.read_text()), report)
            with self.assertRaises(FileExistsError):
                release_packet.write_private_new(output, report)

    def test_discovery_output_boundary_rejects_broad_or_repository_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            parent = Path(directory_name).resolve()
            os.chmod(parent, 0o755)
            with self.assertRaisesRegex(
                host_privacy_discovery.HostDiscoveryError, "mode 0700"
            ):
                host_privacy_discovery.validate_private_output(parent / "report.json")
        with tempfile.TemporaryDirectory(dir=ROOT) as repository_directory:
            repository_parent = Path(repository_directory)
            os.chmod(repository_parent, 0o700)
            with self.assertRaisesRegex(
                host_privacy_discovery.HostDiscoveryError, "source repository"
            ):
                host_privacy_discovery.validate_private_output(
                    repository_parent / "host-discovery-should-not-exist.json"
                )

    def test_missing_storage_root_produces_not_ready_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            storage = Path(directory_name).resolve() / "missing"
            report = self.discover(storage)
            checks = self.checks(report)
            self.assertEqual(checks["storage_map"]["status"], "FAIL")
            self.assertEqual(checks["no_sync"]["status"], "FAIL")
            self.assertEqual(
                report["storage_root_sha256"],
                host_privacy_discovery.path_identity(storage),
            )

    def test_malformed_identity_and_clock_fail_with_domain_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            storage = self.root(Path(directory_name).resolve())
            with self.assertRaisesRegex(
                host_privacy_discovery.HostDiscoveryError, "named_host"
            ):
                host_privacy_discovery.discover(
                    storage_root=storage,
                    named_host="",
                    environment_id="pgc-private-evaluation-001",
                    sync_roots=[],
                    sync_inventory_complete=False,
                    source_identity=lambda _: CANDIDATE,
                )
            with self.assertRaisesRegex(
                host_privacy_discovery.HostDiscoveryError, "timezone aware"
            ):
                host_privacy_discovery.discover(
                    storage_root=storage,
                    named_host="host",
                    environment_id="pgc-private-evaluation-001",
                    sync_roots=[],
                    sync_inventory_complete=False,
                    source_identity=lambda _: CANDIDATE,
                    clock=lambda: datetime(2026, 8, 12),
                )


if __name__ == "__main__":
    unittest.main()
