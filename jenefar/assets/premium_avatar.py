from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


PIPELINE_SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "blender" / "premium_avatar.py"


def _find_blender() -> str | None:
    configured = os.getenv("JENEFAR_BLENDER_BIN", "").strip()
    candidates = [configured] if configured else []
    candidates.extend(
        [
            "blender",
            "blender-4.5",
            "blender-4.4",
            "blender-4.3",
            "blender-4.2",
        ]
    )
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def prepare_premium_avatar(
    source: str | Path,
    output: str | Path | None = None,
    *,
    blend_output: str | Path | None = None,
) -> Path | None:
    """Bake a premium VRM copy when Blender + VRM add-on are available.

    This never modifies the source model. If Blender is unavailable or the
    add-on is missing, the caller can safely continue with the source VRM.
    """
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        return None

    destination = (
        Path(output).expanduser().resolve()
        if output
        else source_path.with_name("Jenefar_Premium.vrm")
    )
    if destination.is_file() and destination.stat().st_size > 0:
        return destination

    blender = _find_blender()
    if not blender:
        return None

    cmd = [
        blender,
        "--background",
        "--python",
        str(PIPELINE_SCRIPT),
        "--",
        "--input",
        str(source_path),
        "--output",
        str(destination),
    ]
    if blend_output:
        cmd.extend(["--blend-output", str(Path(blend_output).expanduser().resolve())])

    timeout = int(os.getenv("JENEFAR_BLENDER_TIMEOUT", "180"))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=max(30, timeout),
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Premium VRM pipeline failed. "
            f"stdout={result.stdout[-1200:]!r} stderr={result.stderr[-2000:]!r}"
        )

    if not destination.is_file() or destination.stat().st_size <= 0:
        raise RuntimeError("Premium VRM pipeline finished without producing the output file.")
    return destination
