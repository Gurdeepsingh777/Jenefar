from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


def prepare_config(
    phrase: str,
    *,
    model_name: str = "jenefar",
    output_dir: str = "data/wakeword",
    piper_path: str | None = None,
    rir_path: str | None = None,
    background_path: str | None = None,
    validation_features_path: str | None = None,
    samples: int = 20_000,
    validation_samples: int = 2_000,
    steps: int = 50_000,
    rich_background: bool = False,
) -> Path:
    phrase = phrase.strip()
    if not phrase:
        raise ValueError("Wake word phrase cannot be empty.")

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    assets = root / "assets"
    piper = Path(piper_path or assets / "piper-sample-generator")
    rir = Path(rir_path or assets / "rir")
    background = Path(
        background_path or (
            assets / "background_rich" if rich_background else assets / "background"
        )
    )
    validation = Path(
        validation_features_path or root / "validation_set_features.npy"
    )

    config = {
        "model_name": model_name,
        "target_phrase": [phrase],
        "custom_negative_phrases": [
            "hello jen",
            "hey jenefar",
            "hello general",
            "hi jen",
        ],
        "n_samples": int(samples),
        "n_samples_val": int(validation_samples),
        "tts_batch_size": 50,
        "augmentation_batch_size": 16,
        "piper_sample_generator_path": str(piper.resolve()),
        "output_dir": str((root / "models").resolve()),
        "rir_paths": [str(rir.resolve())],
        "background_paths": [str(background.resolve())],
        "background_paths_duplication_rate": [1],
        "false_positive_validation_data_path": str(validation.resolve()),
        "augmentation_rounds": 1,
        "feature_data_files": {},
        "batch_n_per_class": {
            "adversarial_negative": 50,
            "positive": 50,
        },
        "model_type": "dnn",
        "layer_size": 32,
        "steps": int(steps),
        "max_negative_weight": 1500,
        "target_false_positives_per_hour": 0.2,
    }
    path = root / f"{model_name}.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def train(config_path: str | Path, *, stage: str = "all") -> int:
    path = Path(config_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    required = {
        "piper_sample_generator_path": "Piper sample generator",
        "rir_paths": "RIR directory",
        "background_paths": "background directory",
        "false_positive_validation_data_path": "validation feature file",
    }
    for key, label in required.items():
        value = config.get(key)
        candidate = value[0] if isinstance(value, list) else value
        if not candidate or not Path(candidate).exists():
            raise RuntimeError(
                f"{label} is missing: {candidate}. "
                "Run the wake-word asset setup command first."
            )

    try:
        import openwakeword  # noqa: F401
    except Exception as exc:
        raise RuntimeError(
            "Install openwakeword plus its training dependencies before training."
        ) from exc

    package_root = Path(__import__("openwakeword").__file__).resolve().parent
    train_py = package_root / "train.py"
    if not train_py.is_file():
        raise RuntimeError(
            "Installed openwakeword package does not expose train.py. "
            "Use the official openWakeWord repository training entry point."
        )

    flags = {
        "clips": ["--generate_clips"],
        "augment": ["--augment_clips"],
        "train": ["--train_model"],
        "tflite": ["--convert_to_tflite"],
        "all": ["--generate_clips", "--augment_clips", "--train_model"],
    }
    if stage not in flags:
        raise ValueError(f"Unknown wake-word stage: {stage}")

    command = [
        sys.executable,
        str(train_py),
        "--training_config",
        str(path),
        *flags[stage],
    ]
    completed = subprocess.run(command, check=False)
    return int(completed.returncode)
