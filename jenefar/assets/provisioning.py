from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

ALLOWED_HOSTS = {
    "github.com",
    "raw.githubusercontent.com",
    "www.openslr.org",
    "openslr.org",
    "huggingface.co",
}

@dataclass(frozen=True)
class ResourceSpec:
    name: str
    url: str
    path: str
    license: str
    attribution: str
    max_bytes: int
    sha256: str | None = None

PIPER_REPO_COMMIT = "f1988a4d54eddb23d99e86f0adfef6226a85acc7"
VRM_REPO_COMMIT = "39d52551c3b5c19507d9399df65c85cab2be9c83"

PIPER_SOURCE = ResourceSpec(
    "piper-sample-generator",
    f"https://github.com/dscripka/piper-sample-generator/archive/{PIPER_REPO_COMMIT}.zip",
    "piper-source.zip",
    "MIT",
    "dscripka/piper-sample-generator",
    250 * 1024 * 1024,
)
PIPER_MODEL = ResourceSpec(
    "libritts-generator-model",
    "https://github.com/rhasspy/piper-sample-generator/releases/download/v1.0.0/en-us-libritts-high.pt",
    "piper-sample-generator/models/en-us-libritts-high.pt",
    "LibriTTS-derived Piper generator model",
    "LibriTTS / Piper Sample Generator",
    2 * 1024 * 1024 * 1024,
)
SLR26 = ResourceSpec(
    "slr26-simulated-rirs",
    "https://www.openslr.org/resources/26/sim_rir_16k.zip",
    "slr26/sim_rir_16k.zip",
    "Apache-2.0",
    "OpenSLR SLR26",
    1 * 1024 * 1024 * 1024,
)
SLR12_CLEAN = ResourceSpec(
    "librispeech-dev-clean",
    "https://www.openslr.org/resources/12/dev-clean.tar.gz",
    "librispeech/dev-clean.tar.gz",
    "CC BY 4.0",
    "OpenSLR SLR12 / LibriSpeech dev-clean",
    1 * 1024 * 1024 * 1024,
)
SLR12_OTHER = ResourceSpec(
    "librispeech-dev-other",
    "https://www.openslr.org/resources/12/dev-other.tar.gz",
    "librispeech/dev-other.tar.gz",
    "CC BY 4.0",
    "OpenSLR SLR12 / LibriSpeech dev-other",
    1 * 1024 * 1024 * 1024,
)
SLR28 = ResourceSpec(
    "slr28-rirs-and-noise",
    "https://www.openslr.org/resources/28/rirs_noises.zip",
    "slr28/rirs_noises.zip",
    "Apache-2.0",
    "OpenSLR SLR28",
    3 * 1024 * 1024 * 1024,
)
VRM_SAMPLE = ResourceSpec(
    "vrm-sample-avatar",
    f"https://github.com/arkavo-org/VRMMetalKit/raw/{VRM_REPO_COMMIT}/AvatarSample_A_1.0.vrm.glb",
    "avatar/AvatarSample_A_1.0.vrm.glb",
    "VRM Platform License 1.0; source fixture documents redistribution permission",
    "AvatarSample_A © pixiv VRoid Project",
    50 * 1024 * 1024,
)

def _validate_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"Refusing non-allowlisted asset URL: {url}")

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _manifest_path(root: Path) -> Path:
    return root / "ASSET_MANIFEST.json"

def _load_manifest(root: Path) -> dict:
    path = _manifest_path(root)
    if not path.is_file():
        return {"resources": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"resources": []}

