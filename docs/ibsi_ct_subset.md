# IBSI 1 CT radiomics support and validation

This document describes the implemented IBSI 1 CT workflows and the evidence
available for them. It is not a claim of complete IBSI conformance, clinical
validity, certification, or validation on patient cohorts.

## Scope

IBSI defines a radiomics processing framework, feature definitions, reference
values, and reporting guidance. The reference manual describes 11 feature
families containing 172 features: morphology (29), local intensity (2),
intensity-based statistics (18), intensity histogram (23), intensity-volume
histogram (5), GLCM (25), GLRLM (16), GLSZM (16), GLDZM (16), NGTDM (5), and
NGLDM (17). The IBSI CT path in `core/ibsi_radiomics.py` dispatches extraction
to the corresponding Z-Rad families. Results can still report a family as
unsupported when it is mathematically undefined for a particular ROI.

The standard's processing guidance also includes image and mask geometry,
segmentation conversion, interpolation, separate morphological and intensity
masks, re-segmentation, discretisation, aggregation, and processing/reporting
provenance. These requirements apply to a named processing profile; arbitrary
custom processing must not be presented as the corresponding reference
configuration.

## IBSI CT reference configurations

The application exposes configurations A–E on CT images with an imported
NIfTI mask or named DICOM RTSTRUCT ROI:

| Configuration | Processing profile |
| --- | --- |
| A | 2D texture/local-intensity extraction on the original grid; fixed HU range [-500, 400]; FBS 25 HU for texture and intensity histogram; direct IVH. |
| B | 2D extraction after 2 x 2 mm in-plane linear interpolation; nearest-integer intensities; mask interpolation threshold 0.5; fixed HU range [-500, 400]; FBN 32; direct IVH. |
| C | 3D linear interpolation to 2 mm isotropic; nearest-integer intensities; mask threshold 0.5; fixed HU range [-1000, 400]; FBS 25 HU for texture and intensity histogram; IVH FBS 2.5 HU. A user-modified range is recorded as a non-reference variant. |
| D | 3D linear interpolation to 2 mm isotropic; nearest-integer intensities; mask threshold 0.5; 3-SD outlier re-segmentation; FBN 32; direct IVH. |
| E | 3D cubic B-spline image interpolation to 2 mm isotropic; trilinear mask interpolation threshold 0.5; nearest-integer intensities; fixed HU range [-1000, 400] plus 3-SD outlier re-segmentation; FBN 32; IVH FBN 1000. |

Texture aggregation and dimension follow each reference configuration. Outputs
record preprocessing settings, implementation version, input fingerprints,
environment, result digest, and unsupported families.
The result view also shows all 11 feature families, their 172-definition
inventory counts, computed output counts, and family status. Computed output
counts are not a permanent-identifier feature map and must not be interpreted
as proof that every definition in a family was emitted.
Each A–E result also includes an IBSI reporting checklist for items 1–76.
The checklist includes allowlisted acquisition and reconstruction attributes
from DICOM headers, records processing settings known to the application, and
marks unavailable, inapplicable, or unclaimed items explicitly. Patient
identifiers and free-text DICOM descriptions are excluded. Study-level
information not supplied to the analysis is not inferred, and a checklist is
not a claim of complete IBSI compliance.

## Evidence available

The official IBSI CT phantom comparison in this workspace reports all populated
feature rows passing for A–E: A 346/346, B 346/346, C 210/210, D 270/270, and
E 210/210. Sixty stage-specific diagnostic rows for each of A, B, C, and E
are not included in those feature comparisons. These checks use the Z-Rad
reference pipelines shared with the application and are not an independent
implementation comparison.

