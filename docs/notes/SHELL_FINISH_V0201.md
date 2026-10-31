# Shell navigation and finish — 0.20.1

The processing and result panels now include a persistent, labeled Back to tools
button. It returns to the wheel while preserving queued/running work, output files
and the selected tools. The wheel's context button returns to processing/results.

Moving the processing panel updates its current position. Progress updates and
successful completion retain that position instead of snapping back to the old
wheel location. The draggable header elides long status labels, and visual state
changes preserve the user's current location while fitting the available screen.

Result buttons are laid out in readable rows, including when PDF, Word and Markdown
outputs are available together. Their dimensions are settled before the panel
height is calculated, preventing thin, clipped rows on first completion. The first
output action is emphasized. A failed file's reason is shown directly with its
filename; the results panel continues to identify mixed-batch failures.

The visual finish uses restrained neutral surfaces, quieter active wheel segments,
sentence-case tool labels, consistent controls and a clear primary action. Redundant
single-tool instructions are removed. A Qt ARGB color interpretation error that
produced yellow outlines is corrected. Keyboard focus remains visible, without
making mouse-focused icon buttons look like selected controls.

Validation includes the actual running-header drag, stage update and completion
sequence; visible Back navigation after a successful conversion; starting a fresh
batch without removing previous results; and readable multi-format result actions
on small work areas. Source rendering, display scaling and packaged offline jobs
are checked before delivery.
