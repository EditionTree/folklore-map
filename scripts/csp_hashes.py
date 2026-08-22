"""Every inline <script> left on the site, with the CSP hash it needs.

A CSP hash covers the exact bytes between <script> and </script>. Anything not
covered stops executing the moment 'unsafe-inline' is removed, so this sweeps
every HTML file rather than the ones I happen to remember.
"""
import base64, glob, hashlib, io, os, re

files = [f for f in glob.glob('**/*.html', recursive=True)
         if not f.replace(os.sep, '/').startswith(('_drafts/', 'node_modules/', 'output/', 'tmp/'))]

blocks = {}
for f in files:
    s = io.open(f, encoding='utf-8').read()
    for attrs, body in re.findall(r'<script([^>]*)>(.*?)</script>', s, re.S):
        if ' src=' in attrs or 'ld+json' in attrs:
            continue
        blocks.setdefault(body, []).append(f)

print(f"  scanned {len(files)} HTML files")
print(f"  {len(blocks)} distinct inline script block(s) remain\n")

hashes = []
for body, where in sorted(blocks.items(), key=lambda kv: -len(kv[1])):
    h = 'sha256-' + base64.b64encode(hashlib.sha256(body.encode('utf-8')).digest()).decode()
    hashes.append(h)
    first = body.strip().split('\n')[0][:64]
    print(f"  x{len(where):<5} {len(body):>5} B  {h}")
    print(f"           {first}")
    if len(where) <= 3:
        print(f"           on: {', '.join(where)}")
    print()

print("  script-src additions:")
print('  ' + ' '.join(f"'{h}'" for h in hashes))
