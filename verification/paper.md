HEEH-V1™ DICOM Viewer: An Open-Source Streamlit Workstation for Reproducible DICOM, NIfTI, Quantitative Imaging, Radiomics, and Experimental AI Research
Manuscript type: Software technical-validation study
Author: Mohamad Yousef Heeh
Affiliation: Independent researcher
ORCID: https://orcid.org/0009-0004-2729-443X
Corresponding author: Mohamad Yousef Heeh, m39.heeh@gmail.com
Abstract
Background
Open-source imaging software can support reproducible research, but implemented capability must be distinguished from clinical validation. We describe HEEH-V1, a research and education DICOM viewer, and evaluate selected quantitative workflows using a public CT phantom series and reference software.
Results
The fully provisioned local test run passed 335 tests with no skips. On one 172-slice CT phantom series, four matched first-order features (mean, standard deviation, minimum and maximum) were compared slice by slice with PyRadiomics 3.0.1: all 688 feature-by-slice pairs had an absolute difference of zero at a 1 x 10^-6 tolerance. All 270 populated IBSI Configuration D reference rows passed in the configured Z-Rad comparison; a separate PyRadiomics mapping assessed 66 rows, all passing, while 204 remained unassessed. Air-region means on all slices were within the project-set +/-30 HU criterion of -1000 HU (maximum deviation 14.39 HU). Export validation accepted 172/172 tested slices, and 11/11 deterministic manifest-tampering probes were rejected.
Conclusions
The findings support reproducibility of the specified software and phantom workflows. They do not demonstrate clinical performance, full IBSI compliance, general privacy effectiveness, superiority to established platforms, or equivalence beyond the tested features and data.
Keywords: DICOM; imaging informatics; radiomics; reproducibility; software validation; computed tomography
Background
Medical imaging research depends on reliable image import, intensity handling, quantitative processing and transparent export provenance. Variation in preprocessing and feature definitions can impair reproducibility, motivating standardized radiomics protocols and reference implementations [1,2]. DICOM defines a standard for medical-image information exchange [3]. A research viewer should not be assumed equivalent to a clinically validated diagnostic workstation.
Open-source image-computing platforms, modular DICOM viewers and viewer-comparison frameworks are already established [7,8]. Recent surveys have compared web-based DICOM viewers across functionality and performance [9], and a 2026 study compared a new open-source viewer's memory use with established macOS viewers on a large TCIA series [10]. In radiomics, multi-tool studies have compared feature outputs with Image Biomarker Standardisation Initiative (IBSI) references, documented substantial between-tool variation, and evaluated the effects of preprocessing and region-of-interest structure [11–13]. The present work therefore does not claim to be the first open-source DICOM viewer, the first integrated imaging platform, or a comprehensive comparison with existing viewers.
HEEH-V1 is an open-source research and education application for DICOM and selected volumetric-image viewing, measurement, quantitative workflows and export validation. Its long-term purpose is to provide an extensible environment in which researchers can inspect, combine and develop imaging tools using documented, standards-informed workflows. The study reported here evaluates selected software paths and their reproducibility; it does not establish that the platform is broadly adopted, superior, or ready for clinical use. It describes a research platform and bounded validation evidence—not a new diagnostic algorithm, clinical device, or proven route to clinical deployment.
Implementation
Software and intended use
HEEH-V1 version 1.0.2 is a Python/Streamlit application. Its selected research workflows include DICOM image loading and display, calibrated measurements, quantitative image and radiomics calculations, provenance reporting, and guarded export validation. The implementation maintains image values used for analysis separately from display transformations and applies DICOM rescale metadata where appropriate. The project source is released under the MIT License.
 
