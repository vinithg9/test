"""Synthetic capability probe; contains no user document or service credentials."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('app',root/'server/app.py');app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
with tempfile.TemporaryDirectory() as tmp:
    command=app.command_for(Path(tmp),'docx-to-pdf',True)
    # Keep the exact namespace and mounts; test only executable loading.
    end=command.index('--setenv')
    # command_for ends with renderer and its arguments; replace only those with version query.
    renderer=next(i for i,x in enumerate(command) if x.endswith('/soffice'))
    command=command[:renderer]+[command[renderer],'--version']
    result=subprocess.run(command,capture_output=True,text=True,timeout=15)
    print('Sandbox renderer probe exit:',result.returncode)
    print(result.stdout[:2000]);print(result.stderr[:2000])
    raise SystemExit(result.returncode)
