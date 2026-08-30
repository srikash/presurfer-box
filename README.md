# presurfer-box [![DOI](https://zenodo.org/badge/1350566808.svg)](https://doi.org/10.5281/zenodo.22163094)

MATLAB-free MP2RAGE preprocessing using SPM Standalone in Docker,
Singularity, or Apptainer.

`presurfer-box` provides presurfer workflows without requiring a local MATLAB
installation or MATLAB license. It uses the [official SPM Standalone container](https://github.com/spm/spm-docker)
and retains the original MATLAB implementation as a Git submodule.

> **Status:** This implementation uses SPM25 Standalone. Results have not yet
> been numerically validated against the historical SPM12/MATLAB pipeline.

## Install

For the containerized Python workflows, clone the repository:

```bash
git clone https://github.com/srikash/presurfer-box.git
cd presurfer-box
```

The legacy MATLAB source is optional. Fetch its pinned submodule only if you
need to inspect or run the historical implementation:

```bash
git submodule update --init --recursive
```

### Docker

```bash
docker pull ghcr.io/spm/spm-docker:docker-matlab-25.01.02
python3 -m pip install .
presurfer-box --check
```

### Singularity / Apptainer

```bash
singularity pull --name spm.sif \
  oras://ghcr.io/spm/spm-docker:singularity-matlab-25.01.02

python3 -m pip install .
presurfer-box --sif spm.sif --check
```

## Quick start

```bash
# Create a bias-corrected image and bias field
presurfer-box biascorrect IMAGE.nii

# Create MPRAGEised UNI
presurfer-box MPRAGEise INV2.nii UNI.nii

# Create an INV2-derived strip mask
presurfer-box stripmask INV2.nii

# Create UNI tissue classes, brain mask, and white-matter mask
presurfer-box brainmask UNI.nii
```

Use a local Singularity or Apptainer image with `--sif`:

```bash
presurfer-box --sif spm.sif stripmask INV2.nii
```

Docker is the default runtime. Override its image with `--image IMAGE`.

Existing workflow output directories are protected by default. To replace one,
pass `--clobber` before the command:

```bash
presurfer-box --clobber stripmask INV2.nii
```

This removes and recreates that workflow's `presurf_*` output directory.

## Choose a workflow

| Need | CLI command | Python function | Primary output |
| --- | --- | --- | --- |
| Bias-correct an image | `biascorrect IMAGE` | `spm_biascorrect()` | Bias-corrected image and bias field |
| Create MPRAGEised UNI | `MPRAGEise INV2 UNI` | `spm_mprageise()` | `*_MPRAGEised.nii` |
| Create a strip mask | `stripmask INV2` | `spm_stripmask()` | `*_stripmask.nii` |
| Create UNI-derived masks | `brainmask UNI` | `spm_seg()` | Tissue classes, brain mask, and WM mask |

`MPRAGEise` bias-corrects INV2, min-max normalizes the corrected INV2,
then multiplies it voxelwise with UNI. It does not run the strip-mask workflow.

## Python API

```python
from presurfer import spm_biascorrect, spm_mprageise, spm_seg, spm_stripmask

spm_biascorrect("INV2.nii")
spm_mprageise("INV2.nii", "UNI.nii")
spm_stripmask("INV2.nii")
spm_seg("UNI.nii")
```

All functions accept `image=` and `runtime=` keywords. Use
`runtime="singularity"` with a local SIF path passed as `image=`.

## Outputs

Each workflow creates an output directory beside its input:

```text
presurf_biascorrect/
presurf_MPRAGEise/
presurf_INV2/
presurf_UNI/
```

Compressed `.nii.gz` inputs are supported. The source file is preserved; the
workflow creates an uncompressed working copy in its output directory.

## Legacy MATLAB implementation

The original MATLAB implementation lives in
[srikash/presurfer](https://github.com/srikash/presurfer) and remains available
here as a pinned Git submodule:

```text
src/matlab/presurfer
```

For MATLAB use:

```matlab
addpath('src/matlab/presurfer/func')
```

Update the submodule only when intentionally adopting a newer original
presurfer commit (unlikely to happen).

## Reproducibility and validation

- Default image: `ghcr.io/spm/spm-docker:docker-matlab-25.01.02`
- SPM runtime: SPM25 Standalone
- Historical implementation: SPM12 with MATLAB
- Numerical equivalence has not yet been validated with reference NIfTI data.

## Citation

See [CITATION.cff](CITATION.cff).
