import base64
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from runpod_workers.juggernaut_xl import handler as worker


class FakeImage:
    def __init__(self, payload=b"fake-png"):
        self.payload = payload

    def save(self, fp, format=None):
        fp.write(self.payload)


def _fake_torch(monkeypatch):
    class FakeGenerator:
        def __init__(self, device=None):
            self.device = device
            self.seed = None

        def manual_seed(self, seed):
            self.seed = seed
            return self

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(Generator=FakeGenerator))


def test_generate_image_matches_forge_contract(monkeypatch):
    _fake_torch(monkeypatch)
    monkeypatch.setattr(worker, "MODEL_SLUG", "juggernaut-xl")
    pipeline = MagicMock(return_value=SimpleNamespace(images=[FakeImage()]))

    result = worker.generate_image(
        {
            "prompt": "a red dragon",
            "negative_prompt": "blurry",
            "num_inference_steps": 28,
            "width": 1024,
            "height": 1024,
            "guidance_scale": 7,
            "seed": 123,
            "model": "juggernaut-xl",
        },
        pipeline=pipeline,
    )

    assert result["model"] == "juggernaut-xl"
    assert result["seed"] == 123
    assert result["width"] == 1024
    assert result["height"] == 1024
    assert base64.b64decode(result["image"])
    pipeline.assert_called_once()

    _, kwargs = pipeline.call_args
    assert kwargs["prompt"] == "a red dragon"
    assert kwargs["negative_prompt"] == "blurry"
    assert kwargs["num_inference_steps"] == 28
    assert kwargs["guidance_scale"] == 7


def test_generate_image_clamps_expensive_inputs(monkeypatch):
    _fake_torch(monkeypatch)
    monkeypatch.setattr(worker, "MODEL_SLUG", "juggernaut-xl")
    pipeline = MagicMock(return_value=SimpleNamespace(images=[FakeImage()]))

    result = worker.generate_image(
        {
            "prompt": "a blue city",
            "num_inference_steps": 200,
            "width": 4096,
            "height": 4096,
            "guidance_scale": 30,
            "seed": 999,
        },
        pipeline=pipeline,
    )

    assert result["num_inference_steps"] == 60
    assert result["width"] == 1536
    assert result["height"] == 1536
    assert result["guidance_scale"] == 15.0


def test_handler_returns_error_for_missing_prompt():
    result = worker.handler({"input": {"prompt": ""}})
    assert "prompt is required" in result["error"]


def test_generate_image_uses_configured_model_slug(monkeypatch):
    _fake_torch(monkeypatch)
    monkeypatch.setattr(worker, "MODEL_SLUG", "cyberrealistic-pony")
    pipeline = MagicMock(return_value=SimpleNamespace(images=[FakeImage()]))

    result = worker.generate_image({"prompt": "portrait"}, pipeline=pipeline)

    assert result["model"] == "cyberrealistic-pony"
