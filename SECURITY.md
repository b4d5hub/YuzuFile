# Security and privacy

YuzuFile processes documents locally using installed models and native libraries.
Preparation scripts download resources. Local inference does not mean local data
is encrypted or automatically deleted: job metadata, staging/results, and published
files can contain document content and identifying paths.

## Trust boundaries

PDF parsers, image decoders, native inference runtimes, and external OCR tools handle
untrusted input. A separate worker, Windows Job Objects, and resource limits reduce
failure impact; they are not a hardened security sandbox. The app does not claim
safe processing of arbitrary hostile documents.

Owned-path checks reject traversal and links/junctions for managed artifacts.
Cancellation clears managed staging when possible. Completed artifacts may persist
after a session closes or its result cards are cleared. Original files remain in
their source directories. Current storage has no automatic retention expiry.

## Reporting

A dedicated private security contact has not yet been configured. Before making
the repository public, the maintainer should enable GitHub private vulnerability
reporting or publish a monitored private address. Until then, do not publish an
exploit, sensitive PDF, credentials, or personal paths in a public issue. Request a
private reporting channel from the maintainer first.

A useful private report includes the affected version, minimal reproduction,
impact, and a safe sample where available. There is no published response-time SLA
or supported-version policy yet.

## Maintainer release checks

Review dependency vulnerabilities and provenance, inspect native binaries, audit
all files selected for publication, and test handling of invalid inputs, path
traversal, interrupted publication, and worker termination. Sanitizing README text
does not sanitize repository history or generated release archives.
