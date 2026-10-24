# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [2.4.11] - 2026-10-24

### Fixed

- The INV2/UNI affine check now allows an absolute difference of 1e-4 (it used
  `np.allclose`'s default 1e-8). Images from dcm2niix carry ~1e-6 where an
  axis-aligned grid has an exact 0. MPRAGEise passed the check on such inputs,
  then failed after segmentation, when `combine_mprageise` compared the
  bias-corrected INV2 with UNI: "INV2 and UNI images must have matching spatial
  affines."

## [2.4.10] - 2026-10-13

### Changed

- With Apptainer, `--image` accepts a bare registry name such as
  `ghcr.io/org/image:tag` and adds the `docker://` prefix.
- Running an Apptainer registry image prints a note that Apptainer converts it
  on every run, and suggests `presurfer pull` with `--sif`.
- `presurfer --sif FILE pull` now says that `pull` cannot use `--sif`.

### Fixed

- Docker runs now work for any user id. The SPM image has a home directory only
  for uid 1000, so other users got `HOME=/` and MATLAB failed with
  `fl:filesystem:AccessDenied`. The container now sets `HOME=/tmp` (#1).
- Apptainer runs and `--check` now start SPM through its `spm` command.
  `apptainer exec` skips the image's entry point, so `batch` and `--version`
  were run as program names. Thanks to Will Foran for the report and fix
  (#3).

## [2.4.9] - 2026-10-13

### Added

- `presurfer pull` saves the SPM image as a local SIF file for reuse with
  `--sif`.

### Changed

- `--engine apptainer` no longer needs `--sif`. It accepts `--image` with a
  registry URI (`docker://`, `oras://`) that Apptainer pulls itself, and uses
  the default SPM image from `ghcr.io` when neither is given.

## [2.4.8] - 2026-10-10

### Fixed

- SPM now runs with multiple MATLAB threads. The MATLAB Runtime in the SPM
  container defaulted to one thread, so SPM used one core. The default is the
  number of available cores, between 8 and 16.

### Added

- `recon-prep` command and `presurf_recon_prep()` function. They prepare INV2
  and UNI for FreeSurfer in one run: the strip-mask segmentation of INV2 also
  supplies the bias-corrected INV2 for MPRAGEise, and the brain-mask
  segmentation then runs on the MPRAGEised UNI. This needs two SPM segmentations
  instead of three, and writes everything into one run directory. The
  bias correction comes from the 2 mm strip-mask segmentation rather than the
  3 mm one that `MPRAGEise` uses, so the MPRAGEised image is not identical to
  the `MPRAGEise` result. In one test subject, about 40% of voxels differed
  (mean difference 0.3% of the intensity range, largest 18%).
- `spm.log` now records the container, image, and MATLAB thread count for every
  SPM step, and keeps the output of all steps instead of only the last one.
- The command is now `presurfer`. `presurfer-box` still works as an alias.
- `--engine docker|apptainer` option for choosing the container engine, for
  example on HPC systems.
- `--threads` option and `threads=` keyword to set the number of MATLAB threads.

### Changed

- Bias correction keeps the original 3 mm sampling, so `biascorrect` and the
  first step of `MPRAGEise` give the same numbers as the earlier code.
- Internally, every SPM step now runs through one runner module
  (`presurfer.spm_runner`), and the MPRAGEise calculation lives in its own module
  (`presurfer.mprageise_maths`). Output files and numbers are unchanged: a
  single-thread bias correction and the MPRAGEised image were byte-identical
  before and after.
- **Breaking:** the Python functions were renamed to match the presurfer
  branding: `spm_biascorrect`, `spm_mprageise`, `spm_stripmask`, and `spm_seg`
  are now `presurf_biascorrect`, `presurf_mprageise`, `presurf_stripmask`, and
  `presurf_seg`.
- **Breaking:** the Singularity runtime was removed. Use Apptainer
  (`--engine apptainer`, or `runtime="apptainer"` in Python). The
  `SINGULARITY_IMAGE` constant is now `SIF_IMAGE`.
- **Breaking:** the internal modules were reorganised. `presurfer.spm_workflows`
  and `presurfer.public_api` no longer exist. Import the four workflow functions
  from `presurfer`.

## [2.0.0] - 2026-10-10

The first PyPI release and a substantial rewrite of the earlier `prathama`
release (package version 0.1.0). Every SPM step now runs in a container, so the
whole pipeline works without MATLAB.

### Changed

- **Breaking:** the workflow commands were renamed. Scripts that use the old
  names need updating.

  | Before (`prathama`) | Now |
  | --- | --- |
  | `presurf_biascorrect` | `biascorrect` |
  | `presurf_MPRAGEise` | `MPRAGEise` |
  | `presurf_INV2` | `stripmask` |
  | `presurf_UNI` | `brainmask` |

- Each run writes into a new timestamped directory, so repeated runs never
  overwrite earlier results.
- Python 3.11 or later is required (the earlier release accepted 3.10).
- The package no longer installs a top-level `scripts` module. Use
  `presurfer.command_line:main` instead of `scripts.presurfer_box:main`.
- The Python functions return the `Path` of the output directory (or, for
  `spm_mprageise`, of the MPRAGEised image), now inside the timestamped run
  directory. `image=` and `runtime=` are keyword-only.
- Problems such as a missing container, a missing image, or a failed SPM job
  raise `RuntimeError` with a message that says how to fix it.

### Added

- First PyPI release, published through trusted publishing: `pip install presurfer`.
- Click command-line interface with `-h`/`--help` on every command and a
  `--check` option that verifies the selected container and reports the SPM
  version.
- `spm_biascorrect`, `spm_mprageise`, `spm_stripmask`, and `spm_seg` Python
  functions, importable from `presurfer`.
- Docker and Apptainer runtimes for SPM25 Standalone.
- MIT licence, citation metadata, type information (`py.typed`), automated
  tests, and continuous integration.

### Notes

- Results have not yet been numerically validated against the historical
  SPM12/MATLAB pipeline.