Figure 1. Research workflow from public imaging input through image handling, selected research workflows, export validation and evidence generation. The figure states the clinical and scientific scope boundary.
The software is intended for research and education. It is not a certified medical device and is not intended for diagnosis, prognosis, treatment planning, triage, or patient-care decisions. A feature being implemented does not mean that every modality, encoding, scanner, or workflow has been validated.
Evaluation design and reproducibility
The evaluation plan was a retrospective technical verification of existing software workflows, public phantom inputs and generated test fixtures. No clinical-performance endpoint or hypothesis about diagnostic benefit was tested.
GitHub Copilot assisted with manuscript drafting and edits to selected analysis code during preparation of this package; the specific model/version was not recorded in the study artifacts. The final analysis results were independently generated by executing the computational scripts, not by AI-generated calculations. The author has reviewed and approved all text and code changes, independently verified the data lineage, references, and results, and confirms this disclosure complies with the journal's current generative AI policy
The repository's complete automated test suite was run in a fully provisioned local environment with optional reference data present. The recorded run collected 335 tests and reported 335 passed, zero failed and zero skipped. This is software regression evidence, not clinical validation.
For an IBSI reference exercise, the dedicated Configuration D workflow and configured Z-Rad implementation were compared with the populated IBSI CT phantom reference table. A separate PyRadiomics reference-table mapping was restricted to features with defensible one-to-one mappings. Unmapped rows were reported as unassessed, not as passes or failures. These results do not establish full IBSI Phase 1 or Phase 2 compliance [1].
For the external-software comparison, one public 172-slice CT phantom series from the TCIA CT-Phantom4Radiomics collection [4,5] was analyzed. TCIA collection metadata describe the collection as derived from real patient data; the analyzed series is described as a task-based anthropomorphic phantom scan. It is not a patient cohort, and no clinical or diagnostic meaning was assigned to the geometric ROIs. This provenance is disclosed so a competent review body can determine whether an ethics review or exemption statement is required. On each slice, the same centered 24-mm-radius geometric ROI (3,884 pixels) was evaluated with HEEH-V1 and PyRadiomics 3.0.1 using a 25 HU bin width and voxel-array shift of zero. Mean, standard deviation, minimum and maximum were compared with an absolute-difference tolerance of 1 x 10^-6; PyRadiomics standard deviation was calculated as the square root of its variance. This produced 688 feature-by-slice pairs. The radius-sensitivity analysis compared 12, 18, 24, 30 and 36 mm radii on the designated mid-slice.
Air-region means were calculated for voxels at or below -950 HU and compared with -1000 HU using a project-set +/-30 HU criterion. This is a study-specific check, not a clinical or regulatory acceptance limit. Export validation was exercised on each slice; deterministic manifest corruption was tested on 11 slices selected at a fixed stride. A separate generated challenge set comprised 20 valid and 20 invalid archives; these constructed fixtures do not estimate real-world sensitivity or specificity.
Statistical analysis
The analysis was descriptive and implementation-focused. For the four matched first-order features, absolute differences were calculated for each slice and summarized by the number within the project-set tolerance, mean absolute difference, and maximum absolute difference. No inferential hypothesis tests or confidence intervals were calculated: the 172 slice measurements are repeated observations within one phantom series, not independent acquisitions or subjects. Other checks are reported as counts against their stated test inputs and criteria, not as estimates of clinical diagnostic performance.
Results
Automated and reference comparisons
The fully provisioned local suite passed 335/335 tests. The configured Z-Rad Configuration D comparison passed all 270 populated reference rows, with no compared row failing or unsupported. In the separate PyRadiomics table mapping, 66 rows were assessed and passed; 204 rows were not assessed because a defensible feature mapping was not established. The unassessed rows are neither passes nor failures.
TCIA phantom series
For the matched external-software comparison, all 172 slice ROIs were within tolerance for each of the four first-order features. Across 688 feature-by-slice pairs, the recorded mean and maximum absolute differences were zero for each feature (Table 1). All five mid-slice ROI-radius checks met the same tolerance.
Air-region means on all slices were within the project-set +/-30 HU criterion; the maximum deviation from -1000 HU was 14.39 HU. Export validation accepted 172/172 tested de-identified slice archives. All 11/11 deterministically sampled manifest-corruption probes were rejected.



