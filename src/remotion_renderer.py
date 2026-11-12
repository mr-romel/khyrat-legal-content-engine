from __future__ import annotations

import json
import math
import shutil
import subprocess
import uuid
from pathlib import Path


def _duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Remotion input duration probe failed for {path}: {result.stderr[-1200:]}")
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"Remotion could not read media duration for {path}") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError(f"Remotion input has invalid duration: {path}")
    return duration


def render_reel_with_remotion(
    *,
    scenes: list[Path],
    voice_audio: Path,
    slogan_audio: Path,
    logo: Path,
    script: str,
    output_video: Path,
    fps: int = 30,
) -> Path:
    """Render the existing AI image pack and narration using the sole Remotion renderer."""
    if len(scenes) != 5:
        raise RuntimeError(f"REMOTION_INPUT_INVALID: expected exactly 5 generated scene images, got {len(scenes)}")
    for item in [*scenes, voice_audio, slogan_audio, logo]:
        if not item.is_file() or item.stat().st_size < 100:
            raise RuntimeError(f"REMOTION_INPUT_MISSING: {item}")

    project_dir = Path(__file__).resolve().parents[1] / "remotion"
    cli = project_dir / "node_modules" / ".bin" / "remotion"
    if not cli.is_file():
        raise RuntimeError("REMOTION_DEPENDENCIES_MISSING: run npm install in remotion/ before rendering")

    # Remotion executes with cwd=project_dir; always pass an absolute output path
    # so the renderer and the post-render validator address the same MP4.
    output_video = output_video.resolve()
    run_id = uuid.uuid4().hex
    public_root = project_dir / "public" / "render-assets" / run_id
    public_root.mkdir(parents=True, exist_ok=False)
    output_video.parent.mkdir(parents=True, exist_ok=True)
    voice_duration = _duration(voice_audio)
    slogan_duration = _duration(slogan_audio)
    if voice_duration > 34.5:
        raise RuntimeError(f"REMOTION_NARRATION_TOO_LONG: {voice_duration:.2f}s exceeds 34.5s content budget")
    if slogan_duration > 8.0:
        raise RuntimeError(f"REMOTION_SLOGAN_TOO_LONG: {slogan_duration:.2f}s exceeds 8s")
    voice_frames = max(1, math.ceil(voice_duration * fps))
    # Keep the final file inside the 40-second delivery contract; do not append
    # an extra 0.8s tail after the spoken sign-off.
    total_frames = voice_frames + math.ceil(slogan_duration * fps)

    try:
        scene_props = []
        scene_span = math.ceil(voice_frames / len(scenes)) + math.ceil(.45 * fps)
        for index, scene in enumerate(scenes, start=1):
            name = f"scene_{index:02d}{scene.suffix.lower() or '.jpg'}"
            shutil.copy2(scene, public_root / name)
            scene_props.append({
                "src": f"render-assets/{run_id}/{name}",
                "durationFrames": scene_span,
            })

        assets = {}
        for key, source in (("voiceAudio", voice_audio), ("sloganAudio", slogan_audio), ("logo", logo)):
            suffix = source.suffix.lower() or (".wav" if "Audio" in key else ".png")
            name = f"{key}{suffix}"
            shutil.copy2(source, public_root / name)
            assets[key] = f"render-assets/{run_id}/{name}"

        sentences = [part.strip() for part in __import__("re").split(r"(?<=[؟!.])\s+", script) if part.strip()]
        weights = [max(1, len(part)) for part in sentences]
        subtitles = []
        cursor = 0
        total_weight = sum(weights) or 1
        for index, (sentence, weight) in enumerate(zip(sentences, weights)):
            end = voice_frames if index == len(sentences) - 1 else round(voice_frames * sum(weights[:index + 1]) / total_weight)
            if end - cursor >= max(6, int(.35 * fps)):
                subtitles.append({"text": sentence, "startFrame": cursor, "endFrame": end})
            cursor = end

        props = {
            "scenes": scene_props,
            **assets,
            "subtitles": subtitles,
            "voiceFrames": voice_frames,
            "totalFrames": total_frames,
            "fps": fps,
        }
        props_path = public_root / "props.json"
        props_path.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
        result = subprocess.run(
            [str(cli), "render", "src/index.ts", "KhyratLegalReel", str(output_video),
             f"--props={props_path}", "--codec=h264", "--crf=18", "--pixel-format=yuv420p",
             "--concurrency=2"],
            cwd=project_dir, capture_output=True, text=True, timeout=1200, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "REMOTION_RENDER_FAILED: " + (result.stderr or result.stdout)[-6000:]
            )
        if not output_video.is_file() or output_video.stat().st_size < 100_000:
            raise RuntimeError("REMOTION_OUTPUT_INVALID: render command completed without a valid MP4")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "json", str(output_video)],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if probe.returncode != 0:
            raise RuntimeError("REMOTION_OUTPUT_PROBE_FAILED: " + probe.stderr[-1200:])
        streams = json.loads(probe.stdout).get("streams", [])
        if not streams or streams[0].get("width") != 1080 or streams[0].get("height") != 1920:
            raise RuntimeError(f"REMOTION_OUTPUT_DIMENSIONS_INVALID: {streams}")
        print(
            f"REEL_STAGE renderer=REMOTION duration={total_frames / fps:.2f}s "
            f"scenes={len(scenes)} subtitles={len(subtitles)} size=1080x1920"
        )
        return output_video
    finally:
        shutil.rmtree(public_root, ignore_errors=True)
