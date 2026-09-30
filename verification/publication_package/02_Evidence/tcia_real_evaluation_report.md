# HEEH-V1 real-data evaluation (TCIA CT-Phantom4Radiomics)

This report contains only measured values on a downloaded real public series. It does not claim clinical accuracy or full IBSI compliance.

## Series provenance
- Collection: `CT-Phantom4Radiomics` (real archive downloaded via NBIA; CC BY 4.0; https://doi.org/10.7937/a1v1-rc66)
- SeriesInstanceUID: `1.3.6.1.4.1.14519.5.2.1.329084730054548979029758794636987310879`
- Downloaded ZIP SHA-256: `fe6d292dc6989ca85d8323781067a3781ddc21c62105403ee83af512725539ea` (44,282,129 bytes)
- DICOM slices: 172 (aggregate SHA-256 `33f6c4d9a382db93...`)

## Geometry and HU calibration
- Volume: 172 slices, 512x512, spacing [0.68359375, 0.68359375, 2.0] mm
- HU range (volume): -1024.0 .. 919.0
- Mid-slice air-region mean HU: -993.769 over 122563 air pixels (reference -1000 HU; |deviation| = 6.231, within ±30 HU: True); soft-tissue insert mean 33.3 HU

## Real-data ROI radiomics (mid axial slice, centered 24 mm radius ROI)
- ROI voxels: 3884
- App engine measured: mean 58.674047 HU, std 36.666334 HU, min -95.000 HU, max 157.000 HU
- PyRadiomics v3.0.1 matched first-order absolute errors: mean 0.000000000, std 0.000000000, min 0.000000000, max 0.000000000 (tolerance 1e-06)
- All within tolerance: True

## Real-data export/privacy round trip
- De-identification markers: PatientName=ANONYMOUS, PatientID=NEURO_34319c148f30bb44, PatientIdentityRemoved=
- Valid archive accepted by the export gate: True
- Tampered-manifest archive rejected: True
- Scope: One real de-identified CT slice exported through the application's own packaging path and validated by the application's own gate; not a clinical performance estimate.

## Limitations
- Single real public phantom series; results describe this series only.
- The radiomics ROI is a defined geometric region, not a clinical lesion; no diagnostic meaning is attached to its values.
- PyRadiomics agreement is matched first-order only, at one preprocessing setting.
- The export check exercises the real packaging path on one real de-identified slice; it does not estimate clinical privacy performance at scale.
- No clinical accuracy, diagnostic, or full IBSI compliance claim is made.
