"""Builds a valid lesson package zip on disk for tests.

The mp4 is generated once with ffmpeg (2 seconds of black video with silent
audio) and cached for the process, so the fixture is tiny and real. Overrides
let tests break individual fields; the content hash is computed correctly by
default.
"""

import copy
import json
import subprocess
import zipfile
from pathlib import Path

from app.services.packages import compute_content_hash

DEFAULT_LESSON_ID = "ASC606-CON-01"
DEFAULT_COURSE_CODE = "ASC606-CON"

# Passing OMIT as a manifest override value deletes the key, for tests that
# need a manifest missing a required field.
OMIT = object()

# Block headings use the `## <block id>` form video-tool 03 writes; rule 18
# matches manifest.video.blocks ids against them.
DEFAULT_TRANSCRIPT = """## block-01

Percentage of completion is no longer a method under ASC 606.

## block-02

Progress is measured with input or output measures toward satisfying a
performance obligation.

## block-03

The measure chosen must faithfully depict the transfer of control.
"""


def default_manifest() -> dict:
    return {
        "package_version": 1,
        "lesson_id": DEFAULT_LESSON_ID,
        "course_code": DEFAULT_COURSE_CODE,
        "position": 1,
        "title": "Why Percentage of Completion Is No Longer a Method",
        "content_hash": "",  # filled in by build_package
        "video": {
            "duration_seconds": 2,
            "duration_source": "measured",
            "measured_at": "2026-08-20T14:02:11Z",
            "narration_blocks": 3,
            "tts_provider": "elevenlabs",
            "tts_voice_id": "HKFOb9iktHA85uKXydRT",
            "tts_model": "eleven_multilingual_v2",
            # Contiguous, ids matching the transcript headings, last end
            # within 1 second of duration_seconds (rule 18).
            "blocks": [
                {"id": "block-01", "start_seconds": 0.0, "end_seconds": 0.6},
                {"id": "block-02", "start_seconds": 0.6, "end_seconds": 1.3},
                {"id": "block-03", "start_seconds": 1.3, "end_seconds": 2.0},
            ],
        },
        "learning_objectives": [
            {
                "id": "lo-1",
                "text": "Distinguish a method from an output measure under ASC 606",
            },
            {
                "id": "lo-2",
                "text": "Select a measure of progress that depicts transfer of control",
            },
        ],
        "field_of_study": "Accounting",
        "knowledge_level": "Intermediate",
        "prerequisites": "Basic familiarity with ASC 606",
        "advance_preparation": "None",
        "sources": [{"citation": "ASC 606-10-25-27", "role": "primary"}],
        "author": {
            "name": "Test Author",
            "credentials": "CPA",
            "license_jurisdiction": "NH",
            "license_number": "12345",
        },
        "word_count": 0,
        "av_is_additional_learning": True,
    }


def default_questions() -> list:
    return [
        {
            "id": "q-01",
            "kind": "review",
            "after_block": 1,
            "stem": "Under ASC 606, percentage of completion is...",
            "choices": [
                {"id": "a", "text": "A revenue recognition method"},
                {"id": "b", "text": "No longer a method"},
                {"id": "c", "text": "Mandatory for construction"},
            ],
            "correct": "b",
            "feedback": "ASC 606 replaced it with measures of progress; re-study block 1.",
            "objective_ids": ["lo-1"],
        },
        {
            "id": "q-02",
            "kind": "assessment",
            "stem": "Which measure depicts transfer of control?",
            "choices": [
                {"id": "a", "text": "Costs incurred with no relation to progress"},
                {"id": "b", "text": "An output measure of units delivered"},
                {"id": "c", "text": "Cash collected"},
            ],
            "correct": "b",
            "feedback": "Output measures depict the value transferred to the customer.",
            "objective_ids": ["lo-2"],
        },
    ]


_video_bytes_cache: bytes | None = None


def _video_bytes() -> bytes:
    global _video_bytes_cache
    if _video_bytes_cache is None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "video.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "color=c=black:s=64x64:d=2",
                    "-f", "lavfi", "-i", "anullsrc",
                    "-t", "2",
                    str(out),
                ],
                check=True,
                capture_output=True,
            )
            _video_bytes_cache = out.read_bytes()
    return _video_bytes_cache


def _deep_merge(base: dict, overrides: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if value is OMIT:
            merged.pop(key, None)
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def build_package(
    tmp_path: Path,
    *,
    manifest_overrides: dict | None = None,
    questions: list | None = None,
    transcript: str = DEFAULT_TRANSCRIPT,
    tamper_transcript: str | None = None,
    dir_name: str | None = None,
    extra_files: dict[str, bytes] | None = None,
) -> Path:
    """Write a package zip under tmp_path and return its path.

    The content hash is computed over the real file bytes unless
    `manifest_overrides` sets `content_hash` explicitly. `tamper_transcript`
    writes a different transcript than the one hashed, simulating a package
    modified after export.
    """
    manifest = default_manifest()
    questions = questions if questions is not None else default_questions()
    questions_bytes = json.dumps(questions, indent=2).encode()
    video = _video_bytes()

    hash_overridden = manifest_overrides is not None and "content_hash" in manifest_overrides
    if manifest_overrides:
        manifest = _deep_merge(manifest, manifest_overrides)
    if not hash_overridden:
        manifest["content_hash"] = compute_content_hash(
            transcript.encode(), questions_bytes, video
        )

    written_transcript = tamper_transcript if tamper_transcript is not None else transcript

    top = dir_name or manifest.get("lesson_id", DEFAULT_LESSON_ID)
    package_dir = tmp_path / "built" / top
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (package_dir / "questions.json").write_bytes(questions_bytes)
    (package_dir / "transcript.md").write_text(written_transcript)
    (package_dir / "video.mp4").write_bytes(video)
    for name, content in (extra_files or {}).items():
        (package_dir / name).write_bytes(content)

    zip_path = tmp_path / f"{top}.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for path in sorted(package_dir.rglob("*")):
            zf.write(path, f"{top}/{path.relative_to(package_dir)}")
    return zip_path
