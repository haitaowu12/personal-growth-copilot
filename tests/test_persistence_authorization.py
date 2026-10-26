from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "persistence_authorization_runtime",
    ROOT / "scripts/persistence_authorization.py",
)
authorization = importlib.util.module_from_spec(spec)
spec.loader.exec_module(authorization)

import release_evidence  # noqa: E402


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def signing_key(directory: Path):
    private_key = directory / "privacy-private.pem"
    public_key = directory / "privacy-public.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "openssl",
            "pkey",
            "-in",
            str(private_key),
            "-pubout",
            "-out",
            str(public_key),
        ],
        check=True,
        capture_output=True,
    )
    return private_key, public_key


def sign(directory: Path, private_key: Path, payload: dict) -> str:
    payload_path = directory / "payload.json"
    signature_path = directory / "signature.bin"
    payload_path.write_bytes(canonical(payload))
    subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-sign",
            "-rawin",
            "-inkey",
            str(private_key),
            "-in",
            str(payload_path),
            "-out",
            str(signature_path),
        ],
        check=True,
        capture_output=True,
    )
    import base64

    return base64.b64encode(signature_path.read_bytes()).decode()


class PersistenceAuthorizationTests(unittest.TestCase):
    def fixture(self, directory: Path):
        private_key, public_key = signing_key(directory)
        storage_root = directory / "storage"
        storage_root.mkdir(mode=0o700)
        os.chmod(storage_root, 0o700)
        host = {
            "schema_version": "1.0",
            "evidence_class": "privacy-host-identity",
            "named_host": "restricted-host-1",
            "environment_id": "restricted-host-0001",
            "storage_root_sha256": authorization.persistent_record_store.storage_root_identity(
                storage_root
            ),
            "audit_id": "privacy-audit-0000000000000001",
            "audit_public_key_path": public_key.name,
            "audit_public_key_sha256": hashlib.sha256(public_key.read_bytes()).hexdigest(),
            "captured_at": "2026-09-11T00:00:00Z",
        }
        host_path = directory / "host.json"
        host_path.write_bytes(canonical(host))
        index = {
            "index_sha256": "c" * 64,
            "gates": {
                "privacy_preflight": {
                    "status": "PASS",
                    "artifact_sha256": "d" * 64,
                }
            },
        }
        index_path = directory / "index.json"
        index_path.write_text(json.dumps(index), encoding="utf-8")
        policy = {
            "privacy_host_identity_sha256": hashlib.sha256(
                host_path.read_bytes()
            ).hexdigest(),
            "authorities": [
                {
                    "key_id": "key-0000000000000001",
                    "role": "privacy_authority",
                    "allowed_gates": ["privacy_preflight"],
                    "public_key_path": public_key.name,
                    "public_key_sha256": hashlib.sha256(
                        public_key.read_bytes()
                    ).hexdigest(),
                }
            ],
        }
        policy_path = directory / "policy.json"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        return (
            private_key,
            public_key,
            storage_root,
            host_path,
            index_path,
            policy_path,
        )

    def test_signed_authorization_binds_current_privacy_gate_and_storage_root(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            (
                private_key,
                _,
                storage_root,
                host_path,
                index_path,
                policy_path,
            ) = self.fixture(directory)
            current = datetime.now(timezone.utc)
            request_path = directory / "authorization-request.json"
            request = authorization.prepare_request(
                output=request_path,
                index_path=index_path,
                policy_path=policy_path,
                host_identity_path=host_path,
                storage_root=storage_root,
                expected_commit="a" * 40,
                expected_policy_sha256="b" * 64,
                expected_index_sha256="c" * 64,
                authorization_id="pauth_" + "1" * 32,
                issued_at=current - timedelta(minutes=1),
                expires_at=current + timedelta(days=30),
                nonce="persistence-authorization-nonce-0001",
                verifier=lambda **_: {
                    "verification_status": "pass",
                    "errors": [],
                },
            )
            request_path.write_bytes(canonical(request))
            signature_path = directory / "signature.base64"
            signature_path.write_text(
                sign(directory, private_key, request["payload"]) + "\n",
                encoding="utf-8",
            )
            artifact = authorization.assemble(
                request_path=request_path, signature_path=signature_path
            )
            artifact_path = directory / "authorization.json"
            artifact_path.write_bytes(canonical(artifact))
            verifier = authorization.SignedPersistenceAuthorizationVerifier(
                authorization_path=artifact_path,
                expected_candidate_commit="a" * 40,
                expected_index_sha256="c" * 64,
                expected_privacy_artifact_sha256="d" * 64,
            )
            record = authorization.authorization_record(artifact)
            self.assertTrue(verifier.verify(record, storage_root))
            self.assertEqual(record.named_host, "restricted-host-1")
            self.assertEqual(record.key_id, "key-0000000000000001")

            other = directory / "other"
            other.mkdir(mode=0o700)
            os.chmod(other, 0o700)
            self.assertFalse(verifier.verify(record, other))

    def test_pending_privacy_wrong_host_and_bad_signature_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            (
                private_key,
                _,
                storage_root,
                host_path,
                index_path,
                policy_path,
            ) = self.fixture(directory)
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["gates"]["privacy_preflight"]["status"] = "PENDING"
            index_path.write_text(json.dumps(index), encoding="utf-8")
            with self.assertRaisesRegex(
                authorization.PersistenceAuthorizationError, "not PASS"
            ):
                authorization.prepare_request(
                    output=directory / "pending.json",
                    index_path=index_path,
                    policy_path=policy_path,
                    host_identity_path=host_path,
                    storage_root=storage_root,
                    expected_commit="a" * 40,
                    expected_policy_sha256="b" * 64,
                    expected_index_sha256="c" * 64,
                    authorization_id="pauth_" + "1" * 32,
                    issued_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                    nonce="persistence-authorization-nonce-0001",
                    verifier=lambda **_: {
                        "verification_status": "pass",
                        "errors": [],
                    },
                )

            index["gates"]["privacy_preflight"]["status"] = "PASS"
            index_path.write_text(json.dumps(index), encoding="utf-8")
            request = authorization.prepare_request(
                output=directory / "request.json",
                index_path=index_path,
                policy_path=policy_path,
                host_identity_path=host_path,
                storage_root=storage_root,
                expected_commit="a" * 40,
                expected_policy_sha256="b" * 64,
                expected_index_sha256="c" * 64,
                authorization_id="pauth_" + "1" * 32,
                issued_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                nonce="persistence-authorization-nonce-0001",
                verifier=lambda **_: {
                    "verification_status": "pass",
                    "errors": [],
                },
            )
            request_path = directory / "request.json"
            request_path.write_bytes(canonical(request))
            signature_path = directory / "bad-signature.base64"
            import base64

            signature_path.write_text(
                base64.b64encode(b"x" * 64).decode() + "\n", encoding="utf-8"
            )
            with self.assertRaises(release_evidence.ReleaseEvidenceError):
                authorization.assemble(
                    request_path=request_path, signature_path=signature_path
                )


if __name__ == "__main__":
    unittest.main()
