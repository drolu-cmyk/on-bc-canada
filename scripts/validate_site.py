#!/usr/bin/env python3
"""Validate SozoRock Canada public pages, clean routes, forms and protected admin shell."""
from __future__ import annotations
import re,sys
from pathlib import Path
SITE=Path('site'); ORIGIN='https://canada.sozorock.com'
PAGES={'index.html':'/','about.html':'/about','programs.html':'/programs','applied-ai.html':'/applied-ai','cybersecurity-grc.html':'/cybersecurity-grc','ai-governance.html':'/ai-governance','cloud.html':'/cloud','curriculum.html':'/curriculum','where-we-work.html':'/where-we-work','impact.html':'/impact','insights.html':'/insights','insight-ai-judgement.html':'/insight-ai-judgement','contact.html':'/contact','register-interest.html':'/register-interest','partnerships.html':'/partnerships','media.html':'/media','enquiry.html':'/enquiry','accessibility.html':'/accessibility','support.html':'/support','privacy.html':'/privacy','terms.html':'/terms'}
FORM_PAGES={'register-interest.html','partnerships.html','media.html','enquiry.html'}; SPECIAL={'404.html','admin.html'}; ROUTES={v:k for k,v in PAGES.items()}
def exists(target):
 clean=target.split('#',1)[0].split('?',1)[0]
 if clean in ('','/'): return (SITE/'index.html').is_file()
 if clean.startswith('/') and clean in ROUTES:return (SITE/ROUTES[clean]).is_file()
 return (SITE/clean.lstrip('/')).is_file()
def main():
 errors=[]; files={p.name for p in SITE.glob('*.html')}; required=set(PAGES)|SPECIAL
 errors += [f'missing page: site/{x}' for x in sorted(required-files)]
 for retired in ('program.html','stories.html','enroll.html'):
  if (SITE/retired).exists():errors.append(f'site/{retired} must be retired')
 for path in sorted(SITE.glob('*.html')):
  s=path.read_text(encoding='utf-8')
  if path.name=='admin.html':
   if '<meta name="robots" content="noindex,nofollow">' not in s:errors.append('site/admin.html must be noindex,nofollow')
   if '<form' in s.lower():errors.append('site/admin.html must use Cognito sign-in, not a local credential form')
   continue
  for req in ('<html lang="en-CA">','<meta name="viewport"','<meta name="description"','<title>','id="main"','href="#main"'):
   if req not in s:errors.append(f'{path}: missing {req}')
  if s.count('<h1')!=1:errors.append(f'{path}: requires exactly one h1')
  has_form='<form' in s.lower()
  if has_form and path.name not in FORM_PAGES:errors.append(f'{path}: public form is not approved on this route')
  if path.name in FORM_PAGES and not has_form:errors.append(f'{path}: expected engagement form')
  fragments=[x for x in re.findall(r'href="([^"]+)"',s) if '#' in x and x!='#main']
  if fragments:errors.append(f"{path}: fragment URLs are not allowed: {', '.join(fragments)}")
  if path.name in PAGES:
   url=ORIGIN+PAGES[path.name]
   for req in (f'<link rel="canonical" href="{url}">',f'<meta property="og:url" content="{url}">','<meta name="twitter:card" content="summary">'):
    if req not in s:errors.append(f'{path}: missing {req}')
  elif path.name=='404.html':
   if '<meta name="robots" content="noindex">' not in s:errors.append('site/404.html must be noindex')
  for target in re.findall(r'(?:href|src)="([^"]+)"',s):
   if target.startswith(('http:','https:','#','mailto:','tel:')):continue
   if not exists(target):errors.append(f'{path}: missing local target {target}')
 for asset in ('reference-home.css','site.js','forms.js','admin.js','engagement-config.js','favicon.svg','robots.txt','sitemap.xml'):
  if not (SITE/asset).is_file():errors.append(f'site/{asset} is missing')
 sm=(SITE/'sitemap.xml').read_text(encoding='utf-8') if (SITE/'sitemap.xml').is_file() else ''
 for route in PAGES.values():
  if f'<loc>{ORIGIN}{route}</loc>' not in sm:errors.append(f'sitemap missing {ORIGIN}{route}')
 for forbidden in ('/admin</loc>','/stories</loc>','/enroll</loc>','.html</loc>'):
  if forbidden in sm:errors.append(f'sitemap contains forbidden entry {forbidden}')
 if errors:
  print('Static site validation failed:',file=sys.stderr);print('\n'.join(errors),file=sys.stderr);return 1
 print(f'Static site validation passed for {len(files)} HTML files.');return 0
if __name__=='__main__':raise SystemExit(main())
