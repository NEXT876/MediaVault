"""Read AI generation metadata from PNG files and summarize prompts.

ComfyUI stores how an image was generated in a ``prompt`` PNG text chunk:
the API workflow as JSON. The prompts are found by following the sampler's
conditioning links to the text encoders.

The result is a flat dict (``generator``, ``prompt``, ``negative_prompt``,
``model``, ``sampler``, ``steps``, ``cfg_scale``, ``seed``, ``width``,
``height``; missing keys are omitted) stored in ``MediaItem.ai_meta``. It
drives AI configs, duplicate detection by generation and the analysis dialog
(:func:`summarize_prompts`). The PNG is parsed with the standard library only,
skipping image data, so reading is fast even for large files.
"""

import json
import logging
import os
import re
import struct
import zlib
from collections import Counter
from collections.abc import Iterable
from typing import Any

from mediavault.models import MediaItem

logger = logging.getLogger(__name__)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _decode_text(raw: bytes) -> str:
    """Decode PNG text as UTF-8, falling back to Latin-1 (the tEXt standard)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _read_text_chunks(path: str) -> dict[str, str]:
    """Return the tEXt/iTXt chunks of a PNG keyed by their keyword.

    Image data chunks are skipped with ``seek``, and reading stops at ``IEND``.
    Compressed iTXt chunks are inflated; broken ones are ignored. When a keyword
    appears twice, the first value wins. Non-PNG files give an empty dict.

    Raises:
        OSError: When the file cannot be read.
    """
    chunks: dict[str, str] = {}
    with open(path, "rb") as f:
        if f.read(8) != _PNG_SIGNATURE:
            return chunks
        while True:
            header = f.read(8)
            if len(header) < 8:
                break
            length, kind = struct.unpack(">I4s", header)
            if kind not in (b"tEXt", b"iTXt"):
                if kind == b"IEND":
                    break
                # IDAT holds the image; skip it instead of reading the whole file.
                f.seek(length + 4, os.SEEK_CUR)
                continue
            data = f.read(length)
            f.read(4)  # shortcut: CRC skip, add check only if corrupt files matter
            if kind == b"tEXt":
                key, _, value = data.partition(b"\x00")
                chunks.setdefault(_decode_text(key), _decode_text(value))
            elif kind == b"iTXt":
                key, _, rest = data.partition(b"\x00")
                if len(rest) < 2:
                    continue
                compressed = rest[0]
                text = rest[2:]
                _, _, text = text.partition(b"\x00")  # language tag
                _, _, text = text.partition(b"\x00")  # translated keyword
                if compressed:
                    try:
                        text = zlib.decompress(text)
                    except zlib.error:
                        continue
                chunks.setdefault(_decode_text(key), _decode_text(text))
    return chunks


def _as_int(value: Any) -> int | None:
    """Convert a metadata value to int, or None if it is not numeric."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    """Convert a metadata value to float, or None if it is not numeric."""
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _find_prompt_text(data: dict[str, Any], node_id: Any, seen: set[str]) -> str:
    """Follow conditioning links until a text encoder node is found.

    Walks input links depth-first from ``node_id`` and returns the text of the
    first ``CLIPTextEncode`` node; ``seen`` guards against cycles. Returns an
    empty string when no encoder is reachable.
    """
    key = str(node_id)
    if key in seen:
        return ""
    seen.add(key)
    node = data.get(key)
    if not isinstance(node, dict):
        return ""
    inputs = node.get("inputs", {})
    if node.get("class_type") == "CLIPTextEncode":
        text = inputs.get("text", "")
        return text.strip() if isinstance(text, str) else ""
    for value in inputs.values():
        if isinstance(value, list) and value:
            text = _find_prompt_text(data, value[0], seen)
            if text:
                return text
    return ""


def _parse_comfyui(data: dict[str, Any]) -> dict[str, Any]:
    """Parse a ComfyUI ``prompt`` chunk (API workflow JSON).

    Uses the first (Advanced) KSampler for sampler settings and follows its
    positive/negative inputs to the prompt texts. Without a resolvable link, all
    text encoder prompts are joined as the positive prompt. Model and size come
    from the checkpoint loader and the empty latent image node.
    """
    nodes = [node for node in data.values() if isinstance(node, dict)]
    meta: dict[str, Any] = {"generator": "ComfyUI"}
    positive = negative = ""

    sampler = next(
        (
            node
            for node in nodes
            if node.get("class_type") in ("KSampler", "KSamplerAdvanced")
        ),
        None,
    )
    if sampler is not None:
        inputs = sampler.get("inputs", {})
        positive_link = inputs.get("positive")
        negative_link = inputs.get("negative")
        if isinstance(positive_link, list) and positive_link:
            positive = _find_prompt_text(data, positive_link[0], set())
        if isinstance(negative_link, list) and negative_link:
            negative = _find_prompt_text(data, negative_link[0], set())
        if isinstance(inputs.get("sampler_name"), str):
            meta["sampler"] = inputs["sampler_name"]
        for source, target, converter in (
            ("steps", "steps", _as_int),
            ("cfg", "cfg_scale", _as_float),
            ("seed", "seed", _as_int),
            ("noise_seed", "seed", _as_int),
        ):
            if source in inputs and target not in meta:
                value = converter(inputs[source])
                if value is not None:
                    meta[target] = value

    if not positive:
        # Heuristic: without a resolvable sampler link, treat every text node as prompt.
        texts = (
            node.get("inputs", {}).get("text", "")
            for node in nodes
            if node.get("class_type") == "CLIPTextEncode"
        )
        positive = ", ".join(
            text.strip() for text in texts if isinstance(text, str) and text.strip()
        )

    meta["prompt"] = positive
    meta["negative_prompt"] = negative

    for node in nodes:
        if node.get("class_type") in ("CheckpointLoaderSimple", "CheckpointLoader"):
            name = node.get("inputs", {}).get("ckpt_name")
            if isinstance(name, str) and name:
                meta["model"] = name
                break

    for node in nodes:
        if node.get("class_type") == "EmptyLatentImage":
            width = _as_int(node.get("inputs", {}).get("width"))
            height = _as_int(node.get("inputs", {}).get("height"))
            if width is not None and height is not None:
                meta["width"] = width
                meta["height"] = height
            break
    return meta


def extract_ai_metadata(path: str) -> dict[str, Any] | None:
    """Return generation metadata from a PNG, or None if none is recognized.

    Parses the ComfyUI workflow (needs a prompt or a model). Non-PNG files and
    unreadable files return None.

    Args:
        path: Image file to inspect.

    Returns:
        The metadata dict described in the module docstring, or None.
    """
    # shortcut: PNG only, add EXIF/XMP if JPEG AI images matter
    if os.path.splitext(path)[1].lower() != ".png":
        return None
    try:
        chunks = _read_text_chunks(path)
    except OSError:
        logger.warning("Could not read image: %s", path)
        return None

    if "prompt" in chunks:
        try:
            data = json.loads(chunks["prompt"])
        except ValueError:
            data = None
        if isinstance(data, dict):
            meta = _parse_comfyui(data)
            if meta.get("prompt") or meta.get("model"):
                return meta
    return None


def ai_duplicate_key(meta: dict[str, Any]) -> tuple[str, str, str, str] | None:
    """Return the generation identity of an image, if it can be determined.

    Two images with the same prompt, negative prompt, seed and model are the
    same generation and must not both enter the database.
    """
    prompt = str(meta.get("prompt") or "").strip()
    seed_value = meta.get("seed")
    seed = "" if seed_value is None else str(seed_value).strip()
    if not prompt or not seed:
        return None
    return (
        prompt,
        str(meta.get("negative_prompt") or "").strip(),
        seed,
        str(meta.get("model") or "").strip(),
    )


def format_ai_meta(meta: dict[str, Any]) -> str:
    """Format generation metadata as one human-readable line.

    Example: ``ComfyUI · model · Euler a · 20 Schritte · CFG 7 · Seed 1 · 512×768``.
    """
    parts = [
        str(meta[key]) for key in ("generator", "model", "sampler") if meta.get(key)
    ]
    if meta.get("steps"):
        parts.append(f"{meta['steps']} Schritte")
    if meta.get("cfg_scale"):
        parts.append(f"CFG {meta['cfg_scale']:g}")
    if meta.get("seed") not in (None, ""):
        parts.append(f"Seed {meta['seed']}")
    if meta.get("width") and meta.get("height"):
        parts.append(f"{meta['width']}×{meta['height']}")
    return " · ".join(parts)


def _prompt_tags(prompt: str) -> list[str]:
    """Split a prompt into lowercase tags, dropping parentheses and weights."""
    tags = []
    for raw in prompt.split(","):
        tag = raw.strip()
        if tag.startswith("(") and tag.endswith(")"):
            tag = tag[1:-1]
        tag = re.sub(r":[\d.]+$", "", tag).strip()
        if tag:
            tags.append(tag.casefold())
    return tags


def summarize_prompts(entries: Iterable[MediaItem]) -> dict[str, Any]:
    """Compute local prompt statistics for the analysis dialog.

    Only entries with a non-empty AI prompt are counted.

    Returns:
        A dict with ``count``, ``average_score``, ``average_prompt_length``,
        the ten most common ``top_tags``, ``models`` and ``samplers``,
        ``top_tags_by_score`` (tags used at least three times, ranked by average
        score) and the ten best-rated ``top_prompts`` (prompt cut to 160 chars).
    """
    ai_entries = [
        entry for entry in entries if (entry.ai_meta.get("prompt") or "").strip()
    ]
    count = len(ai_entries) or 1  # avoids dividing by zero for an empty list
    tag_counts: Counter[str] = Counter()
    tag_scores: dict[str, list[int]] = {}
    for entry in ai_entries:
        for tag in _prompt_tags(entry.ai_meta["prompt"]):
            tag_counts[tag] += 1
            tag_scores.setdefault(tag, []).append(entry.score)
    models = Counter(m for e in ai_entries if (m := e.ai_meta.get("model")))
    samplers = Counter(s for e in ai_entries if (s := e.ai_meta.get("sampler")))

    scored_tags = [
        (tag, len(scores), sum(scores) / len(scores))
        for tag, scores in tag_scores.items()
        if len(scores) >= 3
    ]
    scored_tags.sort(key=lambda item: (-item[2], -item[1], item[0]))

    top_prompts = sorted(ai_entries, key=lambda entry: -entry.score)[:10]
    return {
        "count": len(ai_entries),
        "average_score": sum(entry.score for entry in ai_entries) / count,
        "average_prompt_length": sum(
            len(entry.ai_meta["prompt"]) for entry in ai_entries
        )
        / count,
        "top_tags": tag_counts.most_common(10),
        "models": models.most_common(10),
        "samplers": samplers.most_common(10),
        "top_tags_by_score": scored_tags[:10],
        "top_prompts": [
            {
                "title": entry.title,
                "score": entry.score,
                "prompt": entry.ai_meta["prompt"][:160],
            }
            for entry in top_prompts
        ],
    }
