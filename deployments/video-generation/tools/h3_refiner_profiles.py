"""Shared native-resolution profiles for the local IC refiner and its HTTP queue."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
RefinerSize = Literal["2560x1440", "1440x2560", "3840x2160"]


@dataclass(frozen=True)
class RefinerProfile:
    size: str
    resolution: str
    label: str
    low_width: int
    low_height: int
    native_width: int
    native_height: int
    max_windows_per_load: int
    max_jobs_per_cohort: int

    @property
    def width(self):
        return int(self.size.split("x")[0])

    @property
    def height(self):
        return int(self.size.split("x")[1])

    def window_path(self, folder, index):
        return Path(folder) / f"window-{index:02d}-{self.label.lower()}.mkv"


PROFILES = {
    "2560x1440": RefinerProfile("2560x1440", "2k", "2K", 1344, 768, 2560, 1440, 2, 2),
    "1440x2560": RefinerProfile("1440x2560", "2k-portrait", "2K", 768, 1344, 1440, 2560, 2, 2),
    # The released VAE/patch geometry computes 2176 rows, then crops 8 rows per edge.
    "3840x2160": RefinerProfile("3840x2160", "4k", "4K", 1344, 768, 3840, 2176, 1, 1),
}


def get_profile(size):
    try:
        return PROFILES[size]
    except KeyError as error:
        raise ValueError(f"Unsupported refiner size {size}; choose one of {list(PROFILES)}") from error


def ic_command(jobs_file, *, size, seed, sampler, full_frames=None):
    get_profile(size)
    command = [ROOT / ".venv-h3-2k/bin/python", ROOT / "tools/h3_ic_runtime.py", "--jobs", Path(jobs_file),
               "--size", size, "--seed", str(seed), "--sampler", sampler]
    if full_frames is not None:
        if size != "3840x2160":
            raise ValueError("Full-sequence profile currently requires 3840x2160")
        command += ["--full-sequence", "--frames", str(full_frames)]
    return command
