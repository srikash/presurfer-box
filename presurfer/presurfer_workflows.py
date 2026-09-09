"""Public presurfer workflows composed from SPM processing steps."""

from pathlib import Path

from presurfer.spm_workflows import (
    IMAGE,
    SINGULARITY_IMAGE,
    Runtime,
    main,
    mprageise,
    run_segmentation,
)


def spm_biascorrect(
    input_file: str | Path,
    *,
    image: str = IMAGE,
    runtime: Runtime = "docker",
) -> Path:
    """Run SPM bias correction for a NIfTI input."""
    return run_segmentation(Path(input_file), "biascorrect", image, runtime)


def spm_mprageise(
    inv2_file: str | Path,
    uni_file: str | Path,
    *,
    image: str = IMAGE,
    runtime: Runtime = "docker",
) -> Path:
    """Create a MPRAGEised UNI image from INV2 and UNI inputs."""
    return mprageise(Path(inv2_file), Path(uni_file), image, runtime)


def spm_stripmask(
    input_file: str | Path,
    *,
    image: str = IMAGE,
    runtime: Runtime = "docker",
) -> Path:
    """Create an INV2-derived strip mask."""
    return run_segmentation(Path(input_file), "INV2", image, runtime)


def spm_seg(
    input_file: str | Path,
    *,
    image: str = IMAGE,
    runtime: Runtime = "docker",
) -> Path:
    """Create UNI tissue-class, brain-mask, and white-matter-mask outputs."""
    return run_segmentation(Path(input_file), "UNI", image, runtime)


__all__ = [
    "IMAGE",
    "SINGULARITY_IMAGE",
    "main",
    "spm_biascorrect",
    "spm_mprageise",
    "spm_seg",
    "spm_stripmask",
]
