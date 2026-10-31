# HEEH-V1 full-series real-data study (TCIA CT-Phantom4Radiomics)

Statistical extension of the single-slice protocol to all 172 slices of the downloaded real series. No clinical claims.

## First-order agreement, all slices (24 mm ROI)
- 172/172 slices within the 1e-6 tolerance (rate 1.000); max absolute error 0.000e+00.

## ROI-radius sensitivity (mid slice)
- r = 12 mm (960 voxels): within tolerance True; max error 0.000e+00
- r = 18 mm (2188 voxels): within tolerance True; max error 0.000e+00
- r = 24 mm (3884 voxels): within tolerance True; max error 0.000e+00
- r = 30 mm (6052 voxels): within tolerance True; max error 0.000e+00
- r = 36 mm (8732 voxels): within tolerance True; max error 0.000e+00

## Air-region CT-number calibration, all slices
- Worst-slice deviation 14.39 HU (slice 9); all slices within +/-30 HU: True.

## Export/privacy round trip, all slices
- Accepted 172/172 (1.000); tamper-rejection checked on 11 deterministically sampled slices, rejected 11/11.

## IBSI morphology reference comparison
- Real 3D sphere ROI: voxel-count 57952.7 mm3 vs PyRadiomics MeshVolume 57899.8 mm3 (internal definitional gap 0.0914%).
- Separate PyRadiomics reference comparison: 75 rows assessed; 75 passed; 0 failed; 195 are categorized as not assessed in `verification/results/ibsi_configuration_d_verification.json`. They are neither passes nor failures.
- Finding: All 75 comparable PyRadiomics reference rows pass, including nine newly mapped GLDM features. The remaining rows are not counted as passes or failures because they use different aggregation semantics, are pipeline-stage diagnostics, or lack a defensible equivalent in PyRadiomics. The earlier eight morphology failures were reproduced when intensity re-segmentation was incorrectly used as the shape mask; shape features now use the original ROI mask while intensity features use the re-segmented mask. This paired verification identifies and corrects the source of those failures. The smooth-ROI mesh-versus-voxel difference below is a separate, feature-definition-specific observation.

## Limitations
- All results describe the single real recorded phantom series only.
- Radiomics ROIs are geometric regions; no clinical or diagnostic meaning is attached.
- PyRadiomics agreement covers matched first-order statistics on 2D ROIs and shape definitions on one 3D ROI.
- The export gate exercise covers this series' slices only; it is not a clinical privacy estimate.
- Morphology and other feature results are limited to the pinned IBSI CT phantom, the stated processing configuration, and features with available reference values.
- No clinical accuracy, diagnostic, or full IBSI compliance claim is made.
