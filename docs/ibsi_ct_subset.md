# IBSI-aligned CT radiomics subset

The application exposes a reproducible CT radiomics subset. It is not a claim
of full IBSI compliance.

## Processing contract

- Source CT intensities remain in HU after DICOM rescale slope/intercept.
- `RadiomicsExtractor.preprocess_ct` validates finite values and positive voxel
  spacing.
- Resampling is explicit and opt-in through `target_spacing`; the interpolation
  order is recorded in provenance.
- Optional resegmentation uses an inclusive `(lower, upper)` HU interval and is
  recorded.
- First-order entropy and GLCM features use declared discretisation settings.
  The default is fixed bin width with `bin_width=25 HU` and `levels=256`.
- Feature reports include `profile=CT_IBSI_SUBSET_V1` and the processing
  parameters needed to reproduce the calculation.

## Validation boundary

This subset includes selected first-order, GLCM, and shape features. It has not
been validated against all IBSI reference datasets or reference values.
Therefore publications must describe it as IBSI-aligned or IBSI-informed, not
as fully IBSI-compliant. Full compliance requires the official IBSI Phase 1 and
Phase 2 benchmark workflow for every claimed feature and preprocessing scheme.

The opt-in IBSI Configuration D workflow accepts an imported 3D ROI mask as
NIfTI or DICOM RTSTRUCT and applies the IBSI manual's settings: 2 mm trilinear
resampling with nearest-integer intensity rounding, trilinear mask resampling
at a 0.5 threshold, 3-SD outlier re-segmentation, and fixed-bin-number
discretisation with 32 bins for texture and intensity-histogram features. The
same processing function is used by the phantom verifier and the application.
The official phantom currently passes all 270 populated Configuration D
reference rows through the configured Z-Rad reference pipeline. The separate
PyRadiomics reference extraction reports 58 of 66 comparable reference-table
rows passing, 8 failing, and 204 unsupported; this is not the default viewer
alignment result. The default viewer's 2D, unmasked radiomics view is
non-comparable to Configuration D and is not established as IBSI-compliant.
Nor does a single configuration certify all IBSI phases or all input cases.
When a published reference row lists zero tolerance, the verifier accounts
for half a unit at the last displayed decimal place, since reference values
are rounded for publication; both the published tolerance and effective
comparison precision are recorded.