The separate PyRadiomics comparison assesses 75 of the 270 Configuration D
reference rows; all 75 pass. The comparison now includes nine additional
GLDM features with direct PyRadiomics counterparts, in addition to the prior
66 matched rows. The remaining 195 rows are explicitly classified rather
than counted as failures: 66 use different aggregation semantics, 60 are
pipeline-stage diagnostics, 23 are histogram definitions not established as
equivalent, 22 belong to feature families not provided by PyRadiomics, 14
have morphology definitions not established as equivalent, seven have no
unambiguous feature mapping, two are local-intensity features not provided
by PyRadiomics, and one mapped feature is not emitted by PyRadiomics.
Not-assessed rows are neither passes nor failures. These categories and
per-row reasons are recorded in
`verification/results/ibsi_configuration_d_verification.json`.
Configuration E's official reference values are generated from the IBSI-1
workbook (CC BY 4.0). The digital phantom comparison covers all 482 populated reference rows: 481
pass and one `szm_lzhge_3D` result differs from the listed value (1494.6 vs.
1490; published tolerance 0). PyRadiomics 3.0.1 independently returns the
same measured value, which corroborates the implementation result but does
not resolve the disagreement with the official table. The official
[digital-phantom GLSZM matrix](https://ibsi.readthedocs.io/en/latest/06_Digital_phantom_texture_matrices.html)
contains five zones; evaluating the IBSI large-zone-high-grey-level formula
on that matrix gives 1494.6, matching both implementations but not the
feature-reference table's 1490. This points to an internal inconsistency in
the published reference materials; until IBSI clarifies it, the reference
comparison remains recorded as a mismatch. The digital-phantom inventory accounts for all 172 definitions: all 167 with
published reference values have implementation outputs. Permanent identifiers
were transcribed from the official feature manual. That manual lists an ID for
171 definitions, omits one for `szm_sze`, and assigns `1PR8` to both
`ih_min` and `ih_p10`; these registry inconsistencies remain explicit in the
inventory and are not silently repaired. The other five features have no
reference values and the IBSI manual explicitly says not to use them:

| Feature tag | IBSI permanent identifier | Feature |
| --- | --- | --- |
| `morph_vol_dens_ombb` | `ZH1A` | Volume density (oriented minimum bounding box) |
| `morph_area_dens_ombb` | `IQYR` | Area density (oriented minimum bounding box) |
| `morph_vol_dens_mvee` | `SWZ1` | Volume density (minimum volume enclosing ellipsoid) |
| `morph_area_dens_mvee` | `BRI8` | Area density (minimum volume enclosing ellipsoid) |
| `ivh_auc` | `9CMM` | Area under the IVH curve |

This exclusion follows the feature-specific notes in the
[official IBSI feature manual](https://ibsi.readthedocs.io/en/latest/03_Image_features.html).
It is not an implementation gap for recommended/reference-supported features.
Two IVH difference values are emitted as derived outputs but are not part of
the 172-definition inventory.

The default viewer's 2D unmasked exploratory analysis remains outside these
reference workflows. The dedicated A–E workflow must be used for the
corresponding CT profile; a passing phantom result does not transfer to the
default view or other data.

## Remaining work for complete IBSI 1 CT coverage

- Resolve the missing and duplicate permanent identifiers in the current
  official feature manual with IBSI; do not infer a replacement ID.
- Validate every applicable digital-phantom reference value and the official
  CT configurations using independent expected results. The current A–E
  reference comparisons share the application engine and are not independent.
- Resolve the single digital-phantom `szm_lzhge_3D` disagreement against
  IBSI's feature definition/reference provenance; do not widen the tolerance
  or claim complete validation until resolved.
- Add tests for geometry, interpolation grid origin/extent, interpolation
  precision, mask conversion, split morphological/intensity masks,
  discretisation boundaries, IVH, and 2D/2.5D/3D aggregation.
- Add any required filtered-image workflows (such as wavelet/Gabor transforms)
  only with explicit parameters and reference tests; they are not currently
  part of the A–E application workflow.
- Extend the IBSI reporting checklist with study-level acquisition,
  reconstruction, segmentation, and validation details when those data are
  supplied; they cannot be reliably inferred from an isolated image and mask.
- Keep CT's verified profile separate from MRI/PET or arbitrary intensity
  workflows. IBSI's manual notes that modality-specific data conversion
  methods are outside its scope; they require separately justified profiles.

Accordingly, describe the current implementation as IBSI 1 CT configuration
workflows with partial reference validation, not as applying all IBSI
requirements. IBSI is a standardisation initiative and reference framework,
not a substitute for clinical validation or regulatory approval.
