# Public release readiness

This is a preparation checklist, not a claim that PDFai is cleared for public
distribution. The current build targets personal use. No GitHub publication is
performed by preparing these documents.

## Licensing and provenance

- [ ] Inventory direct/transitive packages, native executables, DLLs, fonts, icons,
  model weights, conversion assets, and their exact revisions/licenses.
- [ ] Review PyMuPDF/PyMuPDF4LLM obligations against the chosen distribution model.
- [ ] Review the exact bundled Indra weights and output/use restrictions; obtain
  appropriate permission or replace incompatible components.
- [ ] Verify model provenance, conversion notices, and redistribution terms for
  every other OCR/vision asset. Do not infer weights licensing from code licensing.
- [ ] Choose a compatible project license and add its actual text. Do not label
  the repository MIT/Apache/AGPL merely because a dependency uses that license.
- [ ] Produce complete third-party notices and corresponding source where required.

Evidence starts with `pyproject.toml`, `requirements-windows.lock`, preparation
scripts, `vendor/` notices/manifests, and the generated package `LICENSES/` folder.
An automated package-license inventory is not a complete legal review.

## Repository hygiene

- [ ] Inspect the exact tracked/staged files and complete Git history.
- [ ] Exclude personal PDFs, Word/Markdown exports, screenshots with private data,
  app databases, machine-specific shortcuts, credentials, caches, and binaries.
- [ ] Check `outputs/`, `.artifact_work/`, `tmp/`, `vendor/`, and generated archives
  explicitly; current ignore rules are not a comprehensive publishing filter.
- [ ] Replace private test inputs with synthetic/redistributable fixtures.
- [ ] Configure a private security-reporting route and maintainer contact.

## Product quality

- [ ] Validate installation/startup on a clean supported Windows machine.
- [ ] Exercise tray activation, Shift-drag, modal windows, cancellation, quit, retry,
  multi-monitor placement, display scaling, and keyboard access.
- [ ] Test source-adjacent output, multi-folder batches, manual destinations,
  collisions, missing directories, and read-only output folders.
- [ ] Build a language/layout benchmark with ground truth and documented failures.
- [ ] Validate editable Word, Markdown assets, searchable PDF text/rendering, and
  image-only output. Inspect representative pages visually.
- [ ] Document retention and a safe way to manage persistent local artifacts.

## Reproducible distribution

- [ ] Validate setup from a clean checkout, including all model/native prerequisites.
- [ ] Run relevant/full tests and record skips and environment details.
- [ ] Build and run the frozen-module guard and an offline packaged smoke conversion.
- [ ] Establish CI only after separating model-heavy/Windows checks from fast checks.
- [ ] Decide on installer/signing/update delivery; the current output is portable.
- [ ] Add versioned release notes, checksums, supported OS requirements, and honest
  download/model sizes measured from the actual release.
- [ ] Recheck bundled source and notices after documentation changes.

## Suggested first public milestone

A limited desktop beta with cleared dependencies, straightforward setup, known
limitations, and a feedback route. A hosted service, auto-update infrastructure,
cross-platform support, and perfect OCR are not promises for this milestone.
