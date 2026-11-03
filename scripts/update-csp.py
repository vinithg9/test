from pathlib import Path
import base64, hashlib, re
p=Path(__file__).resolve().parent.parent/'docflow-single-file.html'
s=re.sub(r'<meta http-equiv="Content-Security-Policy" content="[^"]*">','',p.read_text())
hashes=["'sha256-"+base64.b64encode(hashlib.sha256(m[1].encode()).digest()).decode()+"'" for m in re.finditer(r'<script(?: type="module")?>([\s\S]*?)</script>',s)]
csp="default-src 'none'; script-src "+' '.join(hashes)+" https://cdn.jsdelivr.net https://cdn.sheetjs.com; style-src 'unsafe-inline'; img-src data: blob:; connect-src 'self' https://cdn.jsdelivr.net https://cdn.sheetjs.com; worker-src blob: https://cdn.jsdelivr.net; base-uri 'none'; object-src 'none'; form-action 'none'"
s=s.replace('<meta name="referrer"','<meta http-equiv="Content-Security-Policy" content="'+csp+'"><meta name="referrer"')
p.write_text(s)
