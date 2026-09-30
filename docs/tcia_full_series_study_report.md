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

## Morphology 58/66 root cause (data-driven)
- Real 3D sphere ROI: voxel-count 57952.7 mm3 vs PyRadiomics MeshVolume 57899.8 mm3 (internal definitional gap 0.0914%).
- Recorded IBSI-table failures decomposed (signed, vs official expected values): volumes {'min': -0.0333695652173913, 'max': -0.03231607629427793}, surface {'min': 0.08309804384972556, 'max': 0.08309804384972556}, ratios {'min': -0.09707780380568497, 'max': 0.11999330071012161}, PCA {'min': -0.028269133985218235, 'max': 0.004463700611600456}.
- Finding: On a smooth real 3D sphere at the series' anisotropic spacing, PyRadiomics' mesh and voxel-count volume definitions agree to within 0.09%. In the recorded IBSI phantom comparison, PyRadiomics' two volume definitions also agree closely with each other, while both deviate from the official expected values by -3.34% to -3.23%; surface area deviates by +8.31%, and surface-derived ratios compound to -9.71% to +12.00%. The dominant source is therefore the reference phantom's mask/grid convention (the official values derive from the IBSI reference segmentation), with marching-cubes surface extraction on anisotropic voxels driving the larger surface and ratio deviations; PCA eigenvalue rows use a further decomposition convention. Reconciliation requires running the comparator on the IBSI reference segmentation itself and is disclosed as out of scope.

## Limitations
- All results describe the single real recorded phantom series only.
- Radiomics ROIs are geometric regions; no clinical or diagnostic meaning is attached.
- PyRadiomics agreement covers matched first-order statistics on 2D ROIs and shape definitions on one 3D ROI.
- The export gate exercise covers this series' slices only; it is not a clinical privacy estimate.
- The morphology analysis quantifies the mesh-vs-voxel-count definitional gap; full reconciliation with the official IBSI phantom mask remains out of scope.
- No clinical accuracy, diagnostic, or full IBSI compliance claim is made.
