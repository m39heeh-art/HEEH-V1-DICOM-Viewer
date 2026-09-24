# Contributing

HEEH-V1(TM) DICOM Viewer is research and education software. Contributions
must preserve that scope and must not introduce claims of clinical validity,
regulatory approval, or full standards conformance without independent
evidence.

## Development workflow

1. Create a focused branch from `main`.
2. Use Python 3.11 or 3.12 and install the locked dependencies:

   ```powershell
   python -m pip install -r requirements.lock
   python -m pip install pytest ruff
   ```

3. Run the focused tests, Ruff, and `cmd /c call .\verify.bat` before opening
   a pull request.
4. Do not commit patient data, credentials, runtime logs, model weights, or
   virtual environments.

## Scientific and privacy requirements

- Preserve calibrated source values separately from display data.
- Keep PHI and burned-in pixel limitations explicit.
- Describe radiomics as IBSI-aligned unless official reference workflows have
  been completed for the claimed features.
- Add or update tests for behavior changes and document reproducibility inputs.
