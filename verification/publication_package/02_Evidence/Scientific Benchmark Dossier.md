# Scientific benchmark dossier

## Purpose and scope

This dossier summarizes the research and engineering measurements published
with HEEH-V1 DICOM Viewer v1.0.2. The evaluations use synthetic fixtures,
reference values, or public metadata as identified below. They do not
establish clinical accuracy, patient-level performance, diagnostic utility,
or superiority over another imaging platform.

The detailed methods, execution environments, and machine-readable values
are in `public_benchmark_report.md` and
`heeh_v1_public_benchmark_results.json`.

## Data provenance

The TCIA/NBIA `CT-Phantom4Radiomics` collection was inspected through its
public metadata interface. Its license is Creative Commons Attribution 4.0
International. The image archive was not downloaded, so the project has no
image-level result for that collection.

The separate IBSI CT phantom comparison used reference material from
`theibsi/data_sets`, commit
`6da96021bc91faf4c0cb7fd7fa56a4225d2064a8`, under CC BY-NC 3.0. The reference
data are not bundled with this release; see `../../README_DATA.md` for
acquisition instructions and licensing.

## Evaluations and results

### Synthetic CT phantom ROI

An ACR-style synthetic water ROI was analyzed with fixed bin width
discretization, bin width 2.0, 256 levels, and spacing 1.0 × 1.0. The measured
mean was `-0.04 HU` against a target of `0.00 ± 3.00 HU`; the measured
standard deviation was `10.02 HU` against a target of `10.00 ± 2.00 HU`.
This is a synthetic phantom result, not patient-data validation.

### Matched PyRadiomics comparison

Four first-order values from a deterministic synthetic ROI were compared with
PyRadiomics 3.0.1. The maximum absolute error was `0.0` at tolerance
`1e-6`. This result applies only to the stated ROI, features, and matched
configuration.

### IBSI Configuration D reference comparison

The configured Z-Rad reference pipeline passed 270 of 270 populated IBSI
Configuration D reference rows. A separate PyRadiomics reference-table
comparison passed 58 of 66 comparable rows, failed 8, and marked 204
unsupported. These are separate comparisons. The Z-Rad result does not
certify the application's separate radiomics implementation or full IBSI
Phase 1/2 compliance.

The default viewer's exploratory slice-radiomics path uses a 2D unmasked
image and is not comparable to Configuration D. No Configuration D pass/fail
result is claimed for that path.

### Generated archive challenge set

The export/archive validator classified all 20 generated valid fixtures and
all 20 generated invalid fixtures as expected. This constructed challenge set
does not estimate real-world sensitivity, specificity, or de-identification
effectiveness.

### Navigation-cache microbenchmark

The fixed synthetic workload reported mean elapsed time `0.003887 s`, median
elapsed time `0.003901 s`, and mean Python allocation peak `0.030 MB`.
Allocation peak was measured with `tracemalloc`; it excludes native
allocations, process resident memory, image decoding, model inference, and
end-to-end application performance.

## Reproducibility and limitations

The included JSON records benchmark parameters, environment details, and
input or script fingerprints where available. The result records also retain
historical paths from the original benchmark workspace; those paths do not
represent files in this public package. Use the adjacent evidence files for
the actual packaged artifacts.

Some comparisons require optional software and licensed reference data that
are not distributed here. Reproduction therefore depends on obtaining those
inputs under their stated terms and using the documented configuration.
Source revision metadata was unavailable in the benchmark workspace; the
reported software version is not a substitute for an exact source revision.

No clinical validation, multi-site generalizability study, image-level
CT-Phantom4Radiomics benchmark, full IBSI certification, or formal standards
conformance assessment was performed.
