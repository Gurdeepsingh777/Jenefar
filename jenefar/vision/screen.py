from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any

from jenefar.offline.connectivity import internet_available


@dataclass(frozen=True)
class ScreenElement:
    label: str
    role: str
    confidence: float
    bbox: tuple[int, int, int, int]
    center: tuple[int, int]
    text: str = ""


@dataclass(frozen=True)
class ScreenFrame:
    png_bytes: bytes
    width: int
    height: int
    encoded_width: int
    encoded_height: int
    path: str | None = None

    @property
    def data_url(self) -> str:
        encoded = base64.b64encode(self.png_bytes).decode("ascii")
        return "data:image/png;base64," + encoded


class ScreenVision:
    """Screenshot -> multimodal model -> validated semantic screen elements."""

    def __init__(
        self,
        desktop,
        *,
        max_dimension: int = 1600,
        confidence_threshold: float | None = None,
    ) -> None:
        self.desktop = desktop
        configured_dimension = os.getenv("JENEFAR_VISION_MAX_DIMENSION", "").strip()
        self.max_dimension = max(
            640,
            min(int(configured_dimension or max_dimension), 2560),
        )
        env_threshold = os.getenv("JENEFAR_VISION_CONFIDENCE", "").strip()
        self.confidence_threshold = (
            float(confidence_threshold)
            if confidence_threshold is not None
            else float(env_threshold or "0.65")
        )

    def capture(self, *, save: bool = False) -> ScreenFrame:
        return self.desktop.capture_frame(
            max_dimension=self.max_dimension,
            save=save,
        )

    def read_screen(self, task: str) -> dict[str, Any]:
        """Explicit screen-understanding entry point; always captures a fresh frame."""
        return self.analyze(task)

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(
                r"^```(?:json)?\s*",
                "",
                cleaned,
                flags=re.IGNORECASE,
            )
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            value = json.loads(cleaned)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise ValueError("Vision model did not return valid JSON.")
        value = json.loads(match.group(0))
        if not isinstance(value, dict):
            raise ValueError("Vision model JSON root must be an object.")
        return value

    @staticmethod
    def _clamp_box(
        box: list[Any] | tuple[Any, ...],
        width: int,
        height: int,
    ) -> tuple[int, int, int, int]:
        if len(box) != 4:
            raise ValueError("Vision bounding box must contain four values.")
        x1, y1, x2, y2 = [
            int(round(float(value))) for value in box
        ]
        x1, x2 = sorted(
            (
                max(0, min(width, x1)),
                max(0, min(width, x2)),
            )
        )
        y1, y2 = sorted(
            (
                max(0, min(height, y1)),
                max(0, min(height, y2)),
            )
        )
        if x2 <= x1 or y2 <= y1:
            raise ValueError("Vision returned an empty bounding box.")
        return x1, y1, x2, y2

    def _parse_elements(
        self,
        payload: dict[str, Any],
        frame: ScreenFrame,
    ) -> list[ScreenElement]:
        raw_elements = payload.get("elements", [])
        if not isinstance(raw_elements, list):
            raise ValueError("Vision response 'elements' must be a list.")

        scale_x = frame.width / frame.encoded_width
        scale_y = frame.height / frame.encoded_height
        elements: list[ScreenElement] = []

        for raw in raw_elements:
            if not isinstance(raw, dict):
                continue
            try:
                confidence = float(raw.get("confidence", 0))
                if confidence < self.confidence_threshold:
                    continue
                box = raw.get("bbox") or raw.get("box")
                if not box:
                    continue
                ex1, ey1, ex2, ey2 = self._clamp_box(
                    box,
                    frame.encoded_width,
                    frame.encoded_height,
                )
                x1 = int(round(ex1 * scale_x))
                y1 = int(round(ey1 * scale_y))
                x2 = int(round(ex2 * scale_x))
                y2 = int(round(ey2 * scale_y))
                label = str(
                    raw.get("label")
                    or raw.get("name")
                    or ""
                ).strip()
                role = str(raw.get("role") or "unknown").strip()
                text = str(raw.get("text") or "").strip()
                if not label:
                    label = text or role
                elements.append(
                    ScreenElement(
                        label=label,
                        role=role,
                        confidence=confidence,
                        bbox=(x1, y1, x2, y2),
                        center=((x1 + x2) // 2, (y1 + y2) // 2),
                        text=text,
                    )
                )
            except (TypeError, ValueError):
                continue

        return elements

    def _online_analyze(
        self,
        frame: ScreenFrame,
        task: str,
    ) -> list[ScreenElement]:
        from openai import OpenAI

        model = (
            os.getenv("JENEFAR_VISION_MODEL", "").strip()
            or os.getenv("JENEFAR_MODEL_VISION", "").strip()
            or os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
        )
        prompt = (
            "Analyze this desktop screenshot for semantic UI control. "
            "Return JSON only with an elements array. "
            "For every visible actionable or task-relevant UI element include "
            "label, role, confidence from 0 to 1, bbox [x1,y1,x2,y2] in "
            "the supplied image pixels, and optional visible text. "
            "Do not invent elements that are not visible. "
            f"User task: {task}"
        )
        response = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY")
        ).responses.create(
            model=model,
            store=False,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": frame.data_url},
                    ],
                }
            ],
        )
        return self._parse_elements(
            self._extract_json(response.output_text),
            frame,
        )

    def _local_analyze(
        self,
        frame: ScreenFrame,
        task: str,
    ) -> dict[str, Any]:
        import urllib.error
        import urllib.request

        base = os.getenv(
            "JENEFAR_LOCAL_VISION_BASE_URL",
            "http://127.0.0.1:11434",
        ).rstrip("/")
        requested_model = os.getenv(
            "JENEFAR_LOCAL_VISION_MODEL",
            "qwen3-vl:4b",
        ).strip()

        try:
            request = urllib.request.Request(
                f"{base}/api/tags",
                headers={"User-Agent": "Jenefar/LocalVision"},
            )
            with urllib.request.urlopen(request, timeout=2.0) as response:
                models_payload = json.loads(response.read().decode("utf-8"))
            installed = [
                str(item.get("name") or item.get("model") or "").strip()
                for item in (models_payload.get("models") or [])
                if isinstance(item, dict)
            ]
        except Exception as exc:
            raise RuntimeError(
                f"Local vision server is unavailable at {base}: {exc}"
            ) from exc

        vision_markers = (
            "qwen3-vl",
            "qwen2.5vl",
            "llama3.2-vision",
            "llava",
            "minicpm-v",
            "moondream",
            "deepseek-ocr",
        )
        model = requested_model if requested_model in installed else next(
            (item for item in installed if any(marker in item.lower() for marker in vision_markers)),
            "",
        )
        if not model:
            raise RuntimeError(
                "No local multimodal vision model is installed. "
                f"Run ollama pull {requested_model} and try again. "
                "The current llama3.2:latest model is text-only and must not be used for screen vision."
            )

        prompt = (
            "You are Jenefar's local desktop vision engine. "
            "Analyze the supplied desktop screenshot and return JSON only. "
            "Schema: {summary: string, elements: ["
            "{label: string, role: string, confidence: number, "
            "bbox: [x1,y1,x2,y2], text: string}]}. "
            "Use the supplied image pixel coordinates. "
            "Only include visible, task-relevant UI elements. "
            "For screen-reading requests, summary must be 1-3 short natural sentences. "
            "Mention only the main visible applications/windows, the user's current task context, "
            "and important on-screen activity. Do not read out file paths, IDs, timestamps, punctuation, "
            "small decorative text, model metadata, or irrelevant controls. Do not speculate. "
            "For GUI tasks, include actionable controls and their visible labels. "
            "Never invent UI elements. "
            f"User task: {task}"
        )
        image_b64 = base64.b64encode(frame.png_bytes).decode("ascii")
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            }],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
        }
        request = urllib.request.Request(
            f"{base}/api/chat",
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Jenefar/LocalVision",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(
                f"Local VLM request failed at {base}: {exc}"
            ) from exc

        message = result.get("message") or {}
        content = str(message.get("content") or result.get("response") or "").strip()
        if not content:
            raise RuntimeError("Local VLM returned an empty response.")

        return self._extract_json(content)
    def analyze(self, task: str) -> dict[str, Any]:
        frame = self.capture(save=False)

        # Safe headless/virtual backend: use deterministic semantic fixtures
        # without pyautogui, a real display, or a configured vision model.
        semantic_provider = getattr(self.desktop, "semantic_elements", None)
        if callable(semantic_provider):
            payload = {"elements": semantic_provider(task)}
            elements = self._parse_elements(payload, frame)
            return {
                "provider": "headless_fixture",
                "task": task,
                "screen": {
                    "width": frame.width,
                    "height": frame.height,
                },
                "elements": [
                    {
                        "label": item.label,
                        "role": item.role,
                        "confidence": item.confidence,
                        "bbox": list(item.bbox),
                        "center": list(item.center),
                        "text": item.text,
                    }
                    for item in elements
                ],
                "errors": [],
            }

        allow_online = os.getenv(
            "JENEFAR_VISION_ALLOW_ONLINE",
            "0",
        ).strip().lower() in {"1", "true", "yes", "on"}
        local_first = os.getenv(
            "JENEFAR_VISION_LOCAL_FIRST",
            "1",
        ).strip().lower() not in {"0", "false", "no"}
        errors: list[str] = []
        provider = ""
        payload: dict[str, Any] | None = None

        if local_first:
            try:
                payload = self._local_analyze(frame, task)
                provider = "local_ollama"
            except Exception as exc:
                errors.append(
                    f"local vision: {type(exc).__name__}: {exc}"
                )

        if payload is None and allow_online and internet_available() and os.getenv("OPENAI_API_KEY"):
            try:
                elements = self._online_analyze(frame, task)
                payload = {"elements": [
                    {
                        "label": item.label,
                        "role": item.role,
                        "confidence": item.confidence,
                        "bbox": list(item.bbox),
                        "text": item.text,
                    }
                    for item in elements
                ]}
                provider = "openai"
            except Exception as exc:
                errors.append(
                    f"online vision: {type(exc).__name__}: {exc}"
                )

        if payload is None and not local_first:
            try:
                payload = self._local_analyze(frame, task)
                provider = "local_ollama"
            except Exception as exc:
                errors.append(
                    f"local vision: {type(exc).__name__}: {exc}"
                )

        if payload is None:
            raise RuntimeError(
                "Local screen vision unavailable. "
                + " ".join(errors)
                + " Ensure Ollama is running and the configured multimodal model is installed."
            )

        elements = self._parse_elements(payload, frame)
        return {
            "provider": provider,
            "task": task,
            "screen": {
                "width": frame.width,
                "height": frame.height,
            },
            "summary": str(payload.get("summary") or "").strip(),
            "elements": [
                {
                    "label": item.label,
                    "role": item.role,
                    "confidence": item.confidence,
                    "bbox": list(item.bbox),
                    "center": list(item.center),
                    "text": item.text,
                }
                for item in elements
            ],
            "errors": errors,
        }

    def locate_window(self, query: str) -> dict[str, Any]:
        frame = self.capture(save=False)
        connected = False
        errors: list[str] = []
        payload: dict[str, Any] | None = None
        provider = ""

        prompt_task = (
            "Find the outer window rectangle for the requested desktop application or window. "
            "Return JSON only with summary and elements. The best matching element must represent "
            "the complete visible application window, not a button inside it. "
            "Use role=window when appropriate. Use exact screenshot pixel coordinates. "
            "Do not include unrelated UI. Requested window: " + str(query)
        )

        try:
            payload = self._local_analyze(frame, prompt_task)
            provider = "local_ollama"
        except Exception as exc:
            errors.append(f"local vision: {type(exc).__name__}: {exc}")

        if payload is None:
            allow_online = os.getenv("JENEFAR_VISION_ALLOW_ONLINE", "0").strip().lower() in {
                "1", "true", "yes", "on"
            }
            if allow_online and internet_available() and os.getenv("OPENAI_API_KEY"):
                try:
                    elements = self._online_analyze(frame, prompt_task)
                    payload = {"elements": [
                        {
                            "label": item.label,
                            "role": item.role,
                            "confidence": item.confidence,
                            "bbox": list(item.bbox),
                            "text": item.text,
                        }
                        for item in elements
                    ]}
                    provider = "openai"
                    connected = True
                except Exception as exc:
                    errors.append(f"online vision: {type(exc).__name__}: {exc}")

        if payload is None:
            raise RuntimeError("Window detection failed: " + " ".join(errors))

        elements = self._parse_elements(payload, frame)
        if not elements:
            raise LookupError("No visible window matched: " + str(query))

        normalized = str(query).lower().strip()

        def rank(item: dict[str, Any]) -> tuple[int, int, float, int]:
            label = str(item["label"]).lower()
            text = str(item.get("text", "")).lower()
            role = str(item.get("role", "")).lower()
            exact = 0 if normalized in label else 1
            text_miss = 0 if normalized in text else 1
            role_penalty = 0 if role in {"window", "application", "browser"} else 1
            area = int(item["bbox"][2] - item["bbox"][0]) * int(
                item["bbox"][3] - item["bbox"][1]
            )
            return exact, text_miss, role_penalty, -area

        best = sorted(elements, key=rank)[0]
        return {
            "provider": provider,
            "task": query,
            "label": best["label"],
            "role": best["role"],
            "confidence": best["confidence"],
            "bbox": best["bbox"],
            "text": best.get("text", ""),
            "screen": {"width": frame.width, "height": frame.height},
            "errors": errors,
        }

    def locate(self, query: str) -> dict[str, Any]:
        result = self.analyze(query)
        elements = result["elements"]
        if not elements:
            raise LookupError(
                "No screen element matching the semantic query was detected: "
                + query
            )

        normalized = query.lower().strip()

        def rank(item: dict[str, Any]) -> tuple[int, int, float]:
            label = str(item["label"]).lower()
            visible_text = str(item.get("text", "")).lower()
            exact = int(normalized not in label)
            text_miss = int(normalized not in visible_text)
            return exact, text_miss, -float(item["confidence"])

        result["match"] = dict(sorted(elements, key=rank)[0])
        result["match"]["center"] = tuple(result["match"]["center"])
        return result

    @staticmethod
    def _hash_payload(value: Any) -> str:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _snapshot(self, frame: ScreenFrame, task: str) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "width": frame.width,
            "height": frame.height,
            "png_sha256": (
                hashlib.sha256(frame.png_bytes).hexdigest()
                if frame.png_bytes
                else None
            ),
        }
        semantic_provider = getattr(self.desktop, "semantic_elements", None)
        if callable(semantic_provider):
            try:
                snapshot["semantic_sha256"] = self._hash_payload(
                    semantic_provider(task)
                )
            except Exception as exc:
                snapshot["semantic_error"] = (
                    f"{type(exc).__name__}: {exc}"
                )
        return snapshot

    @staticmethod
    def _compare_snapshots(
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> dict[str, Any]:
        checks = []
        for key in ("png_sha256", "semantic_sha256"):
            left = before.get(key)
            right = after.get(key)
            if left is not None and right is not None:
                checks.append(left != right)
        return {
            "screen_changed": any(checks) if checks else None,
            "signals_compared": len(checks),
            "before": before,
            "after": after,
        }

    def _verify_postcondition(
        self,
        query: str | None,
    ) -> dict[str, Any] | None:
        if not query:
            return None
        try:
            result = self.locate(query)
            return {
                "query": query,
                "matched": True,
                "match": result["match"],
                "provider": result.get("provider"),
            }
        except Exception as exc:
            return {
                "query": query,
                "matched": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    def locate_and_click(
        self,
        query: str,
        *,
        verify: str | None = None,
    ) -> dict[str, Any]:
        before = self.capture(save=False)
        before_snapshot = self._snapshot(before, query)
        result = self.locate(query)
        x, y = [int(value) for value in result["match"]["center"]]
        result["action"] = self.desktop.click(x, y, "left")
        after = self.capture(save=False)
        after_snapshot = self._snapshot(after, query)
        result["verification"] = self._compare_snapshots(
            before_snapshot,
            after_snapshot,
        )
        result["postcondition"] = self._verify_postcondition(verify)
        return result

    def locate_and_type(
        self,
        query: str,
        text: str,
        *,
        verify: str | None = None,
    ) -> dict[str, Any]:
        before = self.capture(save=False)
        before_snapshot = self._snapshot(before, query)
        result = self.locate(query)
        x, y = [int(value) for value in result["match"]["center"]]
        result["click"] = self.desktop.click(x, y, "left")
        result["type"] = self.desktop.type_text(text)
        after = self.capture(save=False)
        after_snapshot = self._snapshot(after, query)
        result["verification"] = self._compare_snapshots(
            before_snapshot,
            after_snapshot,
        )
        result["postcondition"] = self._verify_postcondition(verify)
        return result
