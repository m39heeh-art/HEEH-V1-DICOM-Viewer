# Security Policy

HEEH-V1(TM) DICOM Viewer is research and education software. It is **not a
certified medical device** and must not be used for patient care.

## Supported versions

| Version | Supported |
| --- | --- |
| 1.0.2 | Yes |
| < 1.0.2 | No |

## Reporting a vulnerability or privacy concern

Preferred: open a **private GitHub security advisory** via
*Security → Report a vulnerability* on this repository.

Alternatively, email **m39.heeh@gmail.com** with the subject
`[HEEH-V1 security]`. Include a minimal reproduction, affected paths, and
your environment. Please do not open a public issue for an unpatched
vulnerability.

You will receive an acknowledgement within 7 days and a status update at
least every 14 days until resolution or documented decline.

## Scope guidance

In scope: the repository's own code (`app.py`, `core/`, `engines/`, `ui/`,
`utils/`, `scripts/`), the included launchers, Docker/compose profile,
export/de-identification logic, and documentation that makes security claims.

Out of scope: upstream dependencies (report to their maintainers; we track
them via `requirements.lock` and `pip check`), clinical-safety questions
(see the README disclaimer), and deployments that bypass the documented
localhost-only defaults.

## Deployment reminder

The application provides **no** authentication, authorization, TLS, or audit
logging by itself. Any networked deployment must sit behind an
organization-approved authenticated HTTPS gateway and complete a documented
privacy/security review before touching identifiable data.