Table 1. Matched first-order feature comparison between HEEH-V1 and PyRadiomics 3.0.1 across one TCIA CT phantom series.
Feature	Paired slice values	Within 1 x 10^-6 tolerance	Mean absolute difference	Maximum absolute difference
Mean	172	172	0	0
Standard deviation	172	172	0	0
Minimum	172	172	0	0
Maximum	172	172	0	0
The 172 slices are repeated measurements from one series and must not be interpreted as 172 independent patients or datasets.
Summary of measured checks
Evaluation	Result	Interpretation
Automated suite	335/335 passed; 0 skipped in the fully provisioned local run	Software regression only
IBSI Configuration D comparison using configured Z-Rad workflow	270/270 populated reference rows passed	One reference configuration; not full IBSI compliance
Separate PyRadiomics IBSI-table mapping	66/66 assessed passed; 204 unassessed	Unassessed values are neither passes nor failures
Matched first-order comparison on the TCIA series	688/688 feature-by-slice pairs had zero recorded absolute difference	Four features, one geometric ROI protocol, one phantom series
Air-region CT-number check	All slices within project-set +/-30 HU; worst deviation 14.39 HU	Phantom check; threshold is not a clinical standard
Export validation	172/172 accepted; 11/11 sampled tampered manifests rejected	Tested series and deterministic probes only
Constructed archive challenges	20 valid and 20 invalid fixtures classified as expected	Synthetic fixture check, not real-world operating characteristics
Discussion
The principal comparative result is exact agreement for four matched first-order features under one defined 2D protocol on one phantom series, alongside a configuration-specific IBSI reference exercise. This gives readers a reproducible check against established software and public reference values, with inputs and non-results made explicit. It does not demonstrate that HEEH-V1 is more accurate, more usable, or more capable than PyRadiomics, Z-Rad, 3D Slicer, OHIF, or other imaging platforms.
Potential utility is the integration of DICOM viewing, selected quantitative workflows, provenance and export checks in an open-source application whose evidence boundaries are stated. The present evaluation does not measure external adoption, usability, broad utility across institutions, scanners or modalities, or comparative end-to-end task performance. It therefore cannot establish that the software represents a significant advance over previously published tools. Prior viewer studies show that fair assessment requires explicit criteria and direct comparison; recent radiomics studies likewise show that agreement depends on the tool, preprocessing, and feature family [8–12]. These comparisons are context for the current bounded work, not evidence that HEEH-V1 has been evaluated against those platforms.
The first-order comparison is restricted to four summary statistics and a fixed processing configuration; equality of these values does not establish equivalence for texture, shape, other feature classes, or other software pathways. The IBSI evidence is limited to the stated reference configuration and mapped rows. The TCIA analysis used one public phantom series, and adjacent slices are not independent observations. The export and tamper checks do not prove anonymity, legal compliance, or resistance to all threats. No user study, clinical workflow deployment, diagnostic accuracy assessment, patient-outcome study, or clinical validation was performed.
Conclusions
HEEH-V1 is an open-source research and education DICOM viewer with selected quantitative imaging and export-validation workflows. Under the stated conditions, four first-order features agreed numerically with PyRadiomics across one 172-slice CT phantom series, and selected reference and regression checks passed. These results support reproducibility of the tested paths but do not establish clinical validity, patient-care readiness, general privacy effectiveness, full IBSI compliance, broad superiority, or a significant advance across imaging software as a whole.
Availability and requirements
Project name: HEEH-V1 DICOM Viewer
Project home page: https://github.com/m39heeh-art/HEEH-V1-DICOM-Viewer [6]
Application source revision: application code at commit `07f937aed1ab0df74cc88ff81759cba4a9cf551a`. The supplied archive retains that commit's tracked source files, with `CITATION.cff` affiliation metadata updated to “Independent Researcher” at the author's request; archive SHA-256 is `3ed6a7a690e88744d3b07623d4ed0df23f89aced871c939d470b4e3ddb616317`. The analysis script is a separate, updated artifact; its SHA-256 and the dependency-lock SHA-256 are recorded in `tcia_full_series_study.json`. The application source snapshot, updated citation metadata, analysis code, and result artifact must be treated as separate provenance items.
Operating system: The reported fully provisioned evaluation was run on Windows 10. The project documents Windows, macOS and Linux installation paths, but platform- and dependency-specific support has not been independently established for every workflow.
Programming language: Python 3.11.9 for the reported evaluation
Other requirements: Streamlit application; install the pinned requirements from `requirements.lock`. PyRadiomics 3.0.1 and Z-Rad 26.9.0 are optional validation dependencies.
License: MIT
Restrictions: No academic-use restriction under the project MIT license; users remain responsible for third-party dependency terms. The software is not for clinical or patient-care use.
List of abbreviations
DICOM: Digital Imaging and Communications in Medicine; HU: Hounsfield unit; IBSI: Image Biomarker Standardisation Initiative; ROI: region of interest; TCIA: The Cancer Imaging Archive.
Declarations
Ethics approval and consent to participate
"The evaluation utilized a publicly available, de-identified reference CT phantom dataset from the TCIA CT-Phantom4Radiomics collection. Because this study involves strictly secondary analysis of fully anonymized, publicly archived phantom imaging data and did not recruit human participants or perform any clinical interventions, institutional research ethics committee review and formal institutional review board (IRB) approval were not required.

