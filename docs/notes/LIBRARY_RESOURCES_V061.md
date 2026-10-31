# Library resource controls — YuzuFile 0.6.1

The existing Low usage / Balanced / High performance selector now governs the native-library lifecycle throughout a conversion. No additional controls or pages are introduced.

| Library / stage | Resource behavior |
| --- | --- |
| PyMuPDF scanning and output validation | Traverse pages in preset-sized parts; release caches at boundaries and completion |
| PyMuPDF native rendering | Low usage disables device caching; restore the previous setting after conversion, including failures |
| PyMuPDF4LLM | Heading analysis streams through the same page-part iterator; Markdown remains page-by-page with text-preservation checks |
| Pillow and figure export | One image at a time; close retry-resize images explicitly and release encoded/decoded figure buffers after each export |
| Compression | Fingerprint and verify pages in bounded parts, report progress, and clear native caches around image rewriting |
| Numerical helper runtimes | Existing preset thread limits are applied before the supervised worker starts |

Low usage, Balanced and High performance clear native caches after parts of at most 1, 2 and 4 pages respectively (fewer on small CPUs). The pinned PyMuPDF build does not expose current native cache-size accounting, so the policy clears caches by part instead of assuming an unenforceable cache-size target. The existing Windows process-tree ceilings of 2 / 3 / 4 GiB and 25 / 50 / 85 percent CPU remain the hard resource limits for supervised conversions.

The PDF remains one document. Native image rewriting and final PDF saving are whole-document operations because the pinned PyMuPDF API does not expose a page-range option for image rewriting. Those operations run under the same process-tree limits. The app does not split/rejoin PDFs for compression, preserving the existing handling of shared images, bookmarks, links and annotations.

Recognition resolution, language choices, heading rules, all text-preservation checks and compression quality are unchanged across presets. More resources can improve throughput but do not guarantee a speedup on every file. This version continues using the installed Tesseract/PyMuPDF/PyMuPDF4LLM pipeline; the researched PaddleOCR-VL/LightOnOCR/RapidOCR ensemble is not integrated.

The common native-library policy is scoped to a conversion and restored in a finally block. Temporary files and final publishing retain the existing atomic-output and cancellation behavior.

Validation: all **76 source tests passed in 56.46 seconds**, including real OCR across the three levels, cache-policy restoration after failure, ordered page-part traversal, and compression feature preservation in all profiles.
