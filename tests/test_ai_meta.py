import json
import struct
import zlib

from mediavault.ai_meta import (
    ai_duplicate_key,
    extract_ai_metadata,
    format_ai_meta,
    summarize_prompts,
)
from mediavault.models import MediaItem

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind, data):
    crc = zlib.crc32(kind + data)
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def _write_png(path, chunks):
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    path.write_bytes(
        _PNG_SIGNATURE + _chunk(b"IHDR", ihdr) + b"".join(chunks) + _chunk(b"IEND", b"")
    )


def _text_chunk(key, value):
    return _chunk(b"tEXt", key.encode() + b"\x00" + value.encode())


def _itxt_chunk(key, value, compressed):
    text = zlib.compress(value.encode()) if compressed else value.encode()
    data = (
        key.encode()
        + b"\x00"
        + bytes([1 if compressed else 0, 0])
        + b"\x00"  # language tag
        + b"\x00"  # translated keyword
        + text
    )
    return _chunk(b"iTXt", data)


_A1111 = (
    "masterpiece, best quality, castle\n"
    "Negative prompt: blurry, low quality\n"
    "Steps: 20, Sampler: DPM++ 2M Karras, CFG scale: 7, Seed: 12345, "
    "Size: 512x768, Model: dreamshaper_8"
)


def test_a1111_metadata(tmp_path):
    path = tmp_path / "a.png"
    _write_png(path, [_text_chunk("parameters", _A1111)])

    meta = extract_ai_metadata(str(path))

    assert meta == {
        "generator": "A1111",
        "prompt": "masterpiece, best quality, castle",
        "negative_prompt": "blurry, low quality",
        "model": "dreamshaper_8",
        "sampler": "DPM++ 2M Karras",
        "steps": 20,
        "cfg_scale": 7.0,
        "seed": 12345,
        "width": 512,
        "height": 768,
    }


def _comfy_graph():
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 42,
                "steps": 30,
                "cfg": 6.5,
                "sampler_name": "euler",
                "positive": ["6", 0],
                "negative": ["7", 0],
            },
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sdxl.safetensors"},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 1024, "height": 1024},
        },
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "a castle at dawn"}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry"}},
    }


def test_comfyui_metadata(tmp_path):
    path = tmp_path / "c.png"
    _write_png(path, [_text_chunk("prompt", json.dumps(_comfy_graph()))])

    meta = extract_ai_metadata(str(path))

    assert meta == {
        "generator": "ComfyUI",
        "prompt": "a castle at dawn",
        "negative_prompt": "blurry",
        "model": "sdxl.safetensors",
        "sampler": "euler",
        "steps": 30,
        "cfg_scale": 6.5,
        "seed": 42,
        "width": 1024,
        "height": 1024,
    }


def test_comfyui_falls_back_to_all_text_nodes(tmp_path):
    path = tmp_path / "c.png"
    graph = {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "castle, dawn"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "soft light"}},
    }
    _write_png(path, [_text_chunk("prompt", json.dumps(graph))])

    meta = extract_ai_metadata(str(path))

    assert meta["prompt"] == "castle, dawn, soft light"


def test_itxt_compressed_and_uncompressed(tmp_path):
    for compressed in (False, True):
        path = tmp_path / f"{compressed}.png"
        _write_png(path, [_itxt_chunk("parameters", _A1111, compressed)])

        meta = extract_ai_metadata(str(path))

        assert meta is not None
        assert meta["prompt"] == "masterpiece, best quality, castle"


def test_png_without_metadata_returns_none(tmp_path):
    path = tmp_path / "plain.png"
    _write_png(path, [])

    assert extract_ai_metadata(str(path)) is None


def test_non_png_returns_none(tmp_path):
    path = tmp_path / "a.jpg"
    _write_png(path, [_text_chunk("parameters", _A1111)])

    assert extract_ai_metadata(str(path)) is None


def test_format_ai_meta_skips_empty_values():
    meta = {
        "generator": "A1111",
        "model": "dreamshaper_8",
        "sampler": "Euler a",
        "steps": 20,
        "cfg_scale": 7.0,
        "seed": 0,
        "width": 512,
        "height": 768,
    }

    text = format_ai_meta(meta)

    assert text == "A1111 · dreamshaper_8 · Euler a · 20 Schritte · CFG 7 · 512×768"
    assert format_ai_meta({}) == ""


def _ai_entry(title, prompt, score, model="m", sampler="euler"):
    return MediaItem(
        title,
        score=score,
        group="G",
        ai_meta={
            "generator": "A1111",
            "prompt": prompt,
            "negative_prompt": "",
            "model": model,
            "sampler": sampler,
        },
    )


def test_summarize_prompts_counts_tags_models_and_scores():
    entries = [
        _ai_entry("A", "castle, (dawn:1.2)", 90),
        _ai_entry("B", "castle, forest", 60),
        _ai_entry("C", "(Castle), forest", 30),
        MediaItem("D", score=100),  # ignored, no prompt
    ]

    summary = summarize_prompts(entries)

    assert summary["count"] == 3
    assert summary["average_score"] == 60
    assert summary["top_tags"][0] == ("castle", 3)
    assert summary["models"] == [("m", 3)]
    assert summary["samplers"] == [("euler", 3)]
    assert summary["top_tags_by_score"][0] == ("castle", 3, 60)
    assert [item["title"] for item in summary["top_prompts"]] == ["A", "B", "C"]


def test_summarize_prompts_handles_empty_input():
    summary = summarize_prompts([MediaItem("A")])

    assert summary["count"] == 0
    assert summary["top_tags"] == []


def test_ai_duplicate_key_identifies_same_generation():
    meta = {
        "prompt": " castle ",
        "negative_prompt": "blurry",
        "seed": 42,
        "model": "m",
    }
    same = {
        "prompt": "castle",
        "negative_prompt": "blurry",
        "seed": "42",
        "model": "m",
    }
    other_seed = {**meta, "seed": 43}
    other_model = {**meta, "model": "n"}

    assert ai_duplicate_key(meta) == ai_duplicate_key(same)
    assert ai_duplicate_key(meta) != ai_duplicate_key(other_seed)
    assert ai_duplicate_key(meta) != ai_duplicate_key(other_model)


def test_ai_duplicate_key_requires_prompt_and_seed():
    assert ai_duplicate_key({"prompt": "castle"}) is None
    assert ai_duplicate_key({"seed": 42}) is None
    assert ai_duplicate_key({}) is None
