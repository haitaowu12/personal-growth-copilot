#!/usr/bin/env python3
"""Record a fail-closed, non-promotional named-host privacy discovery."""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import platform
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_evidence  # noqa: E402


REQUIRED_CHECKS = (
    "storage_map",
    "encryption",
    "no_sync",
    "backup_restore",
    "correction_export_deletion",
    "bounded_retention",
    "incident_response",
)
MAX_COMMAND_BYTES = 65_536
CLAIM_LIMIT = (
    "This report is read-only host discovery. It is not a privacy-preflight PASS, "
    "does not prove sync-inventory completeness, backup recovery, persistent-store "
    "semantics, retention enforcement, incident response, or release readiness, and "
    "does not authorize persistent storage."
)


class HostDiscoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    command_id: str
    exit_code: int
    stdout: bytes
    stderr: bytes


CommandRunner = Callable[[str, Sequence[str]], CommandResult]
FileAclProbe = Callable[[int, str], str]


def native_file_acl_status(descriptor: int, system: str) -> str:
    if system != "Darwin":
        return "UNKNOWN"
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        get_acl = libc.acl_get_fd_np
        get_acl.argtypes = [ctypes.c_int, ctypes.c_int]
        get_acl.restype = ctypes.c_void_p
        free_acl = libc.acl_free
        free_acl.argtypes = [ctypes.c_void_p]
        free_acl.restype = ctypes.c_int
        ctypes.set_errno(0)
        acl = get_acl(descriptor, 0x00000100)
        acl_errno = ctypes.get_errno()
    except (AttributeError, OSError, TypeError, ValueError):
        return "UNKNOWN"
    if not acl:
        return "ABSENT" if acl_errno == errno.ENOENT else "UNKNOWN"
    try:
        return "PRESENT"
    finally:
        free_acl(acl)


@dataclass
class BoundDirectory:
    requested: Path
    resolved: Path
    descriptor: int
    device: int
    inode: int

    def visible_matches(self) -> bool:
        if path_has_symlink_component(self.requested):
            return False
        try:
            visible = self.requested.resolve(strict=True).stat()
            bound = os.fstat(self.descriptor)
        except OSError:
            return False
        return (
            stat.S_ISDIR(visible.st_mode)
            and (visible.st_dev, visible.st_ino) == (self.device, self.inode)
            and (bound.st_dev, bound.st_ino) == (self.device, self.inode)
        )

    def close(self) -> None:
        if self.descriptor >= 0:
            os.close(self.descriptor)
            self.descriptor = -1


def bind_directory(path: Path) -> tuple[BoundDirectory | None, str | None]:
    if path_has_symlink_component(path):
        return None, "SYMLINK"
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except OSError:
        return None, "UNAVAILABLE"
    if not stat.S_ISDIR(metadata.st_mode):
        return None, "NOT_DIRECTORY"
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(resolved, flags)
        bound = os.fstat(descriptor)
    except OSError:
        return None, "UNAVAILABLE"
    binding = BoundDirectory(
        requested=path,
        resolved=resolved,
        descriptor=descriptor,
        device=bound.st_dev,
        inode=bound.st_ino,
    )
    if (bound.st_dev, bound.st_ino) != (metadata.st_dev, metadata.st_ino) or not binding.visible_matches():
        binding.close()
        return None, "CHANGED"
    return binding, None


