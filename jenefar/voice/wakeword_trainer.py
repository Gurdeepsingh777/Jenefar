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
    piper_path: str = "./piper-sample-generator",
    rir_path: str = "./mit_rirs",
    background_path: str = "./background",
    samples: int = 20000,
    validation_samples: int = 2000,
    steps: int = 50000,
) -> Path:
    phrase = phrase.strip()
    if not phrase:
        raise ValueError("Wake word phrase cannot be empty.")

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    config = {
        "model_name": model_name,
        "target_phrase": [phrase],
        "custom_negative_phrases": [
            "hello jen",
            "hey jenefar",
            "hello general",
        ],
        "n_samples": int(samples),
        "n_samples_val": int(validation_samples),
        "tts_batch_size": 50,
        "augmentation_batch_size": 16,
        "piper_sample_generator_path": piper_path,
        "output_dir": str(root / "models"),
        "rir_paths": [rir_path],
        "background_paths": [background_path],
        "background_paths_duplication_rate": [1],
        "false_positive_validation_data_path": "./validation_set_features.npy",
        "augmentation_rounds": 1,
        "feature_data_files": {
            "ACAV100M_sample": "./openwakeword_features_ACAV100M_2000_hrs_16bit.npy",
        },
        "batch_n_per_class": {
            "ACAV100M_sample": 1024,
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

    try:
        import openwakeword  # noqa: F401
    except Exception as exc:
        raise RuntimeError("Install openwakeword and training dependencies first.") from exc

    package_root = Path(__import__("openwakeword").__file__).resolve().parent
    train_py = package_root / "train.py"
    if not train_py.is_file():
        raise RuntimeError(
            "Installed openwakeword package does not expose train.py. "
            "Clone the upstream repository training source and run it with the generated config."
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
