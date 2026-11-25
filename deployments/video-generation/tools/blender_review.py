"""Public request and input contract for the pinned Blender review adapter."""
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

from pydantic import BaseModel, Field, model_validator
from typing import Literal

from model_registry import ROOT

SOURCE = "fb7e7cf55f4753d8f81242b7afc62d9ae8338f6e"
BLENDER_ROOT = Path(os.environ.get("BLENDER_REVIEW_RUNTIME", ROOT / "tools/vendor/blender-5.3.0"))
SOURCE_ROOT = ROOT / "tools/vendor/pbz-render-source-fb7e7cf"
IMPORTER_ROOT = ROOT / "tools/vendor/pbz-ueformat/plugins/blender"
SUITE = SOURCE_ROOT / "qa/suites/humanoid_v1_1.json"
NATIVE_CASES = ("Hun_Unarmed_Idle_Loop", "Hun_Unarmed_Run_Fwd_Loop", "Hun_BaiShanDual_Attack_A")
MAX_UPLOAD = 2 * 1024**3
MAX_UNPACKED = 6 * 1024**3
MAX_IMAGES = 512
ALLOWED_SUFFIXES = {".blend", ".json", ".ueanim", ".png", ".jpg", ".jpeg", ".exr", ".tga", ".txt"}


class ReviewParams(BaseModel):
    model_config = {"extra": "forbid"}
    forms: list[Literal["coat_on", "coat_off"]] = Field(default=["coat_on", "coat_off"], min_length=1, max_length=2)
    cases: list[str] = Field(min_length=1, max_length=24)
    sample_indices: list[int] = Field(default=[0, 2, 4], min_length=1, max_length=32)
    views: list[Literal["front", "back", "side", "oblique"]] = Field(default=["front", "oblique"], min_length=1, max_length=4)
    resolution: tuple[int, int] = (1280, 1280)
    samples: int = Field(default=32, ge=1, le=128, strict=True)
    engine: Literal["EEVEE"] = "EEVEE"
    timeout_seconds: int = Field(default=1800, ge=30, le=14400, strict=True)

    @model_validator(mode="after")
    def validate_limits(self):
        for entries in (self.forms, self.cases, self.sample_indices, self.views):
            if len(set(entries)) != len(entries):
                raise ValueError("Forms, cases, sample indices and views must be unique")
        if any(not 128 <= side <= 4096 for side in self.resolution):
            raise ValueError("Resolution sides must be between 128 and 4096")
        if any(not 0 <= i < 128 for i in self.sample_indices):
            raise ValueError("Sample indices start at zero")
        if self.image_count() > MAX_IMAGES:
            raise ValueError(f"No more than {MAX_IMAGES} images per task")
        return self

    def image_count(self):
        return len(self.forms) * len(self.cases) * len(self.sample_indices) * len(self.views) * 2


class ReviewRequest(BaseModel):
    model_config = {"extra": "forbid"}
    kind: Literal["blender_review"] = "blender_review"
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_commit: Literal[SOURCE, "fb7e7cf"] = SOURCE
    priority: int = Field(default=0, ge=-1000, le=1000, strict=True)
    params: ReviewParams


def ready():
    return (BLENDER_ROOT / "blender").is_file() and SUITE.is_file() and (
        IMPORTER_ROOT / "io_scene_ueformat/__init__.py").is_file()


def validate_samples(params):
    lengths = {case["id"]: len(case["samples"]) for case in json.loads(SUITE.read_text())["cases"]}
    lengths.update({name: 5 for name in NATIVE_CASES})
    for name in params.cases:
        if name not in lengths:
            raise ValueError(f"Unknown case: {name}")
        if max(params.sample_indices) >= lengths[name]:
            raise ValueError(f"Case {name} has {lengths[name]} samples")


def relative_name(name):
    if not isinstance(name, str) or "\\" in name or not name or len(name) > 512:
        raise ValueError("Invalid asset path")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Only relative asset paths within the archive are accepted")
    return path


def inspect_archive(path):
    """Validate names and advertised expansion before a queued worker extracts anything."""
    with zipfile.ZipFile(path) as archive:
        entries = {}
        sizes = 0
        infos = archive.infolist()
        if len(infos) > 4096:
            raise ValueError("Archive contains too many entries")
        for item in infos:
            relative = relative_name(item.filename)
            if stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1:
                raise ValueError("Symlinks and encrypted entries are forbidden")
            if item.is_dir():
                continue
            if relative.suffix.lower() not in ALLOWED_SUFFIXES:
                raise ValueError(f"Unsupported archived file type: {relative.suffix}")
            key = relative.as_posix()
            if key in entries:
                raise ValueError("Duplicate archive path")
            entries[key] = item
            sizes += item.file_size
            if sizes > MAX_UNPACKED:
                raise ValueError("Archive expands beyond 6 GiB")
        if "manifest.json" not in entries or entries["manifest.json"].file_size > 64 * 1024:
            raise ValueError("Archive needs a manifest.json no larger than 64 KiB")
        payload = json.loads(archive.read(entries["manifest.json"]))
        if not isinstance(payload, dict) or not isinstance(payload.get("forms"), dict):
            raise ValueError("Manifest needs a forms object")
        return payload, entries


def resolve_manifest(payload, names, params):
    def asset(value, extension):
        path = relative_name(value)
        if path.suffix.lower() != extension or path.as_posix() not in names:
            raise ValueError(f"Missing {extension} asset: {path}")
        return path.as_posix()

    forms = {name: asset(payload["forms"].get(name), ".blend") for name in params.forms}
    donor = asset(payload.get("donor"), ".blend")
    donor_report = str(PurePosixPath(donor).with_name("sampling_report.json"))
    if donor_report not in names:
        raise ValueError("Missing sampling_report.json beside the donor")
    control = asset(payload.get("cc0_control"), ".blend")
    supplied = payload.get("animations", {})
    if not isinstance(supplied, dict):
        raise ValueError("animations must be an object keyed by the pinned clip name")
    animations = {name: asset(supplied.get(name), ".ueanim") for name in params.cases if name in NATIVE_CASES}
    return {"forms": forms, "donor": donor, "cc0_control": control, "animations": animations}


def valid_sha(value):
    return re.fullmatch(r"[0-9a-f]{64}", value) is not None