def _save_manifest(root: Path, payload: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _manifest_path(root).write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

def _record(root: Path, spec: ResourceSpec, path: Path, status: str) -> None:
    payload = _load_manifest(root)
    resources = [item for item in payload.get("resources", []) if item.get("name") != spec.name]
    resources.append({
        **asdict(spec),
        "resolved_path": str(path.resolve()),
        "bytes": path.stat().st_size if path.is_file() else None,
        "sha256_actual": _sha256(path) if path.is_file() else None,
        "status": status,
        "recorded_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    payload["resources"] = sorted(resources, key=lambda item: item["name"])
    _save_manifest(root, payload)

def download_resource(spec: ResourceSpec, root: str | Path) -> Path:
    root = Path(root)
    _validate_url(spec.url)
    destination = root / spec.path
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")

    if destination.is_file():
        if spec.sha256 and _sha256(destination) != spec.sha256:
            destination.unlink()
        elif destination.stat().st_size > 0:
            _record(root, spec, destination, "cached")
            return destination

    request = urllib.request.Request(
        spec.url,
        headers={"User-Agent": "Jenefar-Asset-Provisioner/1.0"},
    )
    total = 0
    with urllib.request.urlopen(request, timeout=60) as response, part.open("wb") as output:
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > spec.max_bytes:
            raise ValueError(f"Refusing oversized download for {spec.name}")
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > spec.max_bytes:
                raise ValueError(f"Download exceeded safety cap for {spec.name}")
            output.write(chunk)

    part.replace(destination)
    if spec.sha256:
        actual = _sha256(destination)
        if actual != spec.sha256:
            destination.unlink(missing_ok=True)
            raise ValueError(
                f"Checksum mismatch for {spec.name}: expected {spec.sha256}, got {actual}"
            )
    _record(root, spec, destination, "downloaded")
    return destination

def _safe_target(root: Path, member_name: str) -> Path:
    target = (root / member_name).resolve()
    base = root.resolve()
    if target != base and base not in target.parents:
        raise ValueError(f"Archive path escapes extraction root: {member_name}")
    return target

def extract_zip(archive: str | Path, destination: str | Path) -> Path:
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as archive_obj:
        for member in archive_obj.infolist():
            _safe_target(destination, member.filename)
        archive_obj.extractall(destination)
    return destination

def extract_tar(archive: str | Path, destination: str | Path) -> Path:
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as archive_obj:
        for member in archive_obj.getmembers():
            _safe_target(destination, member.name)
            if member.issym() or member.islnk():
                raise ValueError(f"Refusing archive link entry: {member.name}")
        archive_obj.extractall(destination)
    return destination

def _audio_files(root: Path) -> list[Path]:
    extensions = {".wav", ".flac", ".ogg", ".mp3"}
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in extensions
    )

def _link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    try:
        os.link(source, destination)
        return
    except OSError:
        pass
    try:
        destination.symlink_to(source.resolve())
        return
    except OSError:
        shutil.copy2(source, destination)

def flatten_audio_tree(source_root: str | Path, destination: str | Path, *, limit: int = 2000) -> int:
    source_root = Path(source_root)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    created = 0
    for index, source in enumerate(_audio_files(source_root)):
        if index >= limit:
            break
        target = destination / f"{index:06d}{source.suffix.lower()}"
        _link_or_copy(source, target)
        created += 1
    return created

def setup_wakeword_assets(root: str | Path = "data/wakeword", profile: str = "safe") -> dict:
    if profile not in {"safe", "rich"}:
        raise ValueError("Wake-word asset profile must be 'safe' or 'rich'.")

    root = Path(root)
    assets = root / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    results: dict[str, str | int] = {}

    piper_zip = download_resource(PIPER_SOURCE, assets)
    extract_root = assets / "_piper_extract"
    extract_zip(piper_zip, extract_root)
    candidates = sorted(extract_root.glob("piper-sample-generator-*"))
    if not candidates:
        raise RuntimeError("Piper sample generator archive did not contain its expected directory.")
    piper_dir = assets / "piper-sample-generator"
    if not piper_dir.exists():
        shutil.move(str(candidates[0]), str(piper_dir))
    results["piper_generator"] = str(piper_dir)

    model = download_resource(PIPER_MODEL, assets)
    results["piper_model"] = str(model)

    rir_archive = download_resource(SLR26, assets)
    rir_root = assets / "slr26"
    extract_zip(rir_archive, rir_root)
    rir_dir = assets / "rir"
    rir_count = flatten_audio_tree(rir_root, rir_dir, limit=2000)
    results["rir_files"] = rir_count

    for spec in (SLR12_CLEAN, SLR12_OTHER):
        archive = download_resource(spec, assets)
        speech_root = assets / "librispeech"
        extract_tar(archive, speech_root)

    background_dir = assets / "background"
    background_count = flatten_audio_tree(assets / "librispeech", background_dir, limit=2500)
    results["background_files"] = background_count
    results["validation_audio_root"] = str((assets / "librispeech").resolve())

    if profile == "rich":
        rich_archive = download_resource(SLR28, assets)
        rich_root = assets / "slr28"
        extract_zip(rich_archive, rich_root)
        rich_background = assets / "background_rich"
        rich_count = flatten_audio_tree(rich_root, rich_background, limit=5000)
        results["rich_background_files"] = rich_count

    return results

def setup_avatar_asset(root: str | Path = "data") -> Path:
    root = Path(root)
    path = download_resource(VRM_SAMPLE, root)
    attribution = path.with_name("AVATAR_LICENSE.txt")
    attribution.write_text(
        "Jenefar local sample avatar provenance\n\n"
        "Asset: AvatarSample_A_1.0.vrm.glb\n"
        f"Source: {VRM_SAMPLE.url}\n"
        "License: VRM Platform License 1.0; the source repository documents "
        "allowRedistribution=true and modification=allowModificationRedistribution "
        "for this fixture.\n"
        "Attribution: AvatarSample_A © pixiv VRoid Project.\n"
        "Do not remove this notice when redistributing the asset.\n",
        encoding="utf-8",
    )
    return path
