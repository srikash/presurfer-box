#!/usr/bin/env python3
"""Run presurfer's SPM jobs in official SPM Standalone containers.

The SPM work is performed in the container.  File management and the small
MPRAGEise calculation live here so a local MATLAB installation is not needed.
"""

from __future__ import annotations

import argparse
import gzip
import os
import shutil
import subprocess
import sys
from pathlib import Path


IMAGE = "ghcr.io/spm/spm-docker:docker-matlab-25.01.02"
SINGULARITY_IMAGE = "spm-docker_singularity-matlab-25.01.02.sif"


def fail(message: str) -> "None":
    raise RuntimeError(message)


def nii_stem(path: Path) -> str:
    name = path.name
    if name.endswith(".nii.gz"):
        return name[:-7]
    if name.endswith(".nii"):
        return name[:-4]
    fail(f"Expected a .nii or .nii.gz file, got: {path}")


def materialize_input(source: Path, output_dir: Path) -> Path:
    """Copy an input to output_dir, decompressing without modifying the source."""
    if not source.is_file():
        fail(f"Input file does not exist: {source}")
    target = output_dir / f"{nii_stem(source)}.nii"
    if source.name.endswith(".nii.gz"):
        with gzip.open(source, "rb") as compressed, target.open("wb") as plain:
            shutil.copyfileobj(compressed, plain)
    else:
        shutil.copy2(source, target)
    return target


def container_path(host_path: Path, mount_root: Path) -> str:
    try:
        return "/data/" + str(host_path.resolve().relative_to(mount_root.resolve()))
    except ValueError as error:
        fail(f"Path is outside the mounted directory {mount_root}: {host_path}")
        raise error  # placate type checkers


def container_command(mount_root: Path, job_file: Path, image: str, runtime: str) -> list[str]:
    """Construct the container runtime command for a generated SPM batch."""
    job = container_path(job_file, mount_root)
    if runtime == "docker":
        return ["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}",
                "-v", f"{mount_root.resolve()}:/data", image, "batch", job]
    if runtime == "singularity":
        executable = shutil.which("singularity") or shutil.which("apptainer")
        if executable is None:
            fail("Neither Singularity nor Apptainer was found on PATH.")
        if not Path(image).is_file():
            fail(
                f"Singularity image does not exist: {image}\n"
                "Pull it first: singularity pull --name "
                f"{SINGULARITY_IMAGE} oras://ghcr.io/spm/spm-docker:singularity-matlab-25.01.02"
            )
        return [executable, "exec", "--bind", f"{mount_root.resolve()}:/data", image, "batch", job]
    fail(f"Unsupported runtime: {runtime}. Use 'docker' or 'singularity'.")


