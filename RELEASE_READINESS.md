# DocFlow release-readiness evidence

Status: verified release candidate; production release remains blocked. Nothing was deployed.

## Tested source

- Repository: `vinithg9/test`
- Branch: `fix/release-verification`
- Tested commit: `2545814061b804ec1ce5c82c1607e21e407e1300`
- Verification completed November 2, 2026, 7:11 PM America/Chicago (November 3, 01:11 UTC).
- [Successful verification run](https://github.com/vinithg9/test/actions/runs/41557705508)
- [Downloadable test evidence](https://github.com/vinithg9/test/actions/runs/41557705508/artifacts/13195108734)
- Evidence archive SHA-256 and integrity metadata are retained by GitHub Actions. Artifacts expire after 30 days.
- This report is a documentation-only addition after that tested commit; it does not change application code.

## Final results

| Verification | Result | Scope |
| --- | --- | --- |
| Browser end-to-end tests | 105 passed, 0 failed | Chromium, Firefox, WebKit |
| Service and isolation tests | 13 passed, 0 failed | Real renderer, API validation, sandbox filesystem/network isolation |
| Python runtime dependency audit | No known vulnerabilities found | Resolved dependencies from server/requirements.txt |
| Sandbox capability probe | Passed | LibreOffice 7.3.7.2 on Ubuntu 22.04 CI |
| Responsive layouts | Passed | 320, 375, 768, and 1440 px; screenshots retained |
| Syntax, whitespace and inline CSP hash checks | Passed locally | JavaScript, Python, tracked changes |

The service tests run with Bubblewrap isolation enabled in CI. Local development tests additionally exercised the renderers without nested namespaces because this execution environment cannot create the additional sandbox. Development-mode results are not represented as production isolation evidence.

## What was exercised

- DOCX import/edit/download, common bold formatting, mixed root text and paragraphs, malformed/empty inputs, basic PDF downloads, pagination and unsupported-character errors.
- XLSX import/edit/download, first-sheet edits, other-sheet retention, unchanged numeric/boolean/text types, leading-zero text, formula serialization and replacement, additional rows, and CSV quoting/newlines/formula neutralization.
- PDF preview, annotation, readable downloaded outputs, merge page counts and content, split ranges/deduplication, invalid ranges, extraction, malformed inputs, and repeated-use worker cleanup.
- Word-to-PDF, Excel-to-PDF, PDF-to-Word through the real HTTP service and document renderers; downloaded files are reopened and their content checked.
- Layout fixtures cover Word tables, embedded images and explicit page breaks; Excel charts, embedded images and multiple sheets; PDF-to-Word table and image reconstruction.
- Unsafe Word HTML and spreadsheet markup, missing libraries, upload size enforcement, archive traversal, macro/binary restrictions, external rendering resources, cross-origin uploads, content type enforcement, request admission, source-file exposure and fail-closed secure conversion.
- A sandboxed subprocess could neither read an outside temporary host file nor connect to the network.
- Modal naming, Escape/focus restoration, and contained layouts for all four workspaces.

## Defects corrected

1. Unsafe imported Word HTML and pasted active resources.
2. Lost mixed text/paragraph content during DOCX export.
3. Changed spreadsheet types, leading-zero strings, cached formulas, and lost new formulas.
4. CSV formula injection and multiline/escaping errors.
5. Incorrect PDF wrapping and silent unsupported-character corruption in basic exports.
6. Outdated browser PDF/spreadsheet/export dependencies and PDF-viewer compatibility failures.
7. Firefox-specific line-break loss in Word PDF and CSV exports.
8. Missing per-file and PDF preview resource limits.
9. Missing background-worker cleanup after PDF preview and extraction.
10. Text-only converters replaced with an isolated layout-rendering service.
11. A known PyMuPDF dependency vulnerability, patched to 1.26.7.
12. Missing secure-renderer readiness checks, process limits and API validation.

## Production blockers

1. A Linux hosting target and access/budget are required. Static hosting and Cloudflare Workers cannot execute the renderer or its namespace sandbox.
2. Select an appropriate licensing model before publishing PDF-to-Word. PyMuPDF is offered under AGPL or commercial licensing; no project-license change or commercial purchase was made. See https://pymupdf.io/licensing.
3. Verify the exact target deployment: HTTPS/domain, proxy upload/rate limits, namespace policy, fonts, worker memory/process limits, timeout and crash cleanup, service restarts and rollback. Run the browser suite against that staging origin before promoting the tested source.

The example systemd/nginx configurations have not been exercised on a production host. No hosting account, domain, TLS certificate, public access change or deployment was created.

## Functional boundaries

The browser Word editor supports common text formatting, not full Microsoft Word round-trip fidelity: imported images/complex layouts and table structure are not preserved by that editing path. Use the File Converter with an original Office file for layout-preserving PDF rendering. The spreadsheet editor edits the first sheet and does not calculate formulas in the browser. Editor PDF buttons remain basic text exports.

PDF tools annotate existing pages; they do not replace/reflow original PDF text. PDF-to-Word reconstruction and renderer font substitution can vary with the source document. Scanned PDFs require OCR and are rejected. These boundaries remain visible in the application and README; the test suite does not establish pixel-identical conversion for arbitrary documents or universal Office compatibility.
