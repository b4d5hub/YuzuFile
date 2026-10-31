# Design decision record

These records explain the current implementation. They are not claims that every
decision is optimal or immutable. Supersede a record explicitly when behavior changes.

## ADR-001 — Local Windows desktop execution

**Status:** implemented. Documents are processed locally using prepared resources.
Qt and Windows tray/drag integration provide a lightweight entry point.

**Reason:** private document handling and direct filesystem workflows are core needs.
**Tradeoff:** native packaging, large model assets, and heterogeneous PCs make support
harder. Cross-platform desktop releases and a hosted service are separate projects.

## ADR-002 — Separate worker and bounded resources

**Status:** implemented. One conversion attempt runs in its own process; the desktop
owns SQLite. Versioned JSON communicates requests/progress. Windows Job Objects
manage the worker tree, while performance presets bound resources.

**Reason:** keep the UI responsive, support cancellation, and recover from native
engine failures. **Tradeoff:** process startup and model loading add latency. This
is failure isolation, not a hardened sandbox.

## ADR-003 — Fresh recognition, one page at a time

**Status:** implemented. OCR-dependent features render visible content before
recognition. Word appends each recognized page before preparing the next. Combined
exports reuse fresh recognition data.

**Reason:** old/garbled OCR and legacy font mappings must not silently become exported
text. **Tradeoff:** clean native PDFs lose their extraction advantage; re-recognition
can introduce errors, and rasterization flattens native PDF structure.

## ADR-004 — Specialized recognition with conditional fallbacks

**Status:** implemented. Indra, Arabic print recognition, RapidOCR, and Tesseract
have distinct roles and fallback conditions.

**Reason:** different scripts and layouts fail differently. **Tradeoff:** more model
assets, licensing obligations, and regression cases. No claim of perfect consensus
or automatic correction is justified; warnings and provenance remain necessary.

## ADR-005 — Session results without a History feature

**Status:** implemented in 0.27.0. Remove persistent History navigation, while
retaining internal job/artifact records for supervision and recovery.

**Reason:** keep the tray workflow simple without discarding recovery state or user
outputs. **Tradeoff:** restarting hides prior result cards, and internal data still
needs an explicit retention policy before broader distribution.

## ADR-006 — Source-adjacent outputs with safe names

**Status:** implemented. Default output follows each source; Merge/Arrange use the
first source directory. Manual destinations override this. Feature suffixes and
collision handling avoid overwriting originals.

**Reason:** users should find results where they work. **Tradeoff:** source folders
may be read-only or disappear; publication can fail after conversion. Recovery must
distinguish finished processing from successfully published output.

## ADR-007 — Staged artifacts and recovery

**Status:** implemented. Workers create outputs and a manifest in staging, then
promote the directory. The store validates/publishes results and records completion.

**Reason:** partial conversion output should not appear successful. **Tradeoff:**
filesystem and database updates cannot be committed as a single transaction;
recovery and cancellation-race tests remain essential.
