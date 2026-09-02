from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol
from urllib.request import urlopen


class TTSProvider(Protocol):
    def synthesize(self, text: str, output_path: Path) -> Path: ...


LAHGTNA_DEFAULT_EGYPTIAN_REF_URL = "https://huggingface.co/spaces/oddadmix/lahgtna-chatterbox-demo/resolve/main/egypt-ref.wav?download=true"


def _chunk_egyptian_text(text: str, max_chars: int = 120) -> list[str]:
    text = " ".join(text.split()).strip()
    if not text:
        return []
    sentences = [s.strip() for s in re.split(r"(?<=[.!؟!،؛])\s+", text) if s.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences or [text]:
        if len(sentence) <= max_chars:
            candidate = f"{current} {sentence}".strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = sentence
            continue
        for word in sentence.split():
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = word
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks


def _patch_lahgtna_cpu_loader(repo: Path) -> None:
    target = repo / "src" / "chatterbox" / "mtl_tts.py"
    if not target.exists():
        raise FileNotFoundError(f"Lahgtna Chatterbox loader not found: {target}")
    source = target.read_text(encoding="utf-8")
    patched = source.replace(
        "        ve = VoiceEncoder()\n        ve.load_state_dict(torch.load(ckpt_dir / \"ve.pt\", weights_only=True))\n",
        "        ve = VoiceEncoder()\n        map_location = torch.device(\"cpu\") if str(device) in {\"cpu\", \"mps\"} else None\n        ve.load_state_dict(torch.load(ckpt_dir / \"ve.pt\", map_location=map_location, weights_only=True))\n",
    )
    patched = patched.replace(
        "        s3gen = S3Gen()\n        s3gen.load_state_dict(torch.load(ckpt_dir / \"s3gen.pt\", weights_only=True))\n",
        "        s3gen = S3Gen()\n        s3gen.load_state_dict(torch.load(ckpt_dir / \"s3gen.pt\", map_location=map_location, weights_only=True))\n",
    )
    if patched != source:
        target.write_text(patched, encoding="utf-8")


def _resolve_reference_audio() -> tuple[Path, str]:
    configured = os.getenv("VIDEO_PILOT_EGYPTIAN_REF_AUDIO", "").strip()
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Egyptian reference audio not found: {path}")
        return path, "configured"

    cached = Path(tempfile.gettempdir()) / "lahgtna-egypt-ref.wav"
    if not cached.is_file() or cached.stat().st_size < 10000:
        with urlopen(LAHGTNA_DEFAULT_EGYPTIAN_REF_URL, timeout=30) as response:
            cached.write_bytes(response.read())
    if not cached.is_file() or cached.stat().st_size < 10000:
        raise RuntimeError("Could not obtain the default Egyptian Lahgtna reference audio")
    return cached, "bundled_demo_reference"


class LahgtnaChatterboxProvider:
    """Egyptian-Arabic TTS using the open-source Lahgtna/Chatterbox model."""

    def synthesize(self, text: str, output_path: Path) -> Path:
        repo = Path(tempfile.gettempdir()) / "lahgtna-chatterbox"
        if not repo.exists():
            subprocess.run(
                ["git", "clone", "--depth", "1", "https://github.com/Oddadmix/lahgtna-chatterbox.git", str(repo)],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            subprocess.run(
                ["python", "-m", "pip", "install", "-r", str(repo / "requirments.txt")],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )

        _patch_lahgtna_cpu_loader(repo)
        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        chunks = _chunk_egyptian_text(text)
        if not chunks:
            raise ValueError("Egyptian TTS received empty text")

        ref_audio, ref_source = _resolve_reference_audio()
        print(f"LAHGTNA_REFERENCE_SOURCE={ref_source}")
        payload = Path(tempfile.gettempdir()) / "lahgtna_chunks.json"
        payload.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
        runner = Path(tempfile.gettempdir()) / "lahgtna_batch_infer.py"
        runner.write_text(
            """
import json, os, sys
from pathlib import Path
import torch
import torchaudio as ta
from inference import TTSEngine
from config import LANGUAGE_CODES
repo, payload, out, ref = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
chunks = json.loads(payload.read_text(encoding='utf-8'))
engine = TTSEngine()
lang_cfg = LANGUAGE_CODES['eg']
ref_audio = ref.expanduser().resolve()
if not ref_audio.is_file():
    raise FileNotFoundError(f'Egyptian reference audio not found: {ref_audio}')
parts = []
metadata = []
for index, chunk in enumerate(chunks, 1):
    wav = engine.synthesise(chunk, language_code=lang_cfg['code'], ref_audio_path=ref_audio,
                             exaggeration=0.72, temperature=0.72, cfg_weight=0.45)
    frames = int(wav.shape[-1])
    duration = frames / float(engine.sample_rate)
    parts.append(wav)
    metadata.append({'text': chunk, 'duration': duration})
    print(f'LAHGTNA_EGYPTIAN_CHUNK={index}/{len(chunks)} CHARS={len(chunk)} DURATION={duration:.3f}', flush=True)
combined = torch.cat(parts, dim=-1)
out.parent.mkdir(parents=True, exist_ok=True)
ta.save(str(out), combined, engine.sample_rate)
out.with_suffix('.chunks.json').write_text(json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
print(f'LAHGTNA_EGYPTIAN_AUDIO={out} SAMPLE_RATE={engine.sample_rate}', flush=True)
""".strip() + "\n", encoding="utf-8"
        )

        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo / "src") + os.pathsep + env.get("PYTHONPATH", "")
        wav = (output_path.with_suffix(".wav")).resolve()
        try:
            completed = subprocess.run(
                ["python", str(runner), str(repo), str(payload), str(wav), str(ref_audio)],
                check=True, cwd=str(repo / "src"), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
        except subprocess.CalledProcessError as exc:
            details = (exc.stdout or "").strip()
            raise RuntimeError(
                f"Lahgtna TTS subprocess failed (exit {exc.returncode}):\n{details[-6000:]}"
            ) from exc

        if completed.stdout:
            print(completed.stdout, end="")
        chunks_meta = wav.with_suffix(".chunks.json")
        if not chunks_meta.is_file():
            raise RuntimeError("Lahgtna TTS produced no chunk timing metadata")
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav), "-ac", "1", "-ar", "24000",
             "-codec:a", "libmp3lame", "-q:a", "4", str(output_path.resolve())],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        output_path.with_suffix(".chunks.json").write_text(
            chunks_meta.read_text(encoding="utf-8"), encoding="utf-8"
        )
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError("Egyptian TTS produced no audio")
        return output_path


