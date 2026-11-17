# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's
[private vulnerability reporting](https://github.com/Ajmoylan/repo-posture/security/advisories/new)
rather than in a public issue. You'll get an acknowledgement within a few days.

## Scope and design

- repo-posture only makes read-only `GET` requests to the GitHub REST API.
- A token is optional and read from `GITHUB_TOKEN` or `GH_TOKEN`; it is never logged or written to
  a report. Use a fine-grained, read-only token.
- Supported version: the latest release on `main`.
