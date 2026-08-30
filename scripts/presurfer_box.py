#!/usr/bin/env python3
"""Run presurfer preprocessing with SPM Standalone containers.

The public API provides separate bias-correction, MPRAGEise, strip-mask, and
UNI segmentation workflows. SPM work runs in Docker or Singularity/Apptainer;
host-side Python handles file preparation and the MPRAGEise multiplication.

Note:
    The default runtime uses SPM25 Standalone. Results have not yet been
    numerically validated against the historical SPM12/MATLAB workflow.
"""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
from pathlib import Path

import click

IMAGE = "ghcr.io/spm/spm-docker:docker-matlab-25.01.02"
SINGULARITY_IMAGE = "spm-docker_singularity-matlab-25.01.02.sif"


def fail(message: str) -> "None":
    """Raise a user-facing runtime error.

    Args:
        message: Error message describing the failed precondition or job.

    Raises:
        RuntimeError: Always raised with ``message``.
    """
    raise RuntimeError(message)


def nii_stem(path: Path) -> str:
    """Return a NIfTI basename without ``.nii`` or ``.nii.gz``.

    Args:
        path: NIfTI file path.

    Returns:
        Filename without its NIfTI extension.

    Raises:
        RuntimeError: If ``path`` does not have a supported NIfTI extension.
    """
    name = path.name
    if name.endswith(".nii.gz"):
        return name[:-7]
    if name.endswith(".nii"):
        return name[:-4]
    fail(f"Expected a .nii or .nii.gz file, got: {path}")


def materialize_input(source: Path, output_dir: Path) -> Path:
    """Copy a NIfTI input into an output directory.

    Compressed inputs are decompressed to ``.nii`` without modifying the
    original source file.

    Args:
        source: Existing ``.nii`` or ``.nii.gz`` input file.
        output_dir: Directory that receives the materialized ``.nii`` file.

    Returns:
        Path to the copied or decompressed ``.nii`` file.

    Raises:
        RuntimeError: If ``source`` does not exist or is not a NIfTI file.
    """
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
    """Map a path below a host mount directory to its container path.

    Args:
        host_path: Host path to expose inside the container.
        mount_root: Host directory mounted at ``/data``.

    Returns:
        Equivalent absolute path below ``/data`` inside the container.

    Raises:
        RuntimeError: If ``host_path`` is outside ``mount_root``.
    """
    try:
        return "/data/" + str(host_path.resolve().relative_to(mount_root.resolve()))
    except ValueError as error:
        fail(f"Path is outside the mounted directory {mount_root}: {host_path}")
        raise error  # placate type checkers


def container_command(mount_root: Path, job_file: Path, image: str, runtime: str) -> list[str]:
    """Build a Docker or Singularity/Apptainer SPM batch command.

    Args:
        mount_root: Host directory mounted at ``/data``.
        job_file: Generated SPM batch script below ``mount_root``.
        image: Docker image tag or local Singularity image path.
        runtime: ``"docker"`` or ``"singularity"``.

    Returns:
        Command arguments suitable for ``subprocess.run``.

    Raises:
        RuntimeError: If the runtime is unsupported, unavailable, or its SIF
            image does not exist.
    """
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


