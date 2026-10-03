"""Distribute the application, not a development repository or example database."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib,json,sqlite3
ROOT=Path(__file__).resolve().parent.parent
PORTABLE=ROOT/'artifacts/StageOS-Portable'
OUT=ROOT.parent/'StageOS-Release-1.0.0-rc.1.zip'
files=[(p,'StageOS/Windows-Portable/'+p.relative_to(PORTABLE).as_posix()) for p in sorted(PORTABLE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
for name in ['README_RU.md','RELEASE_AUDIT_RU.md','TEST_RESULTS.md','BUILD_RESULTS.md','THIRD_PARTY.md','release-test-results.txt','release-ui-results.txt','release-empty-ui-results.txt','release-static-results.txt','release-build-results.txt']:
 files.append((ROOT/name,'StageOS/'+name))
files.append((ROOT/'database/stageos-empty.db','StageOS/database/stageos-empty.db'))
manifest='\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+n for p,n in files)+'\n'
with ZipFile(OUT,'w',ZIP_DEFLATED,compresslevel=6) as z:
 for p,n in files:z.write(p,n)
 z.writestr('StageOS/MANIFEST.sha256',manifest)
with ZipFile(OUT) as z:
 assert z.testzip() is None
 assert not any(n.endswith(('seed.py','scenarios.py','stageos-demo.db')) for n in z.namelist())
 assert 'StageOS/Windows-Portable/StageOS.exe' in z.namelist()
with sqlite3.connect(ROOT/'database/stageos-empty.db') as db:
 assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
 counts={t:db.execute('select count(*) from '+t).fetchone()[0] for t in ['resources','productions','events','bookings','tasks','audit','settings']}
 assert not any(counts.values())
print(json.dumps(dict(archive=str(OUT),bytes=OUT.stat().st_size,files=len(files)+1,integrity='PASS',empty_database=counts,sha256=hashlib.sha256(OUT.read_bytes()).hexdigest()),indent=2))
