"""Same-origin document conversion service. Production conversion fails closed without Bubblewrap."""
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
MAX_UPLOAD = 25 * 1024 * 1024
MAX_EXPANDED = 100 * 1024 * 1024
SLOTS = threading.BoundedSemaphore(2)
ALLOWED = {'docx-to-pdf': ('.docx', '.pdf', 'application/pdf'),
           'xlsx-to-pdf': ('.xlsx', '.pdf', 'application/pdf'),
           'pdf-to-docx': ('.pdf', '.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')}

class ConversionError(Exception):
    pass

def validate_input(path, extension):
    if extension == '.pdf':
        if not path.read_bytes()[:8].startswith(b'%PDF-'):
            raise ConversionError('This file is not a valid PDF.')
        return
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(e.file_size for e in entries) > MAX_EXPANDED:
                raise ConversionError('The document expands beyond the safe processing limit.')
            names = set(archive.namelist())
            expected = 'word/document.xml' if extension == '.docx' else 'xl/workbook.xml'
            if expected not in names or '[Content_Types].xml' not in names:
                raise ConversionError('The document does not match its file type.')
            for entry in entries:
                name = entry.filename.replace('\\', '/')
                if name.startswith('/') or '..' in name.split('/') or entry.flag_bits & 1:
                    raise ConversionError('Unsafe or encrypted document archive.')
                if 'vbaproject' in name.lower() or name.lower().endswith('.bin'):
                    raise ConversionError('Documents containing macros or embedded binaries are not supported.')
                if name.endswith('.rels'):
                    rels = archive.read(entry)
                    if b'<!DOCTYPE' in rels.upper() or b'<!ENTITY' in rels.upper():
                        raise ConversionError('Unsafe document XML.')
                    # Rendering may dereference external images, templates, or linked sheets.
                    import xml.etree.ElementTree as ET
                    for rel in ET.fromstring(rels):
                        if rel.attrib.get('TargetMode', '').lower() == 'external' and not rel.attrib.get('Type', '').endswith('/hyperlink'):
                            raise ConversionError('Remove externally linked resources before converting.')
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ConversionError('This file is not a valid Office document.') from exc

def command_for(job, kind, sandbox=True):
    src_ext, out_ext, _ = ALLOWED[kind]
    work = '/work' if sandbox else str(job)
    source = work + '/input' + src_ext
    if kind == 'pdf-to-docx':
        command = [sys.executable, str(ROOT / 'server' / 'pdf_to_docx.py'), source, work + '/input.docx']
    else:
        command = [shutil.which('soffice') or '/usr/bin/soffice', '-env:UserInstallation=file://' + (('/tmp' if sandbox else str(job)) + '/docflow-profile'), '--headless', '--nologo', '--nodefault', '--nolockcheck', '--norestore', '--convert-to', 'pdf', '--outdir', work, source]
    if not sandbox:
        return command
    bwrap = shutil.which('bwrap')
    if not bwrap:
        raise ConversionError('Secure conversion is unavailable. No document was processed.')
    args = [bwrap, '--unshare-all', '--die-with-parent', '--new-session', '--cap-drop', 'ALL', '--clearenv']
    # Deliberately omit /home, service state, credentials, and host network access.
    for directory in ['/usr', '/bin', '/sbin', '/lib', '/lib64', '/opt']:
        if Path(directory).exists():
            args += ['--ro-bind', directory, directory]
    for directory in ['/etc/fonts', '/etc/alternatives', '/etc/libreoffice']:
        if Path(directory).exists():
            args += ['--ro-bind', directory, directory]
    args += ['--ro-bind', str(ROOT / 'server'), str(ROOT / 'server'), '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--bind', str(job), '/work', '--chdir', '/work', '--setenv', 'HOME', '/tmp', '--setenv', 'LANG', 'C.UTF-8', '--setenv', 'LD_LIBRARY_PATH', str(Path(sys.base_prefix) / 'lib'), '--setenv', 'PATH', '/usr/local/bin:/usr/bin:/bin']
    return args + command

