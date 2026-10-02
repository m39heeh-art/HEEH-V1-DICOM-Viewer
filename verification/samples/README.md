# verification/samples — documentation screenshots

This folder contains UI screenshots used in the project documentation. It
intentionally does **not** include any DICOM export archive.

## Why no sample export ships

A demonstration export (`HEEH-V1_DICOM_Viewer_export.zip`) existed in local
development only. It was excluded from the public release because the
project's own publication gate requires every shared export to pass a
burned-in-identifier inspection and a redistribution-rights review before
release, and this package conservatively ships no pixel data at all.

To generate your own demonstration export, run the application, load any
image (synthetic test fixtures from the test suite are ideal), use the
Export dialog, and inspect the result with:

```
python scripts/validate_export.py path/to/export.zip
```

The screenshots subfolder contains UI captures used for documentation. No
accuracy or performance claim is based on anything in this folder, and no
file here is an input to the automated test suite.