def run_spm_batch(mount_root: Path, job_file: Path, image: str, runtime: str) -> None:
    """Run a generated SPM batch and preserve container error output."""
    if runtime == "docker":
        if shutil.which("docker") is None:
            fail("Docker was not found on PATH. Install Docker, then pull the SPM image.")
        inspect = subprocess.run(
            ["docker", "image", "inspect", image],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if inspect.returncode:
            fail(f"SPM image is not available locally: {image}\nPull it first: docker pull {image}")
    command = container_command(mount_root, job_file, image, runtime)
    result = subprocess.run(command, text=True)
    if result.returncode:
        fail(f"SPM batch failed (Docker exit status {result.returncode}).")


def segmentation_job(input_file: str, output_dir: str, native: list[int], samp: int) -> str:
    tissues = "\n".join(
        "matlabbatch{1}.spm.spatial.preproc.tissue(%d).tpm = {fullfile(spm('Dir'),'tpm','TPM.nii,%d')};\n"
        "matlabbatch{1}.spm.spatial.preproc.tissue(%d).ngaus = %d;\n"
        "matlabbatch{1}.spm.spatial.preproc.tissue(%d).native = [%d %d];\n"
        "matlabbatch{1}.spm.spatial.preproc.tissue(%d).warped = [0 0];"
        % (index, index, index, ngaus, index, native[index - 1], 0, index)
        for index, ngaus in enumerate((2, 2, 2, 3, 4, 2), 1)
    )
    return f"""spm('defaults','FMRI');
spm_jobman('initcfg');
matlabbatch{{1}}.spm.spatial.preproc.channel.vols = {{'{input_file},1'}};
matlabbatch{{1}}.spm.spatial.preproc.channel.biasreg = 0.001;
matlabbatch{{1}}.spm.spatial.preproc.channel.biasfwhm = 30;
matlabbatch{{1}}.spm.spatial.preproc.channel.write = [1 1];
{tissues}
matlabbatch{{1}}.spm.spatial.preproc.warp.mrf = 1;
matlabbatch{{1}}.spm.spatial.preproc.warp.cleanup = 1;
matlabbatch{{1}}.spm.spatial.preproc.warp.reg = [0 0.001 0.5 0.05 0.2];
matlabbatch{{1}}.spm.spatial.preproc.warp.affreg = 'mni';
matlabbatch{{1}}.spm.spatial.preproc.warp.fwhm = 0;
matlabbatch{{1}}.spm.spatial.preproc.warp.samp = {samp};
matlabbatch{{1}}.spm.spatial.preproc.warp.write = [0 0];
matlabbatch{{1}}.spm.spatial.preproc.warp.vox = NaN;
matlabbatch{{1}}.spm.spatial.preproc.warp.bb = [NaN NaN NaN; NaN NaN NaN];
spm_jobman('run',matlabbatch);
save(fullfile('{output_dir}','{Path(input_file).stem}_presurfSegBatch.mat'),'matlabbatch');
"""


def imcalc_job(inputs: list[str], output: str, expression: str, batch_file: str) -> str:
    quoted_inputs = "\n".join(f"    '{item},1'" for item in inputs)
    return f"""spm('defaults','FMRI');
spm_jobman('initcfg');
matlabbatch{{1}}.spm.util.imcalc.input = {{
{quoted_inputs}
    }};
matlabbatch{{1}}.spm.util.imcalc.output = '{Path(output).name}';
matlabbatch{{1}}.spm.util.imcalc.outdir = {{'{Path(output).parent}'}};
matlabbatch{{1}}.spm.util.imcalc.expression = '{expression}';
matlabbatch{{1}}.spm.util.imcalc.var = struct('name', {{}}, 'value', {{}});
matlabbatch{{1}}.spm.util.imcalc.options.dmtx = 0;
matlabbatch{{1}}.spm.util.imcalc.options.mask = 0;
matlabbatch{{1}}.spm.util.imcalc.options.interp = -7;
matlabbatch{{1}}.spm.util.imcalc.options.dtype = 2;
spm_jobman('run',matlabbatch);
save('{batch_file}','matlabbatch');
"""


def rename_segmentation(out: Path, stem: str, classes: tuple[int, ...]) -> None:
    for produced, suffix in ((f"m{stem}.nii", "_biascorrected.nii"),
                             (f"BiasField_{stem}.nii", "_biasfield.nii")):
        (out / produced).replace(out / f"{stem}{suffix}")
    for number in classes:
        (out / f"c{number}{stem}.nii").replace(out / f"{stem}_class{number}.nii")
    (out / f"{stem}_seg8.mat").unlink(missing_ok=True)


def run_segmentation(source: Path, kind: str, image: str, runtime: str) -> Path:
    source = source.resolve()
    if not source.is_file():
        fail(f"Input file does not exist: {source}")
    out = source.parent / f"presurf_{kind}"
    out.mkdir(exist_ok=False)
    copied = materialize_input(source, out)
    mount_root = source.parent
    input_in_container = container_path(copied, mount_root)
    out_in_container = container_path(out, mount_root)
    native, samp, classes = ({"biascorrect": ([0] * 6, 3, ()),
                              "UNI": ([1, 1, 1, 0, 0, 0], 2, (1, 2, 3)),
                              "INV2": ([0, 0, 1, 1, 1, 1], 2, (3, 4, 5, 6))}[kind])
    job = out / ".presurfer_segmentation.m"
    job.write_text(segmentation_job(input_in_container, out_in_container, native, samp))
    try:
        run_spm_batch(mount_root, job, image, runtime)
    finally:
        job.unlink(missing_ok=True)
    stem = nii_stem(copied)
    rename_segmentation(out, stem, classes)
    if kind == "UNI":
        masks = [([1, 2, 3], "_brainmask.nii", "(i1+i2+i3)>0.3"),
                 ([2], "_WMmask.nii", "(i1)>0.5")]
    elif kind == "INV2":
        masks = [([3, 4, 5, 6], "_stripmask.nii", "1-((i1+i2+i3+i4)>0.5)")]
    else:
        masks = []
    for numbers, suffix, expression in masks:
        job = out / ".presurfer_imcalc.m"
        inputs = [container_path(out / f"{stem}_class{number}.nii", mount_root) for number in numbers]
        output = container_path(out / f"{stem}{suffix}", mount_root)
        batch_name = "_presurfWMBatch.mat" if suffix == "_WMmask.nii" else "_presurfStripBatch.mat"
        batch_file = container_path(out / f"{stem}{batch_name}", mount_root)
        job.write_text(imcalc_job(inputs, output, expression, batch_file))
        try:
            run_spm_batch(mount_root, job, image, runtime)
        finally:
            job.unlink(missing_ok=True)
    return out


def mprageise(inv2: Path, uni: Path, image: str, runtime: str) -> Path:
    bias_dir = run_segmentation(inv2, "biascorrect", image, runtime)
    try:
        import nibabel as nib
        import numpy as np
    except ImportError:
        fail("MPRAGEise needs numpy and nibabel. Install with: pip install -r requirements.txt")
    uni = uni.resolve()
    output_dir = uni.parent / "presurf_MPRAGEise"
    output_dir.mkdir(exist_ok=False)
    uni_local = materialize_input(uni, output_dir)
    inv2_bias = bias_dir / f"{nii_stem(inv2)}_biascorrected.nii"
    uni_img = nib.load(str(uni_local))
    inv2_data = nib.load(str(inv2_bias)).get_fdata(dtype=np.float64)
    minimum, maximum = np.nanmin(inv2_data), np.nanmax(inv2_data)
    normalised = np.zeros_like(inv2_data) if maximum == minimum else (inv2_data - minimum) / (maximum - minimum)
    result = uni_img.get_fdata(dtype=np.float64) * normalised
    output = output_dir / f"{nii_stem(uni)}_MPRAGEised.nii"
    nib.save(nib.Nifti1Image(result, uni_img.affine, uni_img.header), str(output))
    shutil.rmtree(bias_dir)
    return output


# Public Python API. Hyphens are not valid in Python identifiers.
def spm_biascorrect(input_file: str | Path, *, image: str = IMAGE, runtime: str = "docker") -> Path:
    """Run SPM bias correction and return ``presurf_biascorrect``."""
    return run_segmentation(Path(input_file), "biascorrect", image, runtime)


def spm_mprageise(inv2_file: str | Path, uni_file: str | Path, *, image: str = IMAGE, runtime: str = "docker") -> Path:
    """Bias-correct INV2, min-max normalise it, and multiply it with UNI."""
    return mprageise(Path(inv2_file), Path(uni_file), image, runtime)


def spm_stripmask(input_file: str | Path, *, image: str = IMAGE, runtime: str = "docker") -> Path:
    """Run INV2 segmentation and produce the class-3-to-6 strip mask."""
    return run_segmentation(Path(input_file), "INV2", image, runtime)


def spm_seg(input_file: str | Path, *, image: str = IMAGE, runtime: str = "docker") -> Path:
    """Run UNI segmentation and produce class, brain-, and WM-mask outputs."""
    return run_segmentation(Path(input_file), "UNI", image, runtime)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    images = parser.add_mutually_exclusive_group()
    images.add_argument("--image", help="Docker image tag (Docker is the default runtime)")
    images.add_argument("--sif", type=Path, help="Singularity/Apptainer SIF file")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("presurf_biascorrect", "presurf_UNI", "presurf_INV2"):
        item = commands.add_parser(name)
        item.add_argument("input", type=Path)
    item = commands.add_parser("presurf_MPRAGEise")
    item.add_argument("inv2", type=Path)
    item.add_argument("uni", type=Path)
    args = parser.parse_args()
    runtime = "singularity" if args.sif else "docker"
    image = str(args.sif) if args.sif else (args.image or IMAGE)
    try:
        if args.command == "presurf_MPRAGEise":
            output = spm_mprageise(args.inv2, args.uni, image=image, runtime=runtime)
        else:
            operation = {
                "presurf_biascorrect": spm_biascorrect,
                "presurf_INV2": spm_stripmask,
                "presurf_UNI": spm_seg,
            }[args.command]
            output = operation(args.input, image=image, runtime=runtime)
        print(output)
        return 0
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f"presurfer-box: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
