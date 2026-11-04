from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from typing import Any
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


BACKUP_FILENAME = "td-backup.tdenc"
BACKUP_FORMAT = "td-github-backup-v1"
KEYCHAIN_SERVICE = "td-github-backup"
PBKDF2_ITERATIONS = 600_000


def _derive_key(password: str, salt: bytes, iterations: int) -> bytes:
    if not password:
        raise ValueError("Backup password cannot be empty")
    return base64.urlsafe_b64encode(
        PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=iterations,
        ).derive(password.encode("utf-8"))
    )


def encrypt_backup(json_data: str, password: str) -> str:
    """Encrypt a JSON export into a portable backup envelope."""
    salt = os.urandom(16)
    key = _derive_key(password, salt, PBKDF2_ITERATIONS)
    ciphertext = Fernet(key).encrypt(json_data.encode("utf-8"))
    envelope = {
        "format": BACKUP_FORMAT,
        "kdf": "pbkdf2-sha256",
        "iterations": PBKDF2_ITERATIONS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "ciphertext": ciphertext.decode("ascii"),
    }
    return json.dumps(envelope, indent=2) + "\n"


def backup_digest(json_data: str, encrypted: bool) -> str:
    """Return a stable digest for the exported data and storage mode."""
    marker = "encrypted" if encrypted else "plain"
    return hashlib.sha256(f"{marker}\0{json_data}".encode("utf-8")).hexdigest()


def is_encrypted_backup(data: str) -> bool:
    try:
        return json.loads(data).get("format") == BACKUP_FORMAT
    except (AttributeError, json.JSONDecodeError):
        return False


def decrypt_backup(encrypted_data: str, password: str) -> str:
    """Decrypt and validate a portable backup envelope."""
    try:
        envelope = json.loads(encrypted_data)
        if envelope.get("format") != BACKUP_FORMAT:
            raise ValueError("Unsupported backup format")
        if envelope.get("kdf") != "pbkdf2-sha256":
            raise ValueError("Unsupported backup KDF")
        iterations = int(envelope["iterations"])
        if iterations < 100_000 or iterations > 10_000_000:
            raise ValueError("Unsupported backup KDF cost")
        salt = base64.b64decode(envelope["salt"])
        ciphertext = envelope["ciphertext"].encode("ascii")
        key = _derive_key(password, salt, iterations)
        return Fernet(key).decrypt(ciphertext).decode("utf-8")
    except ValueError as error:
        if str(error) in ("Unsupported backup format", "Unsupported backup KDF"):
            raise
        raise ValueError("Invalid backup password or corrupted backup") from error
    except (KeyError, TypeError, InvalidToken, UnicodeDecodeError, binascii.Error) as error:
        raise ValueError("Invalid backup password or corrupted backup") from error


def decode_backup(data: str, password: str | None = None) -> str:
    """Return plaintext for either encrypted or intentionally plain backups."""
    if not is_encrypted_backup(data):
        return data
    if password is None:
        raise ValueError("Backup password required")
    return decrypt_backup(data, password)


def _run_gh(
    args: list[str], *, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["gh", *args],
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            "gh CLI not found. Install it from https://cli.github.com/"
        ) from error


def _require_gh(result: subprocess.CompletedProcess[str]) -> str:
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown gh error"
        raise RuntimeError(detail)
    return result.stdout


def _private_repo(repo: str, *, create: bool) -> tuple[str, bool]:
    _require_gh(_run_gh(["auth", "status"]))
    viewed = _run_gh(["repo", "view", repo, "--json", "nameWithOwner,isPrivate,isEmpty"])
    if viewed.returncode != 0:
        if not create:
            raise RuntimeError(f'GitHub repository "{repo}" not found or inaccessible')
        created = _run_gh([
            "repo",
            "create",
            repo,
            "--private",
            "--add-readme",
            "--description",
            "Encrypted td backup",
        ])
        _require_gh(created)
        viewed = _run_gh(["repo", "view", repo, "--json", "nameWithOwner,isPrivate,isEmpty"])

    details = json.loads(_require_gh(viewed))
    if not details.get("isPrivate"):
        raise RuntimeError("Backup repository must be private")
    return details["nameWithOwner"], details.get("isEmpty") is True


def _contents_endpoint(repo: str) -> str:
    return f"repos/{repo}/contents/{BACKUP_FILENAME}"


