# presurfer-box [![Version](https://img.shields.io/badge/version-2.4.11-purple.svg)](https://github.com/srikash/presurfer-box/releases/tag/v2.4.11) [![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE) [![CI](https://github.com/srikash/presurfer-box/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/srikash/presurfer-box/actions/workflows/ci.yml) [![DOI](https://zenodo.org/badge/1350566808.svg)](https://doi.org/10.5281/zenodo.22163094)

MATLAB-free MP2RAGE preprocessing for [presurfer](https://github.com/srikash/presurfer),
using SPM Standalone in a Docker or Apptainer container.

`presurfer-box` makes the presurfer steps (bias correction, MPRAGEising, strip
masks, and brain masks) available as a Python package and command-line tool. You
do not need MATLAB, a MATLAB licence, or a local SPM installation. SPM runs
inside the
[official SPM Standalone container](https://github.com/spm/spm-docker), and
Python prepares the files and runs the container for you.

> **Status:** This version uses SPM25 Standalone. Results have not yet been
> numerically validated against the historical SPM12/MATLAB pipeline.

## Table of contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Choosing a workflow](#choosing-a-workflow)
- [Python API](#python-api)
- [Outputs](#outputs)
- [Example](#example)
- [Legacy MATLAB implementation](#legacy-matlab-implementation)
- [Reproducibility and validation](#reproducibility-and-validation)
- [Licence](#licence)
- [Changelog](#changelog)
- [Citation](#citation)

## Installation

The command is `presurfer`. The older name `presurfer-box` also works.

`presurfer-box` requires Python 3.11+ and one container runtime: Docker,
or Apptainer. It is a standard `pyproject.toml` package, so install
it with whichever of these you already use.

### venv

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install presurfer
presurfer --help
```

### conda / mamba

`presurfer` comes from PyPI, not conda-forge, so `pip install` does the actual
install inside a conda or mamba environment:

```bash
conda create -n presurfer python=3.11
conda activate presurfer
pip install presurfer
presurfer --help
```

(`mamba` is a drop-in replacement for `conda` in both commands above.)

### From a source checkout

```bash
git clone https://github.com/srikash/presurfer-box.git
cd presurfer-box
pip install .            # or: pip install -e . for an editable install
```

The legacy MATLAB source is optional. Fetch its pinned submodule only if you
need to inspect or run the historical implementation:

```bash
git submodule update --init --recursive
```

### uv

Included because this project's development and CI use
[uv](https://docs.astral.sh/uv/). It is not required for everyday use.

```bash
# from PyPI, into an isolated tool environment
uv tool install --python 3.11 presurfer
presurfer --help

# from a source checkout
cd presurfer-box
uv sync
uv run presurfer --help
```

### The SPM container

The Python package does not include SPM. Download the official container once,
then check that `presurfer` can use it.

**Docker**

```bash
docker pull ghcr.io/spm/spm-docker:docker-matlab-25.01.02
presurfer --check
```

**Apptainer** (for example on an HPC cluster)

```bash
apptainer pull --name spm.sif \
  oras://ghcr.io/spm/spm-docker:singularity-matlab-25.01.02

presurfer --engine apptainer --sif spm.sif --check
```

Apptainer can pull from the registry itself, so you don't need a `.sif` file:

```bash
presurfer --engine apptainer --image docker://ghcr.io/spm/spm-docker:docker-matlab-25.01.02 --check
```

This way Apptainer converts the image on every run, though it caches the
downloaded layers in `~/.apptainer/cache` (or `$APPTAINER_CACHEDIR`). On a
cluster it is faster to pull a `.sif` once. `presurfer pull` does that:

```bash
presurfer pull --output /data/containers/spm.sif   # default: ./spm.sif
presurfer --sif /data/containers/spm.sif --check
```

`pull` uses the default SPM image, or a registry URI given with `--image`
(`presurfer --image docker://... pull`). It refuses to overwrite an existing
file unless you add `--force`.

A successful check prints the runtime,
the image, and the SPM version.

## Quick start

```bash
# Create a bias-corrected image and bias field
presurfer biascorrect IMAGE.nii

# Create MPRAGEised UNI
presurfer MPRAGEise INV2.nii UNI.nii

# Create an INV2-derived strip mask
presurfer stripmask INV2.nii

# Create UNI tissue classes, brain mask, and white-matter mask
presurfer brainmask UNI.nii

# Do all of the above for a FreeSurfer run in one go
presurfer recon-prep INV2.nii UNI.nii
```

Inputs can be `.nii` or `.nii.gz`. Docker is the default runtime. To use
Apptainer, pass `--engine apptainer` before the command. Apptainer pulls the
default SPM image from `ghcr.io` on its own:

```bash
presurfer --engine apptainer stripmask INV2.nii
```

To reuse a local Apptainer image, pass `--sif IMAGE` (see `presurfer pull` above):

```bash
presurfer --sif spm.sif stripmask INV2.nii
```

To use a different image, pass `--image IMAGE` (a Docker tag, or with Apptainer
a registry name such as `ghcr.io/org/image:tag`, with or without `docker://`).
`--image` and `--sif` cannot be combined.

### Container engine

`--engine` chooses between `docker` (the default) and `apptainer`. With
Apptainer, give either a local SIF file (`--sif`) or a registry URI such as
`docker://ghcr.io/...` (`--image`). `--engine apptainer` alone uses the default
SPM image from `ghcr.io`. Passing `--sif` alone selects Apptainer automatically.

```bash
presurfer --engine apptainer --sif spm.sif brainmask UNI.nii
```

### Threads

The MATLAB Runtime inside the SPM container starts with a single thread, so SPM
would otherwise use one core however many the machine has. `presurfer` sets
the thread count for every SPM step. By default it uses the number of available
cores, but never fewer than 8 and never more than 16, because extra threads stop
helping beyond a certain point. Choose a number yourself with `--threads`:

```bash
presurfer --threads 12 brainmask UNI.nii
```

In Python, pass `threads=12` to any workflow function.

The thread count can change results in the last digits, although a fixed count
always gives identical results. `spm.log` records the container, image, and
thread count of every step, so you can reproduce a run by passing the same
`--threads` value.

## Choosing a workflow

| Need | CLI command | Python function | Main output |
| --- | --- | --- | --- |
| Bias-correct an image | `biascorrect IMAGE` | `presurf_biascorrect()` | Bias-corrected image and bias field |
| Create MPRAGEised UNI | `MPRAGEise INV2 UNI` | `presurf_mprageise()` | `*_MPRAGEised.nii` |
| Create a strip mask | `stripmask INV2` | `presurf_stripmask()` | `*_stripmask.nii` |
| Create UNI-derived masks | `brainmask UNI` | `presurf_seg()` | Tissue classes, brain mask, and white-matter mask |
| Prepare INV2 and UNI for FreeSurfer | `recon-prep INV2 UNI` | `presurf_recon_prep()` | MPRAGEised UNI, strip mask, brain mask, and white-matter mask |

`MPRAGEise` bias-corrects INV2 in a temporary directory, rescales the corrected
INV2 to the range 0 to 1, and multiplies it voxel by voxel with UNI. It does not
run the strip-mask workflow, so run `stripmask` separately if you need the mask.

`recon-prep` runs the whole preparation with two SPM segmentations instead of
three. It segments INV2 (which gives the strip mask and a bias-corrected INV2),
reuses that bias-corrected INV2 to MPRAGEise UNI, and then segments the
MPRAGEised UNI to get the brain and white-matter masks. It checks that INV2 and
UNI share the same voxel grid before it starts SPM.

Because `recon-prep` takes the bias correction from the strip-mask segmentation
(2 mm sampling) instead of the separate 3 mm bias correction that `MPRAGEise`
runs, its MPRAGEised image is not the same as the one `MPRAGEise` makes. In one
test subject, about 40% of voxels differed, the mean difference was 0.3% of the
intensity range, and the largest was 18%. Over the brighter half of the voxels
the two images correlated at 0.988.

This is a deliberate trade. `recon-prep` saves one segmentation, about 13 to 15
minutes per subject on a 12-thread machine, in exchange for a slightly different
MPRAGEised image. Whether that difference matters for your FreeSurfer surfaces is
worth checking on your own data. Use `MPRAGEise` followed by `brainmask` when you
need the result of the original MATLAB pipeline.

## Python API

```python
from presurfer import (
    presurf_biascorrect,
    presurf_mprageise,
    presurf_recon_prep,
    presurf_seg,
    presurf_stripmask,
)

presurf_biascorrect("INV2.nii")
presurf_mprageise("INV2.nii", "UNI.nii")
presurf_stripmask("INV2.nii")
presurf_seg("UNI.nii")
presurf_recon_prep("INV2.nii", "UNI.nii")
```

Every function accepts the optional keywords `image=`, `runtime=`, and
`threads=`. For Apptainer, `runtime="apptainer"` alone uses the default SPM
image from `ghcr.io`. Pass a local SIF path or a registry URI as `image=` to
override it:

```python
presurf_stripmask("INV2.nii", runtime="apptainer")
presurf_stripmask("INV2.nii", image="spm.sif", runtime="apptainer")
```

`presurf_biascorrect`, `presurf_stripmask`, and `presurf_seg` return the path
of the `presurf_*` output directory. `presurf_mprageise` returns the path of the
`*_MPRAGEised.nii` image. `presurf_recon_prep` returns the run directory that
holds `presurf_INV2`, `presurf_MPRAGEise`, and `presurf_UNI`. All of them raise
`RuntimeError` if the container is unavailable or SPM fails.

## Outputs

Each run creates a new UTC timestamped directory beside its input, containing one
`presurf_*` directory for the workflow. The `biascorrect`, `stripmask`, and
`brainmask` workflows also save the SPM output as `spm.log`, with a short header
for each step that gives the container, the image, and the MATLAB thread count:

```text
YYMMDDThh:mm:ss_presurfer/
├── spm.log
└── presurf_INV2/      # or presurf_UNI, presurf_biascorrect, presurf_MPRAGEise
```

For example, `250101T12:34:56_presurfer/presurf_INV2/`. If two runs start in the
same second, the second directory gets a numeric suffix (`-2`). `MPRAGEise` uses a
temporary `tmp_` directory for its bias-correction step and removes it
afterwards.

`recon-prep` writes all three workflows into one run directory:

```text
YYMMDDThh:mm:ss_presurfer/
├── spm.log
├── presurf_INV2/        # strip mask and bias-corrected INV2
├── presurf_MPRAGEise/   # MPRAGEised UNI
└── presurf_UNI/         # brain mask and white-matter mask, from the MPRAGEised UNI
```

Compressed `.nii.gz` inputs are supported. The source file is never changed, and
the workflow writes an uncompressed working copy into its output directory.

## Example

### Prepare an MP2RAGE for FreeSurfer

One command prepares INV2 and UNI for FreeSurfer:

```bash
presurfer recon-prep INV2.nii UNI.nii
```

It runs the INV2 segmentation first, reuses its bias correction to MPRAGEise UNI,
and then segments the MPRAGEised UNI. Everything goes into one run directory:

```text
YYMMDDThh:mm:ss_presurfer/
├── presurf_INV2/        # INV2_stripmask.nii
├── presurf_MPRAGEise/   # UNI_MPRAGEised.nii
└── presurf_UNI/         # UNI_MPRAGEised_brainmask.nii, UNI_MPRAGEised_WMmask.nii
```

The strip mask, from INV2:

<img src="https://raw.githubusercontent.com/srikash/TheBeesKnees/main/imgs/presurf_INV2_output.png" width="400" alt="Strip mask from INV2">

The MPRAGEised UNI. [MPRAGEising is better than background removal ('denoising')](https://github.com/srikash/3dMPRAGEise).

<img src="https://raw.githubusercontent.com/srikash/TheBeesKnees/main/imgs/presurfer_step0.gif" width="400" alt="MPRAGEising the UNI image">

The brain mask, from the MPRAGEised UNI:

<img src="https://raw.githubusercontent.com/srikash/TheBeesKnees/main/imgs/presurf_UNI_output.png" width="400" alt="Brain mask from the MPRAGEised UNI">

Then use the strip mask to remove the non-brain parts of the MPRAGEised UNI, and
run `recon-all` on the stripped image:

```bash
RUN=YYMMDDThh:mm:ss_presurfer
fslmaths $RUN/presurf_MPRAGEise/UNI_MPRAGEised.nii \
  -mul $RUN/presurf_INV2/INV2_stripmask.nii MPRAGEised_stripped.nii
```

Here is a fully automated segmentation with presurfer and FreeSurfer, including
laminar surfaces:

<img src="https://raw.githubusercontent.com/srikash/TheBeesKnees/main/imgs/freesurfer_seg.png" width="1200" alt="FreeSurfer segmentation and laminar surfaces">

<img src="https://raw.githubusercontent.com/srikash/TheBeesKnees/main/imgs/drake_presurfer.jpg" width="400" alt="Drake approves of presurfer">

### Step by step

Run the steps separately when you only want some of the outputs, or need to work
on an image in between.

```bash
presurfer stripmask INV2.nii            # strip mask from INV2
presurfer MPRAGEise INV2.nii UNI.nii    # MPRAGEised UNI
presurfer brainmask UNI_MPRAGEised.nii  # brain mask from the MPRAGEised UNI
```

The step-by-step route needs three SPM segmentations instead of two, because
`MPRAGEise` runs its own bias correction.

To run only the SPM bias correction, use `presurfer biascorrect`.

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
- Numerical equivalence with the historical pipeline has not yet been validated
  against reference NIfTI data.
- The MPRAGEise multiplication is reimplemented with NumPy and NiBabel. It
  follows the original `mat2gray(INV2) .* UNI` calculation but also needs
  validation on representative data.
- Bias correction (`biascorrect` and the first step of `MPRAGEise`) samples at
  3 mm, as the original MATLAB code does. The strip-mask and brain-mask
  segmentations sample at 2 mm.
- Tidying the code did not change any numbers. On one test subject, a
  single-thread bias correction from this version was byte-identical to the one
  from the earlier code, and the MPRAGEise calculation was byte-identical before
  and after it moved into its own module.
- A fixed `--threads` value gives identical results every time. Different values
  can change results slightly, and `recon-prep` differs from `MPRAGEise` as
  described above.

## Licence

MIT. See [LICENSE](LICENSE).

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for what changed in each version.

## Citation

See [CITATION.cff](CITATION.cff).
