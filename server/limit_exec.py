"""Apply per-render limits before exec; avoids preexec_fn in a threaded server."""
import os
import resource
import sys
os.umask(0o077)
resource.setrlimit(resource.RLIMIT_CPU, (90,90))
resource.setrlimit(resource.RLIMIT_FSIZE, (100*1024*1024,100*1024*1024))
resource.setrlimit(resource.RLIMIT_NOFILE, (256,256))
resource.setrlimit(resource.RLIMIT_CORE, (0,0))
resource.setrlimit(resource.RLIMIT_AS, (2*1024**3,2*1024**3))
os.execv(sys.argv[1], sys.argv[1:])
