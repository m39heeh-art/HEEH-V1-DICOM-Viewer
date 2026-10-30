---
title: 'HEEH-V1™ DICOM Viewer: An Open-Source Streamlit Workstation for Reproducible DICOM, NIfTI, Quantitative Imaging, and Radiomics Research'
tags:
  - Python
  - medical imaging
  - DICOM
  - NIfTI
  - radiomics
  - reproducibility
  - Streamlit
authors:
  - name: Mohamad Yousef Heeh
    orcid: 0009-0004-2729-443X
    affiliation: 1
affiliations:
  - name: Independent researcher
    index: 1
date: 30 October 2026
bibliography: paper.bib
---

# Summary

HEEH-V1 is an open-source Python/Streamlit application for reproducible medical-image research and education. It provides an integrated environment for DICOM and selected volumetric-image viewing, calibrated measurements, CT intensity analysis, multiplanar and three-dimensional research visualization, radiomics-style feature calculation, provenance-aware export, and export validation.

The software is designed for researchers, educators, and biomedical engineers who need a transparent, extensible environment in which imaging workflows can be inspected, documented, and reproduced. HEEH-V1 is released under the MIT License and is explicitly intended for research and education rather than clinical care.

# Statement of Need

Medical imaging research depends on reliable image import, consistent intensity handling, transparent quantitative processing, and clear records of how images and derived outputs are generated. In many research settings, analysis values must be separated from display-only transformations, while export processes should preserve sufficient provenance to allow later review or reproduction.

Existing tools provide strong capabilities in individual areas, but researchers and educators may still need a lightweight, integrated environment in which image inspection, measurement, quantitative analysis, and export validation can be performed together. HEEH-V1 addresses this need by combining these functions in a single Streamlit application with explicit documentation of its scientific and clinical boundaries.

HEEH-V1 is not a certified medical device. It is not intended for diagnosis, prognosis, treatment planning, triage, or any patient-care decision. A feature being implemented in the software does not imply that every imaging modality, scanner, encoding, or clinical workflow has been validated.

# State of the Field

Established platforms such as 3D Slicer, OHIF, and PyRadiomics provide mature capabilities for image computing, visualization, and radiomics. 3D Slicer is a widely used open-source platform for medical-image computing and visualization, while OHIF provides web-based viewing workflows for medical imaging. PyRadiomics is a widely used open-source radiomics feature-extraction library.

HEEH-V1 is not intended to replace these platforms. Instead, it provides a complementary, education-friendly Streamlit environment that integrates selected viewing, measurement, quantitative imaging, and export-validation workflows. Its contribution is not a new diagnostic algorithm or a claim of superiority over established systems; rather, it is an integrated, transparent research environment with documented evidence boundaries.

Radiomics research also requires careful attention to feature definitions, preprocessing, region-of-interest structure, and reproducibility. Variation in these factors can affect quantitative outputs and complicate comparison across tools. HEEH-V1 therefore documents its tested workflows and distinguishes implemented functionality from independently validated capability.

# Software Design
The implementation separates image values used for analysis from display transformations. Where appropriate, DICOM rescale metadata are applied to analysis values, while display windowing and other visual transformations remain separate. This design is intended to reduce ambiguity between what a user sees on screen and the numerical values used in quantitative workflows.

The application includes provenance-aware export functionality and guarded export validation. Export products can be packaged with metadata describing their origin and processing context, while validation workflows are designed to detect selected forms of archive or manifest inconsistency. These features are intended to support reproducible research workflows rather than to provide a guarantee of anonymity, legal compliance, or protection against all security threats.

The repository includes automated tests, documentation, a pinned dependency lock file, Docker support, continuous-integration configuration, and a Zenodo archival record. The source code is released under the MIT License, and the project provides a citation file to support reproducible referencing.


# Research Impact Statement

A technical-validation preprint associated with HEEH-V1 reports 335 passing automated tests in a fully provisioned local environment. In a comparison using one public 172-slice CT phantom series from The Cancer Imaging Archive, four matched first-order features—mean, standard deviation, minimum, and maximum—were compared slice by slice with PyRadiomics 3.0.1. All 688 feature-by-slice comparisons were within the specified absolute-difference tolerance.

The same preprint reports agreement for populated Image Biomarker Standardisation Initiative Configuration D reference rows in a configured comparison workflow, successful export validation across the tested phantom series, and rejection of deterministic manifest-tampering probes. These results support reproducibility of the specified software and phantom workflows.

These findings do not establish clinical validity, diagnostic performance, patient-care readiness, general privacy effectiveness, full IBSI compliance, broad superiority, or equivalence beyond the tested features, settings, and data. The phantom slices are repeated measurements from one series and should not be interpreted as independent patients or datasets.

# Availability and Requirements

Project name: HEEH-V1™ DICOM Viewer

Project home page: https://github.com/m39heeh-art/HEEH-V1-DICOM-Viewer

Operating system: Windows, macOS, and Linux installation paths are documented; platform-specific behavior may vary.

Programming language: Python 3.11 or later.

Other requirements: Streamlit and the dependencies listed in the repository’s pinned requirements file. PyRadiomics and Z-Rad are optional dependencies for selected validation workflows.

License: MIT.

Restrictions: The software is intended for research and education only. It is not for clinical or patient-care use.

# AI Usage Disclosure

GitHub Copilot assisted with manuscript drafting and selected code edits during preparation of this package. The final analysis results were generated by executing computational scripts rather than by AI-generated calculations. The author reviewed and approved all text and code changes, accepts responsibility for their accuracy and integrity, and discloses this assistance in accordance with JOSS policy.

# References
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
