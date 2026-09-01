from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol


class TTSProvider(Protocol):
    def synthesize(self, text: str, output_path: Path) -> Path: ...


def _chunk_egyptian_text(text: str, max_chars: int = 280) -> list[str]:
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
    patched = source
    patched = patched.replace(
        "        ve = VoiceEncoder()\n        ve.load_state_dict(torch.load(ckpt_dir / \"ve.pt\", weights_only=True))\n",
        "        ve = VoiceEncoder()\n        map_location = torch.device(\"cpu\") if str(device) in {\"cpu\", \"mps\"} else None\n        ve.load_state_dict(torch.load(ckpt_dir / \"ve.pt\", map_location=map_location, weights_only=True))\n",
    )
    patched = patched.replace(
        "        s3gen = S3Gen()\n        s3gen.load_state_dict(torch.load(ckpt_dir / \"s3gen.pt\", weights_only=True))\n",
        "        s3gen = S3Gen()\n        s3gen.load_state_dict(torch.load(ckpt_dir / \"s3gen.pt\", map_location=map_location, weights_only=True))\n",
    )
    if patched != source:
        target.write_text(patched, encoding="utf-8")


class LahgtnaChatterboxProvider:
    """Egyptian-Arabic TTS using Lahgtna/Chatterbox with short-form chunks."""

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

        payload = Path(tempfile.gettempdir()) / "lahgtna_chunks.json"
        payload.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
        runner = Path(tempfile.gettempdir()) / "lahgtna_batch_infer.py"
        runner.write_text(
            """
import json, sys
from pathlib import Path
import torch
import torchaudio as ta
from inference import TTSEngine
from config import LANGUAGE_CODES
repo, payload, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
chunks = json.loads(payload.read_text(encoding='utf-8'))
engine = TTSEngine()
lang_cfg = LANGUAGE_CODES['eg']
relative_ref = Path(lang_cfg['ref'].lstrip('./'))
ref_candidates = (repo / 'src' / relative_ref, repo / relative_ref)
ref_audio = next((p for p in ref_candidates if p.is_file() and p.stat().st_size > 0), None)
if ref_audio is None:
    checked = ', '.join(str(p) for p in ref_candidates)
    raise FileNotFoundError(f'Egyptian reference audio not found. Checked: {checked}')
parts = []
for index, chunk in enumerate(chunks, 1):
    wav = engine.synthesise(chunk, language_code=lang_cfg['code'], ref_audio_path=ref_audio,
                             exaggeration=0.55, temperature=0.75, cfg_weight=0.45)
    parts.append(wav)
    print(f'TTS_CHUNK={index}/{len(chunks)} CHARS={len(chunk)}', flush=True)
combined = torch.cat(parts, dim=-1)
out.parent.mkdir(parents=True, exist_ok=True)
ta.save(str(out), combined, engine.sample_rate)
print(f'TTS_AUDIO={out} SAMPLE_RATE={engine.sample_rate}', flush=True)
""".strip() + "\n", encoding="utf-8"
        )

        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo / "src") + os.pathsep + env.get("PYTHONPATH", "")
        wav = (output_path.with_suffix(".wav")).resolve()
        try:
            completed = subprocess.run(
                ["python", str(runner), str(repo), str(payload), str(wav)],
                check=True, cwd=str(repo / "src"), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
        except subprocess.CalledProcessError as exc:
            details = (exc.stdout or "").strip()
            tail = details[-6000:] if details else "(no TTS subprocess output captured)"
            raise RuntimeError(f"Lahgtna TTS subprocess failed (exit {exc.returncode}):\n{tail}") from exc

        if completed.stdout:
            print(completed.stdout, end="")

        # Keep this conversion intentionally lightweight. The previous loudnorm
        # filter caused ffmpeg to exit 254 on the pilot runner after a long CPU
        # TTS pass. Render-time audio is already 24 kHz PCM; stereo expansion and
        # loudness normalization are not required for the pilot acceptance gate.
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(wav), "-ac", "1", "-ar", "24000",
                 "-codec:a", "libmp3lame", "-q:a", "4", str(output_path.resolve())],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise RuntimeError(f"TTS WAV->MP3 conversion failed (exit {exc.returncode}): {stderr[-4000:]}") from exc
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
        async def _run() -> None:
            await edge_tts.Communicate(text, self.voice).save(str(output_path))
        asyncio.run(_run())
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
