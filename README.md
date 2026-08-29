# presurfer-box [![DOI](https://zenodo.org/badge/1350566808.svg)](https://doi.org/10.5281/zenodo.22163094)

## MATLAB-free execution

The original MATLAB functions remain available, but new runs can use SPM
Standalone in Docker and do **not** need a MATLAB licence or local MATLAB/SPM
installation. The wrapper uses the [official SPM Docker image](https://github.com/spm/spm-docker),
pinned to SPM 25.01.02:

```bash
docker pull ghcr.io/spm/spm-docker:docker-matlab-25.01.02
python3 -m pip install .
presurfer-box presurf_MPRAGEise INV2.nii UNI.nii
presurfer-box presurf_INV2 INV2.nii
presurfer-box presurf_UNI UNI.nii
```

### Singularity / Apptainer

For HPC systems, download the official corresponding SIF once, then pass it
with `--sif`:

```bash
singularity pull --name spm-docker_singularity-matlab-25.01.02.sif \
  oras://ghcr.io/spm/spm-docker:singularity-matlab-25.01.02
presurfer-box --sif spm-docker_singularity-matlab-25.01.02.sif presurf_INV2 INV2.nii
```

`apptainer pull` and `apptainer exec` are also supported. Docker is the default;
use `--image IMAGE` only to override its Docker image tag. `--image` and
`--sif` are mutually exclusive.

The Docker commands deliberately use the same names as the original MATLAB
functions: `presurf_biascorrect`, `presurf_INV2`, `presurf_UNI`, and
`presurf_MPRAGEise`. Inputs may be `.nii` or `.nii.gz`. Unlike the legacy
MATLAB functions, the wrapper does not delete a compressed input while
preparing it.

Like the original example, `presurf_MPRAGEise INV2.nii UNI.nii` runs a
temporary INV2 **bias correction** before the MPRAGEise calculation;
`presurf_INV2 INV2.nii` then performs the distinct segmentation that produces
the strip mask. It is not a duplicate `presurf_INV2` invocation.

### Python library

```python
from presurfer import spm_biascorrect, spm_mprageise, spm_seg, spm_stripmask

spm_biascorrect("INV2.nii")
spm_mprageise("INV2.nii", "UNI.nii")
spm_stripmask("INV2.nii")
spm_seg("UNI.nii")
```

These are deliberately separate modules. Python names cannot contain hyphens,
so use underscores rather than `spm-biascorrect` etc. Each accepts an optional
`image="..."` and `runtime="docker"` or `runtime="singularity"` select the
container backend in the Python API. For Singularity, `image` is the local
`.sif` path.

The wrapper generates the original SPM Unified Segmentation and Image
Calculator batches and runs them with Docker or Singularity, mounting the
input/output directory at `/data`. It reports a missing runtime, image, or
failed SPM job as an error.

This is a migration from SPM12 to SPM25: results have **not** been numerically
validated against the old MATLAB/SPM12 pipeline because this repository has no
reference NIfTI test data and no exact historical SPM12 revision. Do not claim
identical numerical outputs until those inputs and baseline outputs are tested.
The MPRAGEise multiplication is reimplemented with NumPy/NiBabel; it preserves
the original `mat2gray(INV2) .* UNI` calculation, but it also needs validation
on representative data.

## Example

### Legacy MATLAB functions

The original MATLAB implementation is retained under `src/matlab/presurfer`.
Before using the examples below with MATLAB, add its function directory to the
MATLAB path:

```matlab
addpath('src/matlab/presurfer/func')
```

### Step-0 : MPRAGEise UNI
Run `presurf_MPRAGEise` <br>

<img src="https://github.com/srikash/TheBeesKnees/blob/main/imgs/presurfer_step0.gif" width="400">

[MPRAGEising is better than background removal ('denoising')](https://github.com/srikash/3dMPRAGEise)
<br>

Optional: \
Strip dielectric pads if used now (see [PadsOff](https://github.com/srikash/faceoff/blob/master/PadsOff), needs [ANTs](https://github.com/srikash/TheBeesKnees/wiki/Installing-Advanced-Normalization-Tools-(ANTs)))

<img src="https://github.com/srikash/TheBeesKnees/blob/main/imgs/presurfer_step0b.gif" width="400">

### Step-1 : Get a stripMask from INV2
Run `presurf_INV2` <br>

<img src="https://github.com/srikash/TheBeesKnees/blob/main/imgs/presurf_INV2_output.png" width="400">

### Step-2 : Get a brainMask from UNI
Run `presurf_UNI` <br>

<img src="https://github.com/srikash/TheBeesKnees/blob/main/imgs/presurf_UNI_output.png" width="400">

### Step-3 : Freesurfer
Use the INV2 stripMask to clean up the non-brain parts of the MPRAGEised UNI image.

e.g. `fslmaths MPRAGEised.nii -mul stripMask.nii MPRAGEised_stripped.nii`

Run `recon-all` using the MPRAGEised_stripped image <br>

Here is an example of a fully automated segmentation using presurfer + Freesurfer and laminar surfaces: 

<img src="https://github.com/srikash/TheBeesKnees/blob/main/imgs/freesurfer_seg.png" width="1200">

<br>

<img src="https://github.com/srikash/TheBeesKnees/blob/main/imgs/drake_presurfer.jpg" width="400">

### Misc. note
Run `presurf_biascorrect` to do just do SPM bias-correction.
<br>

Every step produces a sub-directory in the working directory containing all relevant segmentations and masks.
<br>

e.g. running `presurf_INV2` creates a presurf_INV2 sub-directory
