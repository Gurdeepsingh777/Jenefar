from __future__ import annotations

import base64
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
        raw_elements = payload.get("elements") or []
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
    ) -> list[ScreenElement]:
        import urllib.error
        import urllib.request

        base = os.getenv(
            "JENEFAR_LOCAL_LLM_BASE_URL",
            "http://127.0.0.1:11434/v1",
        ).rstrip("/")
        model = os.getenv(
            "JENEFAR_LOCAL_VISION_MODEL",
            "",
        ).strip() or os.getenv(
            "JENEFAR_LOCAL_LLM_MODEL",
            "",
        ).strip()

        if not model:
            request = urllib.request.Request(
                f"{base}/models",
                headers={"User-Agent": "Jenefar/1.0"},
            )
            payload = json.loads(
                urllib.request.urlopen(request, timeout=1.5)
                .read()
                .decode("utf-8")
            )
            models = payload.get("data") or []
            model = str(models[0].get("id")) if models else ""

        if not model:
            raise RuntimeError(
                "No local multimodal model configured or detected."
            )

        prompt = (
            "Analyze this desktop screenshot for semantic UI control. "
            "Return JSON only with an elements array. "
            "For every visible actionable or task-relevant UI element include "
            "label, role, confidence from 0 to 1, bbox [x1,y1,x2,y2] in "
            "image pixels, and optional visible text. Do not invent elements. "
            f"User task: {task}"
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": frame.data_url},
                    },
                ],
            }
        ]
        request = urllib.request.Request(
            f"{base}/chat/completions",
            method="POST",
            data=json.dumps(
                {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                }
            ).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer sk-local",
            },
        )
        try:
            response = urllib.request.urlopen(request, timeout=120)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(
                f"Local vision request failed: {exc}"
            ) from exc

        payload = json.loads(
            response.read().decode("utf-8")
        )
        content = (
            ((payload.get("choices") or [{}])[0].get("message") or {})
            .get("content")
            or ""
        )
        return self._parse_elements(
            self._extract_json(str(content)),
            frame,
        )

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

        connected = internet_available()
        errors: list[str] = []

        if connected and os.getenv("OPENAI_API_KEY"):
            try:
                elements = self._online_analyze(frame, task)
                provider = "openai"
            except Exception as exc:
                errors.append(
                    f"online vision: {type(exc).__name__}: {exc}"
                )
                try:
                    elements = self._local_analyze(frame, task)
                    provider = "local"
                except Exception as local_exc:
                    errors.append(
                        f"local vision: {type(local_exc).__name__}: {local_exc}"
                    )
                    raise RuntimeError("; ".join(errors)) from local_exc
        else:
            try:
                elements = self._local_analyze(frame, task)
                provider = "local"
            except Exception as exc:
                errors.append(
                    f"local vision: {type(exc).__name__}: {exc}"
                )
                raise RuntimeError(
                    "No usable vision backend is available. Configure an "
                    "online vision model or an offline multimodal local model."
                ) from exc

        return {
            "provider": provider,
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

        result["match"] = sorted(elements, key=rank)[0]
        return result

    def locate_and_click(self, query: str) -> dict[str, Any]:
        result = self.locate(query)
        x, y = [int(value) for value in result["match"]["center"]]
        result["action"] = self.desktop.click(x, y, "left")
        return result

    def locate_and_type(self, query: str, text: str) -> dict[str, Any]:
        result = self.locate(query)
        x, y = [int(value) for value in result["match"]["center"]]
        result["click"] = self.desktop.click(x, y, "left")
        result["type"] = self.desktop.type_text(text)
        return result