def check_container(image: str, runtime: str) -> str:
    """Check that a selected SPM container can start and report its version.

    Args:
        image: Docker image tag or local Singularity image path.
        runtime: ``"docker"`` or ``"singularity"``.

    Returns:
        Human-readable runtime, image, and SPM version information.

    Raises:
        RuntimeError: If the runtime or image is unavailable, or SPM cannot
            start inside the selected container.
    """
    if runtime == "docker":
        if shutil.which("docker") is None:
            fail("Docker was not found on PATH. Install Docker, then pull the SPM image.")
        inspect = subprocess.run(
            ["docker", "image", "inspect", image],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if inspect.returncode:
            fail(f"SPM image is not available locally: {image}\nPull it first: docker pull {image}")
        command = ["docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}", image, "--version"]
        label = "Docker image"
    elif runtime == "singularity":
        executable = shutil.which("singularity") or shutil.which("apptainer")
        if executable is None:
            fail("Neither Singularity nor Apptainer was found on PATH.")
        if not Path(image).is_file():
            fail(
                f"Singularity image does not exist: {image}\n"
                "Pull it first: singularity pull --name "
                f"{SINGULARITY_IMAGE} oras://ghcr.io/spm/spm-docker:singularity-matlab-25.01.02"
            )
        command = [executable, "exec", image, "--version"]
        label = f"{Path(executable).name.capitalize()} image"
    else:
        fail(f"Unsupported runtime: {runtime}. Use 'docker' or 'singularity'.")

    result = subprocess.run(command, check=False, text=True, capture_output=True)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        message = f"SPM container check failed (exit status {result.returncode})."
        fail(f"{message}\n{detail}" if detail else message)
    version = result.stdout.strip()
    return f"Runtime: {runtime}\n{label}: {image}\nSPM version:\n{version}"


def run_spm_batch(mount_root: Path, job_file: Path, image: str, runtime: str) -> None:
    """Run a generated SPM batch in the selected container runtime.

    Args:
        mount_root: Host directory mounted at ``/data``.
        job_file: Generated SPM batch script below ``mount_root``.
        image: Docker image tag or local Singularity image path.
        runtime: ``"docker"`` or ``"singularity"``.

    Raises:
        RuntimeError: If the runtime or image is unavailable, or the SPM batch
            exits unsuccessfully.
    """
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
    """Generate an SPM Unified Segmentation batch script.

    Args:
        input_file: Container path to the input NIfTI file.
        output_dir: Container path where SPM writes results.
        native: Six flags selecting native tissue-class outputs.
        samp: Segmentation sampling distance in millimetres.

    Returns:
        Executable MATLAB batch-script source.
    """
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
    """Generate an SPM Image Calculator batch script.

    Args:
        inputs: Container paths to input NIfTI files.
        output: Container path for the output NIfTI file.
        expression: SPM Image Calculator expression using ``i1``, ``i2``, etc.
        batch_file: Container path for the saved ``matlabbatch`` MAT file.

    Returns:
        Executable MATLAB batch-script source.
    """
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
    """Rename SPM segmentation outputs to presurfer output names.

    Args:
        out: Directory containing SPM-produced segmentation files.
        stem: NIfTI basename without its extension.
        classes: Native tissue-class numbers retained by the workflow.
    """
    for produced, suffix in ((f"m{stem}.nii", "_biascorrected.nii"),
                             (f"BiasField_{stem}.nii", "_biasfield.nii")):
        (out / produced).replace(out / f"{stem}{suffix}")
    for number in classes:
        (out / f"c{number}{stem}.nii").replace(out / f"{stem}_class{number}.nii")
    (out / f"{stem}_seg8.mat").unlink(missing_ok=True)


def prepare_output_dir(output_dir: Path, clobber: bool) -> None:
    """Create an output directory, optionally replacing an existing one.

    Args:
        output_dir: Workflow output directory to create.
        clobber: Whether to remove an existing output directory first.

    Raises:
        RuntimeError: If the output already exists without ``clobber``, or is
            an existing file rather than a directory.
    """
    if output_dir.exists():
        if not output_dir.is_dir():
            fail(f"Output path exists and is not a directory: {output_dir}")
        if not clobber:
            fail(f"Output directory already exists: {output_dir}\nUse --clobber to overwrite it.")
        shutil.rmtree(output_dir)
    output_dir.mkdir()


def run_segmentation(source: Path, kind: str, image: str, runtime: str, clobber: bool = False) -> Path:
    """Run one configured presurfer SPM segmentation workflow.

    Args:
        source: Input ``.nii`` or ``.nii.gz`` file.
        kind: Workflow name: ``"biascorrect"``, ``"UNI"``, or ``"INV2"``.
        image: Docker image tag or local Singularity image path.
        runtime: ``"docker"`` or ``"singularity"``.
        clobber: Whether to replace an existing workflow output directory.

    Returns:
        Created ``presurf_<kind>`` output directory.

    Raises:
        RuntimeError: If input validation, container execution, or expected SPM
            output handling fails.
    """
    source = source.resolve()
    if not source.is_file():
        fail(f"Input file does not exist: {source}")
    out = source.parent / f"presurf_{kind}"
    prepare_output_dir(out, clobber)
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


def mprageise(inv2: Path, uni: Path, image: str, runtime: str, clobber: bool = False) -> Path:
    """Create a MPRAGEised UNI image from INV2 and UNI acquisitions.

    The workflow bias-corrects INV2 with SPM, min-max normalizes the resulting
    image, and multiplies it voxelwise with UNI.

    Args:
        inv2: INV2 ``.nii`` or ``.nii.gz`` input file.
        uni: UNI ``.nii`` or ``.nii.gz`` input file.
        image: Docker image tag or local Singularity image path.
        runtime: ``"docker"`` or ``"singularity"``.
        clobber: Whether to replace existing bias-correction and MPRAGEise
            output directories.

    Returns:
        Path to the generated ``*_MPRAGEised.nii`` image.

    Raises:
        RuntimeError: If SPM bias correction fails or NumPy/NiBabel is absent.
    """
    bias_dir = run_segmentation(inv2, "biascorrect", image, runtime, clobber)
    try:
        import nibabel as nib
        import numpy as np
    except ImportError:
        fail("MPRAGEise needs numpy and nibabel. Install with: pip install -r requirements.txt")
    uni = uni.resolve()
    output_dir = uni.parent / "presurf_MPRAGEise"
    prepare_output_dir(output_dir, clobber)
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
def spm_biascorrect(
    input_file: str | Path,
    *,
    image: str = IMAGE,
    runtime: str = "docker",
    clobber: bool = False,
) -> Path:
    """Run SPM bias correction.

    Args:
        input_file: Path to a ``.nii`` or ``.nii.gz`` image.
        image: Docker image tag or local Singularity image path. Defaults to the
            pinned official SPM25 Docker image.
        runtime: ``"docker"`` or ``"singularity"``. Defaults to ``"docker"``.
        clobber: Whether to replace an existing output directory. Defaults to
            ``False``.

    Returns:
        Path to the ``presurf_biascorrect`` output directory.

    Raises:
        RuntimeError: If input validation or SPM execution fails.
    """
    return run_segmentation(Path(input_file), "biascorrect", image, runtime, clobber)


def spm_mprageise(
    inv2_file: str | Path,
    uni_file: str | Path,
    *,
    image: str = IMAGE,
    runtime: str = "docker",
    clobber: bool = False,
) -> Path:
    """Create a MPRAGEised UNI image.

    Args:
        inv2_file: Path to the INV2 ``.nii`` or ``.nii.gz`` image.
        uni_file: Path to the UNI ``.nii`` or ``.nii.gz`` image.
        image: Docker image tag or local Singularity image path. Defaults to the
            pinned official SPM25 Docker image.
        runtime: ``"docker"`` or ``"singularity"``. Defaults to ``"docker"``.
        clobber: Whether to replace existing output directories. Defaults to
            ``False``.

    Returns:
        Path to the generated ``*_MPRAGEised.nii`` image.

    Raises:
        RuntimeError: If SPM bias correction or image processing fails.
    """
    return mprageise(Path(inv2_file), Path(uni_file), image, runtime, clobber)


def spm_stripmask(
    input_file: str | Path,
    *,
    image: str = IMAGE,
    runtime: str = "docker",
    clobber: bool = False,
) -> Path:
    """Generate an INV2-derived non-brain strip mask.

    Args:
        input_file: Path to an INV2 ``.nii`` or ``.nii.gz`` image.
        image: Docker image tag or local Singularity image path. Defaults to the
            pinned official SPM25 Docker image.
        runtime: ``"docker"`` or ``"singularity"``. Defaults to ``"docker"``.
        clobber: Whether to replace an existing output directory. Defaults to
            ``False``.

    Returns:
        Path to the ``presurf_INV2`` output directory, including the strip mask.

    Raises:
        RuntimeError: If input validation or SPM execution fails.
    """
    return run_segmentation(Path(input_file), "INV2", image, runtime, clobber)


def spm_seg(
    input_file: str | Path,
    *,
    image: str = IMAGE,
    runtime: str = "docker",
    clobber: bool = False,
) -> Path:
    """Generate UNI tissue-class, brain-mask, and WM-mask outputs.

    Args:
        input_file: Path to a UNI ``.nii`` or ``.nii.gz`` image.
        image: Docker image tag or local Singularity image path. Defaults to the
            pinned official SPM25 Docker image.
        runtime: ``"docker"`` or ``"singularity"``. Defaults to ``"docker"``.
        clobber: Whether to replace an existing output directory. Defaults to
            ``False``.

    Returns:
        Path to the ``presurf_UNI`` output directory.

    Raises:
        RuntimeError: If input validation or SPM execution fails.
    """
    return run_segmentation(Path(input_file), "UNI", image, runtime, clobber)


def _run_command(ctx: click.Context, operation: object, *args: Path) -> None:
    """Run a public workflow and translate its errors for the Click CLI.

    Args:
        ctx: Click context containing runtime configuration.
        operation: Public workflow function to call.
        *args: NIfTI input paths accepted by the workflow.

    Raises:
        click.ClickException: If the workflow fails before producing output.
    """
    try:
        output = operation(*args, **ctx.obj)
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(str(output))


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
)
@click.option("--image", help="Docker image tag. Docker is the default runtime.")
@click.option(
    "--sif",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Singularity or Apptainer SIF file.",
)
@click.option("--check", "check_", is_flag=True, help="Check the selected SPM container and print its version.")
@click.option("--clobber", is_flag=True, help="Replace existing workflow output directories.")
@click.pass_context
def main(ctx: click.Context, image: str | None, sif: Path | None, check_: bool, clobber: bool) -> None:
    """Run MATLAB-free presurfer workflows through SPM Standalone.

    Args:
        ctx: Click context used to pass selected runtime configuration.
        image: Optional Docker image tag.
        sif: Optional local Singularity or Apptainer SIF path.
        check_: Whether to check the selected container and exit.
        clobber: Whether workflows may replace existing output directories.

    Raises:
        click.UsageError: If Docker and SIF image options are combined.
    """
    if image and sif:
        raise click.UsageError("Use either --image or --sif, not both.")
    ctx.ensure_object(dict)
    ctx.obj["image"] = str(sif) if sif else (image or IMAGE)
    ctx.obj["runtime"] = "singularity" if sif else "docker"
    ctx.obj["clobber"] = clobber
    if check_:
        try:
            click.echo(check_container(ctx.obj["image"], ctx.obj["runtime"]))
        except RuntimeError as error:
            raise click.ClickException(str(error)) from error
        ctx.exit()
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command(name="biascorrect")
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def presurf_biascorrect(ctx: click.Context, input_file: Path) -> None:
    """Create a bias-corrected image from INPUT_FILE."""
    _run_command(ctx, spm_biascorrect, input_file)


@main.command(name="MPRAGEise")
@click.argument("inv2_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("uni_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def presurf_mprageise(ctx: click.Context, inv2_file: Path, uni_file: Path) -> None:
    """Create a MPRAGEised UNI image from INV2_FILE and UNI_FILE."""
    _run_command(ctx, spm_mprageise, inv2_file, uni_file)


@main.command(name="stripmask")
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def presurf_inv2(ctx: click.Context, input_file: Path) -> None:
    """Create an INV2-derived strip mask from INPUT_FILE."""
    _run_command(ctx, spm_stripmask, input_file)


@main.command(name="brainmask")
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def presurf_uni(ctx: click.Context, input_file: Path) -> None:
    """Create UNI tissue classes, brain mask, and WM mask from INPUT_FILE."""
    _run_command(ctx, spm_seg, input_file)


if __name__ == "__main__":
    main()
