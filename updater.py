"""Check and download signed-by-HTTPS GitHub Release installer updates."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import tempfile
import urllib.parse
import urllib.request

from version import __version__

REPOSITORY = "mcann1423/scribe-guide-publisher"
API_URL = "https://api.github.com/repos/" + REPOSITORY + "/releases/latest"
ASSET_NAME = "HelpGuidePublisherSetup.exe"
MAX_INSTALLER_BYTES = 150 * 1024 * 1024
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class Release:
    version: str
    download_url: str
    size: int
    sha256: str | None = None


def _version_key(value: str) -> tuple[int, int, int]:
    match = _VERSION.fullmatch(value.strip())
    if not match:
        raise ValueError("Release version must use vMAJOR.MINOR.PATCH.")
    return tuple(int(part) for part in match.groups())


def _read_json(urlopen=urllib.request.urlopen) -> dict:
    request = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "HelpGuidePublisher/" + __version__})
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def latest_release(urlopen=urllib.request.urlopen) -> Release:
    data = _read_json(urlopen)
    tag = data.get("tag_name")
    if not isinstance(tag, str):
        raise ValueError("GitHub did not return a release version.")
    version = tag[1:] if tag.startswith("v") else tag
    _version_key(version)
    for asset in data.get("assets", []):
        if asset.get("name") != ASSET_NAME:
            continue
        url, size = asset.get("browser_download_url"), asset.get("size")
        expected_prefix = "https://github.com/" + REPOSITORY + "/releases/download/"
        if not isinstance(url, str) or not url.startswith(expected_prefix):
            raise ValueError("GitHub returned an unexpected installer URL.")
        if not isinstance(size, int) or size < 1 or size > MAX_INSTALLER_BYTES:
            raise ValueError("GitHub returned an invalid installer size.")
        digest = asset.get("digest")
        sha256 = digest[7:].lower() if isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest) else None
        return Release(version, url, size, sha256)
    raise ValueError("The latest release does not contain " + ASSET_NAME + ".")


def check_for_update(urlopen=urllib.request.urlopen) -> Release | None:
    release = latest_release(urlopen)
    return release if _version_key(release.version) > _version_key(__version__) else None


def download_installer(release: Release, directory: Path | None = None, urlopen=urllib.request.urlopen) -> Path:
    """Download exactly the advertised release asset, verify size/digest, and return its temp path."""
    target_dir = Path(directory) if directory else Path(tempfile.gettempdir())
    target_dir.mkdir(parents=True, exist_ok=True)
    parsed = urllib.parse.urlsplit(release.download_url)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise ValueError("Installer URL is not a GitHub HTTPS download.")
    request = urllib.request.Request(release.download_url, headers={"User-Agent": "HelpGuidePublisher/" + __version__})
    fd, temporary = tempfile.mkstemp(prefix="HelpGuidePublisherUpdate-", suffix=".part", dir=target_dir)
    temp = Path(temporary)
    final = temp.with_suffix(".exe")
    total = 0
    digest = hashlib.sha256()
    try:
        with open(fd, "wb", closefd=True) as file, urlopen(request, timeout=60) as response:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_INSTALLER_BYTES:
                    raise ValueError("Installer download is too large.")
                file.write(chunk)
                digest.update(chunk)
        if total != release.size:
            raise ValueError("Installer download size did not match the GitHub Release.")
        if release.sha256 and digest.hexdigest() != release.sha256:
            raise ValueError("Installer download checksum did not match the GitHub Release.")
        temp.replace(final)
        return final
    except Exception:
        temp.unlink(missing_ok=True)
        final.unlink(missing_ok=True)
        raise
