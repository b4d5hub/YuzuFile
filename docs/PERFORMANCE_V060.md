# Performance controls — PDFai 0.6.0

The Home form now has one Performance dropdown above Process PDFs. No settings page is added. Balanced is the initial choice; a submitted batch captures the selection, then the form resets to Balanced. History details show the selection, and Process Again recalls that job's level.

| Level | Maximum concurrent OCR pages / pages per part | Windows CPU ceiling | Worker-tree committed-memory ceiling |
| --- | --- | --- | --- |
| Low usage | 1 | 25% | 2 GiB |
| Balanced | 2 | 50% | 3 GiB |
| High performance | 4 | 85% | 4 GiB |

Small machines can use fewer workers. CPU ceilings apply to the conversion process tree, not the whole app or other applications, and represent maximum allocations rather than expected utilization. Parent job restrictions can impose lower effective limits. These are Windows Job Object controls; CPU/memory hard ceilings are not implemented for other operating systems.

Each file is still processed individually. OCR renders at most one part ahead, drains every recognition future, grafts the overlays in page order, deletes that part's temporary files, and releases the MuPDF cache before starting the next part. Markdown streams one page at a time and trims caches at part boundaries. Compression validation retains fixed-size per-page hashes instead of a second copy of every page's text. PDF compression/save operations remain native whole-document operations under the same process-tree budget; the entire pipeline is not a constant-memory PDF splitter.

Recognition DPI, pixel cap, languages, Markdown extraction and compression settings are identical across performance levels. Each Tesseract subprocess uses one OpenMP thread; other numerical libraries receive bounded thread settings before the supervised worker starts. Parallelism can improve throughput on longer documents but is not a guaranteed speedup for small PDFs.

Memory limits are ceilings, not reservations or targets. An unusually large PDF can exceed its selected budget and fail. Choose a higher level if that happens; source files remain unchanged and incomplete results are not published. The normal GUI and CLI use the supervisor, which applies Windows limits before releasing the worker's input request. Internal direct `--worker` invocations used by developer smoke tooling do not create their own Job Object.

Implementation uses the documented Windows [Job Object limits](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) and [CPU rate control](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_cpu_rate_control_information). Limits cover helper processes as well as the Python worker.

This release implements resource controls for the existing Tesseract/PyMuPDF pipeline. PaddleOCR-VL, LightOnOCR and RapidOCR are not installed or merged in this release. The three-engine implementation must first benchmark and reconcile regions, then reuse these budgets to schedule engine stages sequentially, release model memory between stages, and retry only disputed regions. Quality/verification settings must remain separate from performance so Low usage does not silently omit checks.

Verification covers real OCR and Markdown on three-page scans in every profile, unchanged rendered PDF appearance, ordered page coverage, bounded part cleanup, old-history migration, UI selection/reset/retry, and querying the native Windows CPU/memory limits. The packaged GUI smoke uses Low usage through its actual supervisor. This is local Windows validation; a clean-VM check remains outstanding.

Source validation: **69 tests passed in 45.56 seconds** on this Windows/Python environment. The updated Home form was also rendered and visually checked at the existing desktop size.

Packaged validation passed for bundled English/French/Arabic discovery, digital Markdown, scanned OCR/Markdown, existing OCR text with graphics, all three compression levels, and an actual frozen GUI conversion using Low usage. The portable executable and ZIP are under `dist/PDFai-0.6.0` and `dist/PDFai-Windows-0.6.0.zip`.
