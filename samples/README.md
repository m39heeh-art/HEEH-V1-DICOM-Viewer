# HEEH-V1(TM) DICOM Viewer sample set

This folder contains optional demonstration assets for the HEEH-V1(TM) DICOM
Viewer publication:

- `HEEH-V1_DICOM_Viewer_export.zip` - an example export package containing
  pseudonymous DICOM, annotated image, measurements, radiomics, cohort metrics,
  XLSX, HTML, DICOM SR, and machine-readable manifest files.
- `screenshots/` - interface screenshots showing the research workflow.
- `demo.mp4` - a recorded interface demonstration.

The sample export is provided for research and education demonstrations only.
Run the local export validator before relying on an archive:

```text
python scripts/validate_export.py samples/HEEH-V1_DICOM_Viewer_export.zip
```

Do not add patient-identifiable images, unredacted DICOM, credentials, runtime
logs, or private model files to this directory.