Consent for publication
Not applicable.
Availability of data and materials
The analyzed series is from TCIA's CT-Phantom4Radiomics collection (data DOI: https://doi.org/10.7937/a1v1-rc66; SeriesInstanceUID: `1.3.6.1.4.1.14519.5.2.1.329084730054548979029758794636987310879`; downloaded archive SHA-256: `b28bf1a030b48b2fc68501ee28d9f98aff45ad8325a1c3781a45b20dd08d6471`). TCIA metadata describe the collection as derived from real patient data; the analyzed series is a task-based anthropomorphic phantom. The series is available from TCIA under the collection's CC BY 4.0 terms and is not redistributed here. Machine-readable results, the analysis script, dependency-lock hash, and reports are supplied as supplementary evidence. IBSI reference data are available from their official source under the applicable license and are not redistributed.
Competing interests
The author is the sole founder and developer of HEEH-V1, the software evaluated in this article. The author reports no financial or non-financial competing interests; this software relationship is disclosed for transparency.
Funding
No funding was received for this study.
Authors' contributions
MYH contributed to conceptualization, methodology, software, validation, investigation, resources, data curation, formal analysis, visualization, project administration, writing—original draft, and writing—review and editing. The author has reviewed and approved the final version of the manuscript.
Acknowledgements
Not applicable.
Use of generative AI and AI-assisted technologies
GitHub Copilot assisted with drafting and editing manuscript text and selected analysis-code changes during preparation of this package. The specific model/version was not recorded in the study artifacts. The final analysis results were independently generated by executing the supplied computational scripts. The author has reviewed the final manuscript and source code, accepts full responsibility for their accuracy and integrity, and confirms that this disclosure complies with the target journal’s current policy on generative AI use.
References
1. Zwanenburg A, Vallières M, Abdalah MA, et al. The Image Biomarker Standardisation Initiative: standardized quantitative radiomics for high-throughput image-based phenotyping. Radiology. 2020;295(2):328-338. https://doi.org/10.1148/radiol.2020191145.
2. van Griethuysen JJM, Fedorov A, Parmar C, et al. Computational Radiomics System to Decode the Radiographic Phenotype. Cancer Research. 2017;77(21):e104-e107. https://doi.org/10.1158/0008-5472.CAN-17-0339.
3. National Electrical Manufacturers Association. Digital Imaging and Communications in Medicine (DICOM) Standard. https://www.dicomstandard.org/current. Accessed 7 October 2026.
4. Clark K, Vendt B, Smith K, et al. The Cancer Imaging Archive (TCIA): maintaining and operating a public information repository. Journal of Digital Imaging. 2013;26:1045-1057. https://doi.org/10.1007/s10278-013-9622-7.
5. The Cancer Imaging Archive. CT-Phantom4Radiomics collection. Dataset DOI: https://doi.org/10.7937/a1v1-rc66.
6. HEEH-V1 DICOM Viewer. Source code at commit 07f937aed1ab0df74cc88ff81759cba4a9cf551a. https://github.com/m39heeh-art/HEEH-V1-DICOM-Viewer/commit/07f937aed1ab0df74cc88ff81759cba4a9cf551a. The Zenodo v1.0.2 record (https://doi.org/10.5281/zenodo.23020151) predates this repository revision and is not the exact source snapshot used for the revised validation evidence.
7. Fedorov A, Beichel R, Kalpathy-Cramer J, et al. 3D Slicer as an image computing platform for the Quantitative Imaging Network. Magnetic Resonance Imaging. 2012;30(9):1323-1341. https://doi.org/10.1016/j.mri.2012.05.001.
8. Ruiz M, Julià A, Boada I. Starviewer and its comparison with other open-source DICOM viewers using a novel hierarchical evaluation framework. International Journal of Medical Informatics. 2020;137:104098. https://doi.org/10.1016/j.ijmedinf.2020.104098.
9. Pereira H, Romero L, Miguel Faria P. Web-based DICOM viewers: a survey and a performance classification. Journal of Imaging Informatics in Medicine. 2025;38(3):1304-1322. https://doi.org/10.1007/s10278-024-01216-5.
10. Heo J, Kim D, Kim K, et al. OpenDicomViewer: a lightweight open-source DICOM viewer for macOS built with Swift. Journal of Imaging Informatics in Medicine. 2026. https://doi.org/10.1007/s10278-026-02085-w.
11. Lei M, Varghese B, Hwang D, et al. Benchmarking various radiomic toolkit features while applying the Image Biomarker Standardization Initiative toward clinical translation of radiomic analysis. Journal of Digital Imaging. 2021;34(5):1156-1170. https://doi.org/10.1007/s10278-021-00506-6.
12. Bettinelli A, Marturano F, Avanzo M, et al. A novel benchmarking approach to assess the agreement among radiomic tools. Radiology. 2022;303(3):533-541. https://doi.org/10.1148/radiol.211604.
13. Bettinelli A, Marturano F, Pirrone G, et al. Assessing the agreement of radiomic tools for dosiomics: a multi-software comparative study. Medical Physics. 2026;53(1):e70203. https://doi.org/10.1002/mp.70203.
