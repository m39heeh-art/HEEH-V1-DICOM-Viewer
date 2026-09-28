# verification/data — optional bulk data (not shipped)

This release **does not include** the third-party IBSI reference data or any
bulk validation images. The automated test suite passes without them; the
IBSI phantom tests skip automatically with a clear message when the data are
absent. Fetch the data below only to re-run the IBSI Configuration-D
cross-validation.

## Why the data are not shipped

- The IBSI CT phantoms are licensed **CC BY-NC 3.0** (noncommercial) and the
  digital phantom and reference values are **CC BY 4.0**. Redistribution is
  possible under those terms, but this package ships under MIT, so the
  cleanest publication posture is: ship the fetch instructions, obtain the
  data from the authoritative source, and follow each dataset's license.
- Medical-image pixel data always require an independent privacy review
  before redistribution.

## Fetching the IBSI reference data

1. Clone the official IBSI data repository and pin the tested revision:

   ```
   git clone https://github.com/theibsi/data_sets.git ibsi_validation
   cd ibsi_validation && git checkout 6da96021bc91faf4c0cb7fd7fa56a4225d2064a8
   ```

2. Place the phantom/reference files under
   `verification/data/ibsi_reference_data/` using the layout the tests
   expect:

   ```
   verification/data/ibsi_reference_data/
   |-- ibsi_1_ct_radiomics_phantom/
   |   |-- nifti/image/phantom.nii.gz
   |   `-- nifti/mask/mask.nii.gz
   |-- ibsi_2_ct_radiomics_phantom/
   |-- ibsi_1_digital_phantom/
   |-- ibsi_2_digital_phantom/
   `-- ibsi_1_reference_values/
       `-- ibsi_1_reference_values_config_D.csv
   ```

3. Install the optional Z-Rad reference engine used by the comparison test:

   ```
   pip install -e ".[ibsi]"
   ```

4. Re-run the suite. The skipped IBSI tests should now execute:

   ```
   python -m pytest verification/tests -q
   ```

The tests located at `verification/tests/test_ibsi_validation.py` and
`verification/tests/test_harmonization_kurtosis.py` document the exact
paths they read.

## Extended datasets (optional, large)

1. **Extended IBSI validation image set** (~842 MB as extracted): only
   required to re-run the extended cross-validation; the test suite passes
   without it. Use the same `theibsi/data_sets` checkout above and place it
   under `verification/data/ibsi_reference_data/ibsi_validation/`.

2. **TCIA NBIA retriever binary** (~132 MB): the app talks to TCIA over the
   public REST API and never needs it. Download from
   https://wiki.cancerimagingarchive.net/display/NBIA
   (Windows x64 build) if you want the standalone retriever.

## Windows first-run behavior (root-caused and fixed in this release)

Earlier release notes attributed first-run test failures after extraction to
antivirus file locking. Controlled experiments disproved that: the failures
were deterministic, and the mechanism was pytest's
`--basetemp=cache_logs/pytest_tmp` (from `pyproject.toml`) — pytest creates
the basetemp directory without creating its parents, so a freshly extracted
package (no `cache_logs/` directory yet) failed every test that uses pytest's
`tmp_path` fixture at setup.

This release ships a root `conftest.py` that creates the basetemp parent
directory before fixtures run. Verified from a pristine extraction: the
first test run passes fully green with no preliminary re-run.