@dataclass
class ReservedPrivateOutput:
    output: Path
    parent_fd: int
    file_fd: int
    parent_device: int
    parent_inode: int
    file_device: int
    file_inode: int
    system: str
    file_acl_probe: FileAclProbe
    sync_bindings: list[BoundDirectory]
    committed: bool = False

    def require_visible_parent(self) -> None:
        try:
            visible_parent = self.output.parent.stat(follow_symlinks=False)
        except OSError as exc:
            raise HostDiscoveryError("output parent changed after reservation") from exc
        if not stat.S_ISDIR(visible_parent.st_mode) or (
            visible_parent.st_dev,
            visible_parent.st_ino,
        ) != (self.parent_device, self.parent_inode):
            raise HostDiscoveryError("output parent changed after reservation")
        if any(not binding.visible_matches() for binding in self.sync_bindings):
            raise HostDiscoveryError("declared sync root changed after reservation")

    def reserved_name_matches(self) -> bool:
        try:
            visible_file = os.stat(
                self.output.name,
                dir_fd=self.parent_fd,
                follow_symlinks=False,
            )
        except OSError:
            return False
        return stat.S_ISREG(visible_file.st_mode) and (
            visible_file.st_dev,
            visible_file.st_ino,
        ) == (self.file_device, self.file_inode)

    def require_reserved_name(self) -> None:
        if not self.reserved_name_matches():
            raise HostDiscoveryError("reserved output file changed after reservation")

    def secure_bound_file(self, *, require_empty: bool) -> None:
        if self.file_fd < 0:
            raise HostDiscoveryError("reserved output file is closed")
        os.fchmod(self.file_fd, 0o600)
        metadata = os.fstat(self.file_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise HostDiscoveryError("reserved output must remain a regular file")
        if metadata.st_uid != os.geteuid():
            raise HostDiscoveryError("reserved output owner changed")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise HostDiscoveryError("reserved output mode is not 0600")
        if require_empty and metadata.st_size != 0:
            raise HostDiscoveryError("reserved output changed before commit")
        acl = self.file_acl_probe(self.file_fd, self.system)
        if acl == "PRESENT":
            raise HostDiscoveryError("reserved output may not have an access control list")
        if acl != "ABSENT":
            raise HostDiscoveryError("reserved output access control list is unobservable")

    def write(self, value: object) -> None:
        if self.committed:
            raise HostDiscoveryError("reserved output has already been committed")
        self.require_visible_parent()
        self.require_reserved_name()
        bound_parent = os.fstat(self.parent_fd)
        if (bound_parent.st_dev, bound_parent.st_ino) != (
            self.parent_device,
            self.parent_inode,
        ):
            raise HostDiscoveryError("reserved output directory identity changed")
        bound_file = os.fstat(self.file_fd)
        if (bound_file.st_dev, bound_file.st_ino) != (
            self.file_device,
            self.file_inode,
        ):
            raise HostDiscoveryError("reserved output file identity changed")
        self.secure_bound_file(require_empty=True)
        data = release_evidence.canonical_bytes(value)
        os.lseek(self.file_fd, 0, os.SEEK_SET)
        remaining = memoryview(data)
        while remaining:
            written = os.write(self.file_fd, remaining)
            if written <= 0:
                raise HostDiscoveryError("reserved output write made no progress")
            remaining = remaining[written:]
        self.secure_bound_file(require_empty=False)
        written_metadata = os.fstat(self.file_fd)
        if written_metadata.st_size != len(data):
            raise HostDiscoveryError("reserved output size differs from canonical report")
        os.lseek(self.file_fd, 0, os.SEEK_SET)
        captured = bytearray()
        while len(captured) < len(data):
            block = os.read(self.file_fd, min(65_536, len(data) - len(captured)))
            if not block:
                break
            captured.extend(block)
        trailing = os.read(self.file_fd, 1)
        final_metadata = os.fstat(self.file_fd)
        if (
            bytes(captured) != data
            or trailing
            or final_metadata.st_size != len(data)
        ):
            raise HostDiscoveryError("reserved output differs from canonical report")
        self.secure_bound_file(require_empty=False)
        os.fsync(self.file_fd)
        os.close(self.file_fd)
        self.file_fd = -1
        os.fsync(self.parent_fd)
        self.require_visible_parent()
        self.require_reserved_name()
        self.committed = True

    def close(self) -> None:
        if self.file_fd >= 0:
            os.close(self.file_fd)
            self.file_fd = -1
        if not self.committed and self.reserved_name_matches():
            try:
                os.unlink(self.output.name, dir_fd=self.parent_fd)
            except FileNotFoundError:
                pass
        if self.parent_fd >= 0:
            os.close(self.parent_fd)
            self.parent_fd = -1
        for binding in self.sync_bindings:
            binding.close()
        self.sync_bindings.clear()

    def __enter__(self) -> ReservedPrivateOutput:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HostDiscoveryError("host discovery clock must be timezone aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def default_runner(command_id: str, command: Sequence[str]) -> CommandResult:
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            check=False,
            timeout=30,
            env={
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG": "C",
                "LC_ALL": "C",
            },
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return CommandResult(
            command_id,
            -1,
            b"",
            f"{type(exc).__name__}".encode("ascii", errors="replace"),
        )
    return CommandResult(
        command_id,
        result.returncode,
        result.stdout[:MAX_COMMAND_BYTES],
        result.stderr[:MAX_COMMAND_BYTES],
    )


def command_evidence(result: CommandResult) -> dict[str, object]:
    return {
        "command_id": result.command_id,
        "exit_code": result.exit_code,
        "stdout_sha256": digest_bytes(result.stdout),
        "stderr_sha256": digest_bytes(result.stderr),
    }


def check(
    check_id: str,
    status: str,
    observed_at: str,
    reason_codes: Sequence[str],
    *,
    facts: dict[str, bool | int | str] | None = None,
    command: CommandResult | None = None,
) -> dict[str, object]:
    return {
        "check_id": check_id,
        "status": status,
        "observed_at": observed_at,
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "facts": facts or {},
        "command_evidence": command_evidence(command) if command else None,
    }


def path_within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def path_identity(path: Path) -> str:
    """Hash a normalized path without requiring the target to exist."""
    return digest_bytes(str(path.expanduser().absolute()).encode("utf-8"))


def path_has_symlink_component(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def acl_status(
    path: Path,
    *,
    runner: CommandRunner,
    command_id: str,
    system: str,
) -> tuple[str, CommandResult | None]:
    if system != "Darwin":
        return "UNKNOWN", None
    result = runner(command_id, ["/bin/ls", "-lde", str(path)])
    if result.exit_code != 0:
        return "UNKNOWN", result
    output = result.stdout.decode("utf-8", errors="replace")
    lines = output.splitlines()
    first_token = lines[0].split(maxsplit=1)[0] if lines else ""
    has_acl_marker = first_token.endswith("+")
    has_acl_entry = any(re.match(r"^\s*\d+:\s", line) for line in lines[1:])
    return ("PRESENT" if has_acl_marker or has_acl_entry else "ABSENT"), result


def reserve_private_output(
    output: Path,
    *,
    runner: CommandRunner = default_runner,
    system: str | None = None,
    home_root: Path | None = None,
    file_acl_probe: FileAclProbe = native_file_acl_status,
    declared_sync_roots: Sequence[Path] = (),
) -> ReservedPrivateOutput:
    if output.exists() or output.is_symlink():
        raise HostDiscoveryError("output must not already exist")
    parent = output.parent
    if path_has_symlink_component(parent):
        raise HostDiscoveryError("output path may not contain a symlink")
    try:
        resolved_parent = parent.resolve(strict=True)
        metadata = resolved_parent.stat()
    except OSError as exc:
        raise HostDiscoveryError("output parent is unavailable") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise HostDiscoveryError("output parent must be a directory")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise HostDiscoveryError("output parent must have mode 0700")
    if metadata.st_uid != os.geteuid():
        raise HostDiscoveryError("output parent owner must match the current user")
    try:
        home_device = (home_root or Path.home()).resolve(strict=True).stat().st_dev
    except OSError as exc:
        raise HostDiscoveryError("home filesystem is unavailable") from exc
    if metadata.st_dev != home_device:
        raise HostDiscoveryError("output parent must be on the home filesystem")
    if path_within(resolved_parent, ROOT.resolve(strict=True)):
        raise HostDiscoveryError("output must remain outside the source repository")
    output_sync_bindings: list[BoundDirectory] = []
    try:
        for sync_root in declared_sync_roots:
            sync_binding, sync_error = bind_directory(sync_root)
            if sync_binding is None:
                raise HostDiscoveryError(
                    "declared sync root is unsafe or unavailable: "
                    + str(sync_error or "UNKNOWN")
                )
            output_sync_bindings.append(sync_binding)
            if path_within(resolved_parent, sync_binding.resolved) or path_within(
                sync_binding.resolved, resolved_parent
            ):
                raise HostDiscoveryError(
                    "output parent overlaps a declared sync root"
                )
    except Exception:
        for binding in output_sync_bindings:
            binding.close()
        raise
    effective_system = system or platform.system()
    acl, _ = acl_status(
        resolved_parent,
        runner=runner,
        command_id="output_parent_acl",
        system=effective_system,
    )
    if acl == "PRESENT":
        raise HostDiscoveryError("output parent may not have an access control list")
    if acl != "ABSENT":
        raise HostDiscoveryError("output parent access control list is unobservable")
    open_directory_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        open_directory_flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        open_directory_flags |= os.O_NOFOLLOW
    try:
        parent_fd = os.open(resolved_parent, open_directory_flags)
    except Exception:
        for binding in output_sync_bindings:
            binding.close()
        raise
    file_fd = -1
    file_metadata: os.stat_result | None = None
    try:
        bound_parent = os.fstat(parent_fd)
        if (bound_parent.st_dev, bound_parent.st_ino) != (
            metadata.st_dev,
            metadata.st_ino,
        ):
            raise HostDiscoveryError("output parent changed during reservation")
        file_flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW
        file_fd = os.open(output.name, file_flags, 0o600, dir_fd=parent_fd)
        file_metadata = os.fstat(file_fd)
        if (
            not stat.S_ISREG(file_metadata.st_mode)
            or file_metadata.st_uid != os.geteuid()
            or stat.S_IMODE(file_metadata.st_mode) != 0o600
            or file_metadata.st_size != 0
        ):
            raise HostDiscoveryError("reserved output is not a private empty file")
        file_acl = file_acl_probe(file_fd, effective_system)
        if file_acl == "PRESENT":
            raise HostDiscoveryError("reserved output may not have an access control list")
        if file_acl != "ABSENT":
            raise HostDiscoveryError("reserved output access control list is unobservable")
    except Exception:
        if file_fd >= 0:
            os.close(file_fd)
            if file_metadata is not None:
                try:
                    visible_file = os.stat(
                        output.name,
                        dir_fd=parent_fd,
                        follow_symlinks=False,
                    )
                except OSError:
                    visible_file = None
                if visible_file is not None and (
                    visible_file.st_dev,
                    visible_file.st_ino,
                ) == (file_metadata.st_dev, file_metadata.st_ino):
                    try:
                        os.unlink(output.name, dir_fd=parent_fd)
                    except FileNotFoundError:
                        pass
        os.close(parent_fd)
        for binding in output_sync_bindings:
            binding.close()
        raise
    return ReservedPrivateOutput(
        output=output,
        parent_fd=parent_fd,
        file_fd=file_fd,
        parent_device=metadata.st_dev,
        parent_inode=metadata.st_ino,
        file_device=file_metadata.st_dev,
        file_inode=file_metadata.st_ino,
        system=effective_system,
        file_acl_probe=file_acl_probe,
        sync_bindings=output_sync_bindings,
    )


def validate_private_output(
    output: Path,
    *,
    runner: CommandRunner = default_runner,
    system: str | None = None,
    home_root: Path | None = None,
    file_acl_probe: FileAclProbe = native_file_acl_status,
    declared_sync_roots: Sequence[Path] = (),
) -> None:
    with reserve_private_output(
        output,
        runner=runner,
        system=system,
        home_root=home_root,
        file_acl_probe=file_acl_probe,
        declared_sync_roots=declared_sync_roots,
    ):
        pass


def inspect_storage(
    binding: BoundDirectory | None,
    binding_error: str | None,
    observed_at: str,
    *,
    home_root: Path,
    system: str,
    acl_probe: FileAclProbe,
) -> dict[str, object]:
    if binding is None:
        reason = {
            "SYMLINK": "STORAGE_ROOT_SYMLINK",
            "NOT_DIRECTORY": "STORAGE_ROOT_NOT_DIRECTORY",
            "CHANGED": "STORAGE_ROOT_CHANGED",
        }.get(binding_error, "STORAGE_ROOT_UNAVAILABLE")
        return check(
            "storage_map", "FAIL", observed_at, [reason]
        )
    resolved = binding.resolved
    metadata = os.fstat(binding.descriptor)
    reasons: list[str] = []
    if not stat.S_ISDIR(metadata.st_mode):
        reasons.append("STORAGE_ROOT_NOT_DIRECTORY")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        reasons.append("STORAGE_ROOT_MODE_NOT_0700")
    if metadata.st_uid != os.geteuid():
        reasons.append("STORAGE_ROOT_OWNER_MISMATCH")
    try:
        home_device = home_root.resolve(strict=True).stat().st_dev
    except OSError:
        home_device = None
        reasons.append("HOME_FILESYSTEM_UNAVAILABLE")
    if home_device is not None and metadata.st_dev != home_device:
        reasons.append("STORAGE_ROOT_NOT_ON_HOME_FILESYSTEM")
    acl = acl_probe(binding.descriptor, system)
    if acl == "PRESENT":
        reasons.append("STORAGE_ROOT_ACL_PRESENT")
    elif acl != "ABSENT":
        reasons.append("STORAGE_ROOT_ACL_UNOBSERVABLE")
    if not binding.visible_matches():
        reasons.append("STORAGE_ROOT_CHANGED")
    repository = ROOT.resolve(strict=True)
    if path_within(resolved, repository):
        reasons.append("STORAGE_ROOT_INSIDE_SOURCE_REPOSITORY")
    return check(
        "storage_map",
        "FAIL" if reasons else "PASS",
        observed_at,
        reasons or ["PRIVATE_LOCAL_ROOT_OBSERVED"],
        facts={
            "owner_matches": metadata.st_uid == os.geteuid(),
            "mode_0700": stat.S_IMODE(metadata.st_mode) == 0o700,
            "on_home_filesystem": home_device is not None
            and metadata.st_dev == home_device,
            "outside_source_repository": not path_within(resolved, repository),
            "acl_absent": acl == "ABSENT",
            "visible_identity_matches": binding.visible_matches(),
            "device_identity_sha256": digest_bytes(str(metadata.st_dev).encode()),
        },
    )


def inspect_encryption(
    observed_at: str,
    *,
    system: str,
    runner: CommandRunner,
) -> dict[str, object]:
    if system != "Darwin":
        return check(
            "encryption",
            "UNKNOWN",
            observed_at,
            ["ENCRYPTION_PROBE_UNSUPPORTED_PLATFORM"],
        )
    result = runner("filevault_status", ["/usr/bin/fdesetup", "status"])
    normalized = result.stdout.decode("utf-8", errors="replace").strip()
    if result.exit_code == 0 and normalized == "FileVault is On.":
        status, reasons = "PASS", ["FILEVAULT_ON_OBSERVED"]
    elif result.exit_code == 0 and normalized == "FileVault is Off.":
        status, reasons = "FAIL", ["FILEVAULT_OFF_OBSERVED"]
    else:
        status, reasons = "UNKNOWN", ["FILEVAULT_STATUS_UNAVAILABLE"]
    return check(
        "encryption",
        status,
        observed_at,
        reasons,
        command=result,
    )


def inspect_no_sync(
    storage: BoundDirectory | None,
    sync_roots: Sequence[BoundDirectory],
    declared_sync_root_count: int,
    unavailable_sync_roots: int,
    sync_root_symlink: bool,
    inventory_complete: bool,
    observed_at: str,
) -> dict[str, object]:
    if storage is None:
        return check(
            "no_sync", "FAIL", observed_at, ["STORAGE_ROOT_UNAVAILABLE"]
        )
    resolved = storage.resolved
    resolved_sync_roots = [item.resolved for item in sync_roots]
    overlap = any(
        path_within(resolved, item) or path_within(item, resolved)
        for item in resolved_sync_roots
    )
    facts: dict[str, bool | int | str] = {
        "declared_sync_root_count": declared_sync_root_count,
        "resolved_sync_root_count": len(resolved_sync_roots),
        "storage_root_outside_declared_sync_roots": not overlap,
    }
    if sync_root_symlink:
        return check(
            "no_sync", "FAIL", observed_at, ["SYNC_ROOT_SYMLINK"], facts=facts
        )
    if not storage.visible_matches():
        return check(
            "no_sync", "FAIL", observed_at, ["STORAGE_ROOT_CHANGED"], facts=facts
        )
    if any(not item.visible_matches() for item in sync_roots):
        return check(
            "no_sync",
            "UNKNOWN",
            observed_at,
            ["DECLARED_SYNC_ROOT_CHANGED"],
            facts=facts,
        )
    if overlap:
        return check(
            "no_sync",
            "FAIL",
            observed_at,
            ["STORAGE_ROOT_INSIDE_DECLARED_SYNC_ROOT"],
            facts=facts,
        )
    if not inventory_complete:
        return check(
            "no_sync",
            "UNKNOWN",
            observed_at,
            ["SYNC_INVENTORY_NOT_ATTESTED_COMPLETE"],
            facts=facts,
        )
    if unavailable_sync_roots:
        return check(
            "no_sync",
            "UNKNOWN",
            observed_at,
            ["DECLARED_SYNC_ROOT_UNAVAILABLE"],
            facts=facts,
        )
    return check(
        "no_sync",
        "PASS",
        observed_at,
        ["OUTSIDE_COMPLETE_DECLARED_SYNC_INVENTORY"],
        facts=facts,
    )


def inspect_backup(
    observed_at: str,
    *,
    system: str,
    runner: CommandRunner,
) -> dict[str, object]:
    if system != "Darwin":
        return check(
            "backup_restore",
            "UNKNOWN",
            observed_at,
            ["BACKUP_PROBE_UNSUPPORTED_PLATFORM"],
        )
    result = runner("time_machine_destination", ["/usr/bin/tmutil", "destinationinfo"])
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    if "No destinations configured" in output:
        status, reasons = "FAIL", ["NO_BACKUP_DESTINATION"]
    else:
        status, reasons = "UNKNOWN", ["BACKUP_RESTORE_EXERCISE_REQUIRED"]
    return check(
        "backup_restore",
        status,
        observed_at,
        reasons,
        command=result,
    )


def discover(
    *,
    storage_root: Path,
    named_host: str,
    environment_id: str,
    sync_roots: Sequence[Path],
    sync_inventory_complete: bool,
    source_identity: Callable[[Path], str] = release_evidence.source_identity,
    clock: Callable[[], datetime] = now,
    runner: CommandRunner = default_runner,
    platform_system: Callable[[], str] = platform.system,
    platform_release: Callable[[], str] = platform.release,
    platform_machine: Callable[[], str] = platform.machine,
    home_root: Callable[[], Path] = Path.home,
    directory_acl_probe: FileAclProbe = native_file_acl_status,
) -> dict[str, object]:
    if not isinstance(named_host, str) or not named_host.strip():
        raise HostDiscoveryError("named_host is required")
    if not isinstance(environment_id, str) or not environment_id.strip():
        raise HostDiscoveryError("environment_id is required")
    candidate = source_identity(ROOT)
    observed_at = timestamp(clock())
    system = platform_system()
    storage_binding, storage_error = bind_directory(storage_root)
    sync_bindings: list[BoundDirectory] = []
    sync_errors: list[str] = []
    for root in sync_roots:
        binding, binding_error = bind_directory(root)
        if binding is None:
            sync_errors.append(binding_error or "UNAVAILABLE")
        else:
            sync_bindings.append(binding)
    try:
        storage = inspect_storage(
            storage_binding,
            storage_error,
            observed_at,
            home_root=home_root(),
            system=system,
            acl_probe=directory_acl_probe,
        )
        encryption = inspect_encryption(observed_at, system=system, runner=runner)
        no_sync = inspect_no_sync(
            storage_binding,
            sync_bindings,
            len(sync_roots),
            len(sync_errors),
            "SYMLINK" in sync_errors,
            sync_inventory_complete,
            observed_at,
        )
        backup = inspect_backup(observed_at, system=system, runner=runner)
        if storage_binding is not None and not storage_binding.visible_matches():
            storage["status"] = "FAIL"
            storage["reason_codes"] = list(
                dict.fromkeys([*storage["reason_codes"], "STORAGE_ROOT_CHANGED"])
            )
            storage["facts"]["visible_identity_matches"] = False
            no_sync["status"] = "FAIL"
            no_sync["reason_codes"] = list(
                dict.fromkeys([*no_sync["reason_codes"], "STORAGE_ROOT_CHANGED"])
            )
        if any(not binding.visible_matches() for binding in sync_bindings):
            if no_sync["status"] != "FAIL":
                no_sync["status"] = "UNKNOWN"
            no_sync["reason_codes"] = list(
                dict.fromkeys(
                    [*no_sync["reason_codes"], "DECLARED_SYNC_ROOT_CHANGED"]
                )
            )
        checks = [
            storage,
            encryption,
            no_sync,
            backup,
            check(
                "correction_export_deletion",
                "UNKNOWN",
                observed_at,
                ["PERSISTENT_ADAPTER_NOT_PRESENT"],
            ),
            check(
                "bounded_retention",
                "UNKNOWN",
                observed_at,
                ["PERSISTENT_ADAPTER_NOT_PRESENT"],
            ),
            check(
                "incident_response",
                "UNKNOWN",
                observed_at,
                ["INCIDENT_DRILL_NOT_EXECUTED"],
            ),
        ]
        if tuple(item["check_id"] for item in checks) != REQUIRED_CHECKS:
            raise HostDiscoveryError("host discovery check catalog is incomplete")
        report: dict[str, object] = {
            "schema_version": "1.0",
            "evidence_class": "host-privacy-discovery",
            "candidate_commit": candidate,
            "generated_at": observed_at,
            "named_host": named_host.strip(),
            "environment_id": environment_id.strip(),
            "platform": {
                "system": system,
                "release": platform_release(),
                "machine": platform_machine(),
            },
            "storage_root_sha256": path_identity(storage_root),
            "sync_inventory_complete": sync_inventory_complete,
            "checks": checks,
            "privacy_gate_ready": False,
            "persistent_adapter_authorized": False,
            "status": "NOT_READY",
            "claim_limit": CLAIM_LIMIT,
        }
        report["report_sha256"] = release_evidence.digest(report)
        if errors := verify_report(report):
            raise HostDiscoveryError(
                "invalid host discovery report: " + "; ".join(errors)
            )
        return report
    finally:
        if storage_binding is not None:
            storage_binding.close()
        for binding in sync_bindings:
            binding.close()


def verify_report(report: object) -> list[str]:
    try:
        errors = release_evidence.schema_errors(report, "host_privacy_discovery")
    except (KeyError, TypeError, ValueError) as exc:
        return [f"host discovery schema validation failed: {type(exc).__name__}"]
    if not isinstance(report, dict):
        return errors
    try:
        expected_hash = release_evidence.object_hash(report, "report_sha256")
    except (KeyError, TypeError, ValueError):
        errors.append("host discovery report cannot be canonically hashed")
        expected_hash = None
    if report.get("report_sha256") != expected_hash:
        errors.append("host discovery report self-hash mismatch")
    checks = report.get("checks")
    if isinstance(checks, list):
        check_ids = tuple(
            item.get("check_id") for item in checks if isinstance(item, dict)
        )
        if check_ids != REQUIRED_CHECKS:
            errors.append("host discovery check catalog is incomplete or reordered")
        generated_at = report.get("generated_at")
        if any(
            isinstance(item, dict) and item.get("observed_at") != generated_at
            for item in checks
        ):
            errors.append("host discovery check time differs from report time")
    return errors


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--storage-root", type=Path, required=True)
    result.add_argument("--named-host", required=True)
    result.add_argument("--environment-id", required=True)
    result.add_argument("--sync-root", type=Path, action="append", default=[])
    result.add_argument("--sync-inventory-complete", action="store_true")
    result.add_argument("--output", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        with reserve_private_output(
            args.output, declared_sync_roots=args.sync_root
        ) as reserved_output:
            report = discover(
                storage_root=args.storage_root,
                named_host=args.named_host,
                environment_id=args.environment_id,
                sync_roots=args.sync_root,
                sync_inventory_complete=args.sync_inventory_complete,
            )
            reserved_output.write(report)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "output": str(args.output),
                    "report_sha256": report["report_sha256"],
                    "checks": {
                        item["check_id"]: item["status"]
                        for item in report["checks"]
                    },
                    "persistent_adapter_authorized": False,
                },
                indent=2,
            )
        )
        return 1
    except (
        HostDiscoveryError,
        KeyError,
        TypeError,
        ValueError,
        OSError,
        release_evidence.ReleaseEvidenceError,
    ) as exc:
        print(
            json.dumps(
                {"status": "fail", "error": f"{type(exc).__name__}: {exc}"},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
