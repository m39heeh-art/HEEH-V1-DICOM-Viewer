# TCIA series-download implementation note

This note describes selected implementation details in the v1.0.2 release.
It is not a performance evaluation, and it does not claim a measured speedup
or production readiness.

## Connection reuse and retries

The application keeps a `requests.Session` for TCIA requests and configures
HTTP connection pools. Series downloads use up to five attempts and can resume
a partial response using a byte-range request when appropriate. The download
code validates archive and extraction limits before returning image files.

## Partial-download handling

The active series archive is written to `series.zip.tmp`. A completed series
is marked with `.series.complete`; incomplete extractions are not treated as
complete cache entries. The stale-file cleanup helper currently targets files
matching `*.zip.part` that are more than seven days old. It does not match the
active `series.zip.tmp` file, so this cleanup should not be interpreted as
removing every stale download artifact.

## Evidence boundary

The automated tests exercise selected retry, resume, archive, and TCIA flow
cases. The public evidence bundle does not contain a controlled network
benchmark comparing throughput or latency with and without connection reuse.
Server preparation time, network conditions, TCIA service behavior, archive
size, and local hardware affect observed download time.

See `../app.py` and `../verification/tests/test_suite.py` for implementation
and tests. These details apply to the code in the corresponding release
snapshot and may change in later versions.
