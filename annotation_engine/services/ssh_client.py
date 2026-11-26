"""
AnnotationEngine Desktop - SSH/SFTP Client

A thin ``paramiko`` wrapper used by remote ("SSH annotating") projects to list
and fetch images on demand and to push annotation results back to the server.

The class is deliberately small and synchronous; callers run it off the UI
thread (or accept the brief block for a single image fetch).
"""
import os
import posixpath
import stat
from pathlib import Path
from typing import List, Optional, Tuple

from annotation_engine.config import SUPPORTED_IMAGE_FORMATS


class SSHConnectionError(RuntimeError):
    """Raised when an SSH/SFTP connection cannot be established."""


def _is_dir(entry) -> bool:
    mode = getattr(entry, "st_mode", None)
    return mode is not None and stat.S_ISDIR(mode)


def encode_secret(password: str = "", key_file: str = "") -> str:
    """Serialize SSH credentials for storage (password encrypted at rest)."""
    import json

    from annotation_engine.utils.encryption import EncryptionManager

    payload = {}
    if password:
        payload["password"] = EncryptionManager().encrypt(password)
    if key_file:
        payload["key_file"] = key_file
    return json.dumps(payload) if payload else ""


def decode_secret(secret: str) -> Tuple[str, str]:
    """Return ``(password, key_file)`` from a stored secret."""
    import json

    from annotation_engine.utils.encryption import EncryptionManager

    if not secret:
        return "", ""
    try:
        data = json.loads(secret)
    except (TypeError, ValueError):
        return "", ""
    encrypted = data.get("password") or ""
    password = EncryptionManager().decrypt(encrypted) if encrypted else ""
    return password, data.get("key_file") or ""


class SSHClient:
    """Minimal SSH/SFTP client for remote image projects."""

    def __init__(self, host: str, port: int = 22, username: str = "",
                 password: str = "", key_file: str = ""):
        self.host = host
        self.port = int(port or 22)
        self.username = username
        self.password = password
        self.key_file = key_file
        self._client = None
        self._sftp = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    def connect(self) -> "SSHClient":
        import paramiko

        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            params = {
                "hostname": self.host,
                "port": self.port,
                "username": self.username,
                "timeout": 30,
            }
            if self.key_file:
                params["key_filename"] = self.key_file
            if self.password:
                params["password"] = self.password
            client.connect(**params)
            self._client = client
            self._sftp = client.open_sftp()
        except Exception as exc:  # paramiko raises many exception types
            raise SSHConnectionError(str(exc)) from exc
        return self

    def _ensure(self):
        if self._sftp is None:
            self.connect()

    def close(self):
        for resource in (self._sftp, self._client):
            try:
                if resource is not None:
                    resource.close()
            except Exception:
                pass
        self._sftp = None
        self._client = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc_info):
        self.close()

    # ------------------------------------------------------------------
    # Listing / transfer
    # ------------------------------------------------------------------
    def list_images(self, remote_dir: str, recursive: bool = True
                    ) -> List[Tuple[str, int]]:
        """Return ``(relative_path, size)`` for images under ``remote_dir``."""
        self._ensure()
        results: List[Tuple[str, int]] = []
        self._walk(remote_dir, "", recursive, results)
        return results

    def _walk(self, base: str, rel: str, recursive: bool, results: list):
        path = posixpath.join(base, rel) if rel else base
        try:
            entries = self._sftp.listdir_attr(path)
        except IOError:
            return
        for entry in sorted(entries, key=lambda e: e.filename):
            name = entry.filename
            entry_rel = posixpath.join(rel, name) if rel else name
            if _is_dir(entry):
                if recursive:
                    self._walk(base, entry_rel, recursive, results)
            elif os.path.splitext(name)[1].lower() in SUPPORTED_IMAGE_FORMATS:
                results.append((entry_rel, entry.st_size or 0))

    def fetch(self, remote_path: str, local_path) -> bool:
        """Download ``remote_path`` to ``local_path`` (atomic via ``.part``)."""
        self._ensure()
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        partial = local_path.with_name(local_path.name + ".part")
        try:
            self._sftp.get(remote_path, str(partial))
            os.replace(partial, local_path)
            return True
        except Exception:
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    def upload(self, local_path, remote_path: str) -> bool:
        """Upload ``local_path`` to ``remote_path`` (atomic via ``.part``)."""
        self._ensure()
        remote_dir = posixpath.dirname(remote_path)
        if remote_dir:
            self._mkdirs(remote_dir)
        partial = remote_path + ".part"
        try:
            self._sftp.put(str(local_path), partial)
            try:
                self._sftp.remove(remote_path)
            except IOError:
                pass
            self._sftp.rename(partial, remote_path)
            return True
        except Exception:
            try:
                self._sftp.remove(partial)
            except Exception:
                pass
            return False

    def _mkdirs(self, remote_dir: str):
        """Create a remote directory tree, ignoring existing components."""
        if not remote_dir or remote_dir in ("/", "."):
            return
        absolute = remote_dir.startswith("/")
        current = "/" if absolute else ""
        for part in remote_dir.strip("/").split("/"):
            if not part:
                continue
            current = posixpath.join(current, part) if current else part
            try:
                self._sftp.stat(current)
            except IOError:
                try:
                    self._sftp.mkdir(current)
                except IOError:
                    pass

    def upload_tree(self, local_dir, remote_dir: str,
                    progress_callback=None) -> int:
        """Upload every file under ``local_dir`` into ``remote_dir``.

        Returns the number of files uploaded. ``progress_callback`` receives
        ``(percent, message)``.
        """
        self._ensure()
        local_dir = Path(local_dir)
        files = sorted(p for p in local_dir.rglob("*") if p.is_file())
        total = len(files)
        if not total:
            return 0

        self._mkdirs(remote_dir)
        uploaded = 0
        for index, path in enumerate(files):
            relative = path.relative_to(local_dir).as_posix()
            target = posixpath.join(remote_dir, relative)
            target_dir = posixpath.dirname(target)
            if target_dir:
                self._mkdirs(target_dir)
            if self.upload(path, target):
                uploaded += 1
            if progress_callback:
                percent = int(((index + 1) / total) * 100)
                progress_callback(percent, f"Uploading {relative}")
        return uploaded
