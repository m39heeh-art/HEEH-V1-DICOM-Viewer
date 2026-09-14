# DICOM display conformance boundary

## Implemented in software

The application preserves source pixel values for analysis and separates them
from the 8-bit display image. For DICOM inputs it validates and reports:

- `(0008,0060)` Modality
- `(0028,0004)` Photometric Interpretation
- `(0028,1050)` Window Center
- `(0028,1051)` Window Width
- `(0028,0010)` Rows and `(0028,0011)` Columns
- `(0028,0100)` Bits Allocated, `(0028,0101)` Bits Stored, and `(0028,0103)`
  Pixel Representation
- `(0028,1052)` Rescale Intercept and `(0028,1053)` Rescale Slope
- SOP Class UID and Transfer Syntax UID/name
- Pixel Spacing `(0028,0030)` in millimeters when supplied

CT rescaling uses the DICOM rescale equation before CT validation and
quantitative analysis. Windowing and MONOCHROME1/MONOCHROME2 handling affect
presentation only; they do not mutate analysis values.

File extensions are ingestion hints only. SOP Class and DICOM metadata are the
authoritative source for image identity and geometry. Enhanced CT and
compressed transfer syntaxes are recognized and reported; pixel decoding
requires a compatible pydicom handler and is never assumed from a filename.

Patient Name `(0010,0010)` is not displayed by default. This is a deliberate
privacy-preserving default, not a claim that the application anonymizes all
DICOM identifying attributes.

## GSDF limitation

DICOM PS3.14 GSDF defines the target grayscale response for a calibrated
display system. Applying a window and a monochrome presentation transform in
software is not sufficient to establish GSDF compliance. Compliance requires
an appropriate medical display, calibration, ambient-light control, and
external photometric quality-assurance measurements. This research application
does not certify or replace that process.

## Scope

This document describes software behavior and conformance boundaries. It is
not a regulatory submission, medical-device certificate, or clinical-use
validation report.