def convert(job, kind):
    # This switch is for deterministic tests/development only; the HTTP server refuses it off loopback.
    sandbox = os.environ.get('DOCFLOW_DEV_UNSANDBOXED') != '1'
    command = command_for(job, kind, sandbox)
    environment = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(job), 'LANG': 'C.UTF-8', 'TMPDIR': str(job), 'LD_LIBRARY_PATH': str(Path(sys.base_prefix) / 'lib')}
    proc = subprocess.Popen([sys.executable, str(ROOT / 'server' / 'limit_exec.py'), *command], cwd=job, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        code = proc.wait(timeout=110)
    except subprocess.TimeoutExpired as exc:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        raise ConversionError('Conversion exceeded its time limit.') from exc
    finally:
        # Stop helper processes that outlive their parent.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if kind == 'pdf-to-docx' and code in [4,5,6]:
        raise ConversionError({4:'No selectable text found. Scanned PDFs require OCR.',5:'Encrypted PDFs are not supported.',6:'PDF to Word supports up to 200 pages.'}[code])
    output = job / ('input' + ALLOWED[kind][1])
    if code or not output.is_file() or output.stat().st_size == 0 or output.stat().st_size > MAX_EXPANDED:
        raise ConversionError('The document could not be converted safely. It may be encrypted, unsupported, or too complex.')
    return output.read_bytes()

class Handler(BaseHTTPRequestHandler):
    server_version = 'DocFlow'
    sys_version = ''
    protocol_version = 'HTTP/1.0'
    def log_message(self, fmt, *args):
        # Do not log filenames, document contents, or request bodies.
        return
    def send_bytes(self, code, body, mime='application/json', download=None):
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        if download:
            self.send_header('Content-Disposition', 'attachment; filename="' + download + '"')
        self.end_headers()
        self.wfile.write(body)
    def error(self, code, message):
        self.send_bytes(code, json.dumps({'error': message}).encode())
    def do_GET(self):
        route = urlsplit(self.path).path
        if route == '/api/health':
            return self.send_bytes(200, json.dumps({'status': 'ok', 'secure_conversion': bool(shutil.which('bwrap')) and os.environ.get('DOCFLOW_DEV_UNSANDBOXED') != '1'}).encode())
        if route not in ['/', '/index.html', '/docflow-single-file.html']:
            return self.error(404, 'Not found')
        self.send_bytes(200, (ROOT / 'docflow-single-file.html').read_bytes(), 'text/html; charset=utf-8')
    def do_POST(self):
        kind = urlsplit(self.path).path.removeprefix('/api/convert/')
        if not self.path.startswith('/api/convert/') or kind not in ALLOWED:
            return self.error(404, 'Unknown conversion')
        # No cross-origin conversion requests, including browser forms.
        origin = self.headers.get('Origin')
        if origin:
            host = urlsplit(origin).netloc
            if host != self.headers.get('Host') or urlsplit(origin).scheme not in ['http', 'https']:
                return self.error(403, 'Cross-origin uploads are not allowed')
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/octet-stream':
            return self.error(415, 'Send the document as application/octet-stream')
        if self.headers.get('Transfer-Encoding'):
            return self.error(400, 'Chunked uploads are not supported')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.error(400, 'Invalid upload size')
        if length <= 0 or length > MAX_UPLOAD:
            return self.error(413, 'Choose a nonempty document up to 25 MB')
        if not SLOTS.acquire(blocking=False):
            return self.error(429, 'The converter is busy. Please try again shortly.')
        try:
            self.connection.settimeout(30)
            with tempfile.TemporaryDirectory(prefix='docflow-') as tmp:
                job = Path(tmp)
                source = job / ('input' + ALLOWED[kind][0])
                # Stream to disk so rejected or interrupted uploads never occupy large heap buffers.
                with source.open('wb') as output:
                    remaining = length
                    while remaining:
                        chunk = self.rfile.read(min(65536, remaining))
                        if not chunk:
                            raise ConversionError('Upload was interrupted')
                        output.write(chunk)
                        remaining -= len(chunk)
                validate_input(source, ALLOWED[kind][0])
                result = convert(job, kind)
                self.send_bytes(200, result, ALLOWED[kind][2], 'converted' + ALLOWED[kind][1])
        except ConversionError as exc:
            self.error(422, str(exc))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.error(500, 'Conversion service failed. Please try again later.')
        finally:
            SLOTS.release()

class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8
    # Conversion slots cap rendering; admission also caps slow header/upload connections.
    def __init__(self, *args, **kwargs):
        self.connections = threading.BoundedSemaphore(16)
        super().__init__(*args, **kwargs)
    def process_request(self, request, address):
        request.settimeout(30)
        if not self.connections.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.connections.release()
            raise
    def process_request_thread(self, *args):
        try:
            super().process_request_thread(*args)
        finally:
            self.connections.release()

if __name__ == '__main__':
    bind = os.environ.get('DOCFLOW_BIND', '127.0.0.1')
    if os.environ.get('DOCFLOW_DEV_UNSANDBOXED') == '1' and bind not in ['127.0.0.1', '::1']:
        raise SystemExit('Unsandboxed development mode is restricted to loopback')
    Server((bind, int(os.environ.get('PORT', '4173'))), Handler).serve_forever()
