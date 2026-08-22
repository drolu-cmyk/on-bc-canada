#!/usr/bin/env python3
"""Reject internal planning vocabulary from public copy without banning ordinary English."""
from __future__ import annotations
import re, sys
from pathlib import Path
PUBLIC_FILES=[Path('README.md'),Path('PROGRAM_CHARTER.md'),Path('CAPABILITY_DOMAINS.md'),Path('CONTRIBUTING.md'),Path('compiler/README.md'),Path('runtime/README.md'),*sorted(Path('docs').glob('*.md')),*sorted(Path('site').glob('*.html')),*sorted(Path('policies').glob('*.yaml')),*sorted(Path('content/modules').glob('*.yaml'))]
BANNED={k:re.compile(v,re.I) for k,v in {
'advisory':r'\badvisory\b','draft':r'\bdraft\b','internal':r'\binternal\b','mvp':r'\bmvp\b','pending':r'\bpending\b','planned':r'\bplanned\b','planning':r'\bplanning\b','proposed':r'\bproposed\b','roadmap':r'\broadmap\b','todo':r'\btodo\b','tbd':r'\btbd\b'}.items()}
def main():
 errors=[]
 for path in PUBLIC_FILES:
  if not path.is_file(): errors.append(f'missing public file: {path}'); continue
  for n,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
   for label,pattern in BANNED.items():
    if pattern.search(line): errors.append(f"{path}:{n}: banned public-copy term '{label}'")
 if errors:
  print('Public-copy validation failed:',file=sys.stderr); print('\n'.join(errors),file=sys.stderr); return 1
 print(f'Public-copy validation passed for {len(PUBLIC_FILES)} files.'); return 0
if __name__=='__main__': raise SystemExit(main())
