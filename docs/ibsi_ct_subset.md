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
  The default is fixed bin width with `bin_width=25 HU`, `bin_origin=-1024 HU`,
  and `levels=256`. The fixed origin is shared across cohort cases; values
  outside the declared range are rejected rather than silently clipped.
- Feature reports include `profile=CT_IBSI_SUBSET_V1` and the processing
  parameters needed to reproduce the calculation.

## Validation boundary

This subset includes selected first-order, GLCM, and shape features. It has not
been validated against all IBSI reference datasets or reference values.
Therefore publications must describe it as IBSI-aligned or IBSI-informed, not
as fully IBSI-compliant. Full compliance requires the official IBSI Phase 1 and
Phase 2 benchmark workflow for every claimed feature and preprocessing scheme.