class EdgeTTSProvider:
    def __init__(self, voice: str = "ar-EG-ShakirNeural") -> None:
        self.voice = voice

    def synthesize(self, text: str, output_path: Path) -> Path:
        import asyncio
        import edge_tts

        output_path.parent.mkdir(parents=True, exist_ok=True)
        timing_path = output_path.with_suffix(".words.json")

        async def _run() -> None:
            communicate = edge_tts.Communicate(text, self.voice)
            timings: list[dict[str, object]] = []
            with output_path.open("wb") as audio_file:
                async for message in communicate.stream():
                    if message["type"] == "audio":
                        audio_file.write(message["data"])
                    elif message["type"] == "WordBoundary":
                        timings.append({
                            "text": str(message.get("text", "")),
                            "offset_100ns": int(message.get("offset", 0)),
                            "duration_100ns": int(message.get("duration", 0)),
                        })
            timing_path.write_text(json.dumps(timings, ensure_ascii=False), encoding="utf-8")

        asyncio.run(_run())
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError("Edge TTS produced no audio")
        if not timing_path.is_file():
            raise RuntimeError("Edge TTS produced no word timing data")
        return output_path


def synthesize_with_fallback(text: str, output_path: Path, providers: list[TTSProvider]) -> Path:
    last_error: Exception | None = None
    for provider in providers:
        try:
            result = provider.synthesize(text, output_path)
            if result.is_file() and result.stat().st_size > 0:
                return result
        except Exception as exc:
            last_error = exc
    if last_error:
        raise RuntimeError("All configured TTS providers failed") from last_error
    raise RuntimeError("No TTS provider configured")