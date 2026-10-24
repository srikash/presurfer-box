"""The MPRAGEise calculation: normalise bias-corrected INV2 and multiply by UNI."""

from pathlib import Path
from typing import cast

import nibabel as nib
import numpy as np

__all__ = ["check_matching_grids", "combine_mprageise", "mprageise_array"]


def mprageise_array(inv2: np.ndarray, uni: np.ndarray) -> np.ndarray:
    """Scale INV2 to the range 0 to 1 and multiply it with UNI, voxel by voxel.

    This is the whole calculation. It matches the original MATLAB
    ``presurf_MPRAGEise``, which computes ``mat2gray(INV2) .* UNI``, where
    ``mat2gray`` rescales the image linearly from its minimum to its maximum.

    Two edge cases follow the current code rather than a check against MATLAB:
    an INV2 image with a single constant value becomes all zeros, and voxels
    that are NaN in INV2 stay NaN in the result.

    Args:
        inv2: Bias-corrected INV2 voxel values.
        uni: UNI voxel values, with the same shape as ``inv2``.

    Returns:
        The MPRAGEised voxel values as 64-bit floats.
    """
    minimum, maximum = np.nanmin(inv2), np.nanmax(inv2)
    normalised = (
        np.zeros_like(inv2)
        if maximum == minimum
        else (inv2 - minimum) / (maximum - minimum)
    )
    result: np.ndarray = uni * normalised
    return result


AFFINE_ATOL = 1e-4
"""Absolute tolerance for comparing affines. Converters such as dcm2niix leave ~1e-6 in
place of an exact 0 on axis-aligned grids, which ``np.allclose``'s default ``atol``
(1e-8) rejects against a 0. 1e-4 is below 0.04 mm over a 320-voxel field of view."""


def _affines_match(first: np.ndarray, second: np.ndarray) -> bool:
    return bool(np.allclose(first, second, rtol=1e-5, atol=AFFINE_ATOL))


def check_matching_grids(inv2: Path, uni: Path) -> None:
    """Check that two images share a voxel grid, reading only their headers.

    Run this before starting any SPM step, so that a mismatched pair fails at
    once instead of after a long segmentation.

    Args:
        inv2: INV2 ``.nii`` or ``.nii.gz`` file.
        uni: UNI ``.nii`` or ``.nii.gz`` file.

    Raises:
        RuntimeError: If the image dimensions or spatial affines differ.
    """
    inv2_img = cast("nib.Nifti1Image", nib.load(str(inv2)))
    uni_img = cast("nib.Nifti1Image", nib.load(str(uni)))
    if inv2_img.shape != uni_img.shape:
        raise RuntimeError("INV2 and UNI images must have matching dimensions.")
    if not _affines_match(inv2_img.affine, uni_img.affine):
        raise RuntimeError("INV2 and UNI images must have matching spatial affines.")


def combine_mprageise(inv2_biascorrected: Path, uni: Path, output: Path) -> Path:
    """Write the MPRAGEised UNI image for a bias-corrected INV2 and a UNI.

    The output keeps the UNI header and affine.

    Args:
        inv2_biascorrected: Bias-corrected INV2 ``.nii`` or ``.nii.gz`` file.
        uni: UNI ``.nii`` or ``.nii.gz`` file.
        output: ``.nii`` file to create.

    Returns:
        The created ``output`` file.

    Raises:
        RuntimeError: If the images differ in dimensions or affine, or INV2
            has no finite voxels.
    """
    uni_img = cast("nib.Nifti1Image", nib.load(str(uni)))
    inv2_img = cast("nib.Nifti1Image", nib.load(str(inv2_biascorrected)))
    uni_data = uni_img.get_fdata(dtype=np.float64)
    inv2_data = inv2_img.get_fdata(dtype=np.float64)
    if uni_data.shape != inv2_data.shape:
        raise RuntimeError("INV2 and UNI images must have matching dimensions.")
    if not _affines_match(uni_img.affine, inv2_img.affine):
        raise RuntimeError("INV2 and UNI images must have matching spatial affines.")
    if not np.isfinite(inv2_data).any():
        raise RuntimeError("Bias-corrected INV2 contains no finite voxel values.")
    result = mprageise_array(inv2_data, uni_data)
    nib.save(nib.Nifti1Image(result, uni_img.affine, uni_img.header), str(output))
    return output
