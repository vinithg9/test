# DocFlow

Word, Excel and PDF tools with a same-origin document conversion service. Development happens on the release-verification branch until release gates pass. The previous single-file app used text-only converters; the service now uses LibreOffice for Office-to-PDF and pdf2docx for PDF-to-Word reconstruction.

## Run locally

Use Python 3.12 on Linux. Install LibreOffice Writer/Calc, Bubblewrap, and DejaVu fonts through the OS package manager. Create a virtual environment and install `server/requirements.txt`.

```sh
python3 -m venv .venv
.venv/bin/pip install -r server/requirements.txt
.venv/bin/python server/app.py
```

Open `http://127.0.0.1:4173`. Production rendering requires working unprivileged Bubblewrap namespaces. Conversion fails closed if isolation cannot be created. The presence of the executable alone is not proof the kernel permits namespaces.

`DOCFLOW_DEV_UNSANDBOXED=1` is restricted to a loopback bind and exists only for local renderer tests. Never set it in a publicly reachable service or through a reverse proxy.

## Verify

```sh
.venv/bin/pip install pillow openpyxl
.venv/bin/python -m unittest discover -s tests -p test_conversion_service.py -v
npm install --no-save @playwright/test@1.64.1 docx@9.5.1 https://cdn.sheetjs.com/xlsx-0.20.3/xlsx-0.20.3.tgz pdf-lib@1.17.1 mammoth@1.9.1
npx playwright install --with-deps chromium firefox webkit
npx playwright test
```

The browser suite starts the service itself. The CI job runs service security/layout tests before three-browser tests and retains its HTML report, traces, screenshots, and downloaded outputs for 30 days. `scripts/update-csp.py` must run after changing inline scripts; the CSP uses content hashes.

## Supported behavior and limits

- Word editor: common text formatting and DOCX import/export. Active content and external resources are removed. Complex imported document layouts and images are not preserved by the editor.
- Spreadsheet editor: edit first-sheet cells; preserve other sheets and unchanged types when exporting XLSX. Formulas are exported but not calculated in the browser. CSV formula-like text receives an apostrophe prefix.
- PDF tools: preview up to 20 pages; annotate first-page text; merge up to 20 files; extract/split pages; extract text up to 500 pages. These tools run in the browser.
- File Converter: original DOCX/XLSX is uploaded to the server, rendered to PDF, then deleted after completion. Tables, charts, images, print areas, and page breaks use the document renderer. Fonts can affect pagination. Unsupported/missing fonts are not silently guaranteed to match Microsoft Office.
- PDF-to-Word reconstructs tables, images and editable text. Scanned PDFs require OCR and are rejected. Encrypted PDFs and documents over 200 pages are rejected. Arbitrary PDF reconstruction cannot be guaranteed pixel-identical.
- Editor PDF buttons remain basic Latin-text exports. Use File Converter with the original Office file for layout preservation. Unsupported characters in basic exports produce an explicit error.
- Uploads are limited to 25 MB; expanded Office archives to 100 MB. Macro binaries, encrypted ZIP entries, traversal paths, and linked rendering resources are rejected. Up to two render jobs and 16 service connections are admitted per instance. Temporary files are removed after each operation; crash/reboot cleanup should use an ephemeral `/tmp` mount.

## Production hosting requirements

Static hosting and Cloudflare Workers cannot execute LibreOffice or this sandbox. Deploy on a Linux host supporting unprivileged user/mount/network namespaces, behind HTTPS, with the service bound to loopback. `deploy/docflow.service` and `deploy/nginx.conf` are reviewable starting configurations, not a deployment.

Before publishing: verify Bubblewrap isolation on the exact host; verify fonts and the fidelity fixture set; exercise TLS, upload limits, request throttling, slow clients, timeout cleanup, process/memory limits, and restart behavior through the real reverse proxy; run the full browser suite against a staging origin; then promote the exact tested commit and retain rollback evidence. Apply edge per-client rate limits before public exposure. The service never trusts forwarded client-IP headers.

No hosting account, domain, paid resource, or production deployment is provisioned by these files. Readiness is determined by release evidence, not by the existence of a workflow or a successful earlier smoke test.

## Dependencies

Runtime browser dependencies are version-pinned CDN distributions and require network availability. Server dependencies are pinned in `server/requirements.txt`; installed LibreOffice and Bubblewrap versions come from the target OS and must be recorded in deployment evidence. PyMuPDF is an AGPL/commercial dual-licensed dependency; review and satisfy the chosen license before offering the service. Dependency source and license information must be available with a release.
