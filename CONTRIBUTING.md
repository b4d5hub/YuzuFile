# Contributing to PDFai

Public contribution infrastructure is being prepared. Start with the
[README](README.md), [architecture](docs/ARCHITECTURE.md), and
[development guide](docs/DEVELOPMENT.md). A project license and public release
policy still need resolution; do not assume a contributor agreement exists.

## Report a problem

Include the app version, Windows version, operation, selected languages/performance,
expected behavior, actual behavior, and minimal reproduction steps. Include a
sanitized warning/error and whether the problem occurs in source or packaged builds.
For visual bugs, include window size and display scaling.

Use a synthetic or redistributable PDF when possible. Do not post private PDFs,
personal paths, unredacted screenshots, or extracted confidential text. See
[security guidance](SECURITY.md) for sensitive findings.

## Make a change

1. Keep each change focused on one user-visible problem or engineering concern.
2. Use an isolated development library; never build tests around a personal app store.
3. Read the relevant implementation and tests before changing pipeline behavior.
4. Add meaningful regression coverage for failures, not tests that merely repeat code.
5. Run affected checks. Exercise real desktop interactions for UI changes.
6. Update documentation and model provenance when behavior/dependencies change.

Preserve these invariants:

- Originals are not overwritten; output collisions are handled explicitly.
- No GUI-thread inference or unbounded background work.
- Worker stdout remains structured protocol data.
- Path ownership checks remain in place before artifact deletion/publication.
- Cancellation terminates worker children and accounts for completed results.
- Fresh OCR remains page-by-page; language fallback must not silently omit a selected script.
- Recognition uncertainty is visible; do not invent text to improve apparent completeness.

## Pull request description

Explain the concrete problem, resulting behavior, and relevant tradeoffs. Include
validation commands/results and any prerequisites or skips. UI changes should show
before/after captures using non-private documents. Engine changes should include
representative accuracy/performance evidence rather than only confidence scores.

Do not commit model binaries, generated releases, personal samples, local libraries,
caches, or credentials. Dependency updates need license/provenance review and a
packaged verification pass. Do not add a CI badge until a real workflow exists.
