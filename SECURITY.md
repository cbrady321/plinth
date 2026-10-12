# Security policy

## Supported versions

Security fixes go into the latest release only.

## Reporting a vulnerability

Please do not open a public issue. Report it privately through GitHub's
[private vulnerability reporting](https://github.com/cbrady321/plinth/security/advisories/new)
with steps to reproduce and the version affected. You should get a reply within a week.

## Trust model

Plinth runs on your machine against data and configs you supply. Keep these limits in mind:

- **Stages are code.** Registered stages run with your privileges; only register stages you trust.
- **Manifests are trusted input.** File paths in a manifest are resolved relative to the dataset
  directory and may contain `..`, so a manifest can point a stage at any file the process can read.
  Only run pipelines on manifests from trusted sources.
- **Pipeline configs are trusted input.** They choose which registered stages run and with what
  parameters.
- **The researcher UI has no authentication.** It binds to `127.0.0.1` by default and rejects
  requests addressed to other hosts. It serves only files under the project's runs directory.
  Expose it with `--host` only on a network you trust.
