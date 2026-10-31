# Output directory — v0.7.4

Home includes one optional folder row with a read-only path, Choose button, and Reset action. Cancelling the picker preserves the current choice. The choice stays within this app session; it is not a saved default. Each queued job records its own destination, so subsequent folder changes do not redirect jobs already queued. Process Again restores the original destination.

History schema migration 4 adds output_directory, defaulting existing jobs to the managed YuzuFile library. New custom jobs write directly under <chosen folder>/YuzuFile-<source name>-<UUID>/result. The worker retains its atomic staging-to-result publication, with Markdown and relative assets kept together. No extra library copy is created. Open File, Open Folder, recovery, missing-output handling, and deletion use the recorded root.

Destinations are checked for existence and writability before queueing, and checked again for availability before the worker starts. Unique folders prevent collisions. Existing path validation continues to reject links/junctions, and deletion targets only manifest-recorded artifacts; original PDFs and unrelated files remain untouched.

Validation: 36 targeted UI, storage, operation, migration and real conversion checks passed. Coverage includes picker cancellation/reset, retries, per-job paths, history after restart, spaces/Unicode, missing/unwritable folders, unavailable destinations before worker start, non-overwrite behavior, asset deletion scope, and a real combined conversion into the selected folder.