def repo_url(repo: str) -> str:
    """Resolve a configured repository to its web URL through gh."""
    result = _run_gh(["repo", "view", repo, "--json", "url", "--jq", ".url"])
    return _require_gh(result).strip()


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise RuntimeError("git CLI not found") from error


def _require_git(result: subprocess.CompletedProcess[str]) -> str:
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise RuntimeError(detail)
    return result.stdout


def _initialize_empty_repo(repo: str, data: str) -> None:
    """Create the first commit in an existing empty GitHub repository."""
    with tempfile.TemporaryDirectory(prefix="td-github-backup-") as temp_dir:
        clone_path = Path(temp_dir) / "repo"
        _require_gh(_run_gh(["repo", "clone", repo, str(clone_path)]))
        backup_path = clone_path / BACKUP_FILENAME
        backup_path.write_text(data, encoding="utf-8")
        _require_git(_run_git(["add", BACKUP_FILENAME], clone_path))
        _require_git(_run_git([
            "-c", "user.name=td-backup",
            "-c", "user.email=td-backup@users.noreply.github.com",
            "commit", "-m", "Create td backup",
        ], clone_path))
        _require_git(_run_git(["push", "-u", "origin", "HEAD:main"], clone_path))


def store_password(repo: str, password: str) -> None:
    """Store a backup password in the macOS Keychain for auto-sync."""
    if sys.platform != "darwin":
        raise RuntimeError("automatic backup passwords require macOS Keychain")
    result = subprocess.run(
        [
            "security",
            "add-generic-password",
            "-U",
            "-a",
            repo,
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
            password,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "Keychain update failed"
        raise RuntimeError(detail)


def load_password(repo: str) -> str | None:
    """Load a stored backup password, if one exists."""
    if sys.platform != "darwin":
        return None
    result = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-w",
            "-a",
            repo,
            "-s",
            KEYCHAIN_SERVICE,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    password = result.stdout.strip()
    return password or None


def sync_if_configured(json_data: str) -> str | None:
    """Upload a configured auto-sync backup. Return repo, or None if disabled."""
    from . import config

    settings = config.github_backup()
    if settings.get("auto_sync") is not True:
        return None
    repo = settings.get("repo")
    if not isinstance(repo, str) or not repo.strip():
        return None
    repo = repo.strip()
    should_encrypt = settings.get("encrypt", True) is not False
    digest = backup_digest(json_data, should_encrypt)
    if settings.get("last_sync_digest") == digest:
        return None
    if should_encrypt:
        password = load_password(repo)
        if password is None:
            return None
        payload = encrypt_backup(json_data, password)
    else:
        payload = json_data
    resolved_repo = upload_backup(repo, payload)
    config.set_github_backup(
        repo=resolved_repo,
        last_sync_digest=digest,
    )
    return resolved_repo


def upload_backup(repo: str, encrypted_data: str) -> str:
    """Create or update the encrypted backup file in a private GitHub repo."""
    name_with_owner, is_empty = _private_repo(repo, create=True)
    if is_empty:
        _initialize_empty_repo(name_with_owner, encrypted_data)
        return name_with_owner
    endpoint = _contents_endpoint(name_with_owner)
    existing = _run_gh(["api", endpoint, "--jq", ".sha"])
    body: dict[str, Any] = {
        "message": "Update encrypted td backup",
        "content": base64.b64encode(encrypted_data.encode("utf-8")).decode("ascii"),
    }
    if existing.returncode == 0 and existing.stdout.strip():
        body["sha"] = existing.stdout.strip()
    elif existing.returncode != 0 and "not found" not in existing.stderr.lower():
        _require_gh(existing)

    uploaded = _run_gh(
        ["api", endpoint, "--method", "PUT", "--input", "-"],
        input_text=json.dumps(body),
    )
    _require_gh(uploaded)
    return name_with_owner


def download_backup(repo: str) -> str:
    """Download the encrypted backup file from a private GitHub repo."""
    name_with_owner, _ = _private_repo(repo, create=False)
    result = _run_gh(["api", _contents_endpoint(name_with_owner), "--jq", ".content"])
    encoded = _require_gh(result)
    try:
        return base64.b64decode("".join(encoded.split())).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as error:
        raise RuntimeError("GitHub backup file is not valid UTF-8") from error
