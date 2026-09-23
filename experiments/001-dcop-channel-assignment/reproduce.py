"""Verify published artifacts or compare an independently regenerated core demonstration."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parent
REPOSITORY=ROOT.parents[1]
# Fixed so the archive bytes depend only on its contents.
ARCHIVE_TIME=(2026,9,23,0,0,0)
ARCHIVED=('LICENSE','software/dcop_channel_assignment/*.py','software/dcop_channel_assignment/visualization.html',
          'tests/test_dcop*.py','data/geography/curitiba-metropolitan/*.geojson')
UNSEALED=('manifest.json',)
# The deferred comparative study is not part of this core evidence.
NOT_ARCHIVED=('tests/test_dcop_comparison.py',)

def archive():
    """Rebuild source.zip from the repository with LF line endings, whatever the checkout uses."""
    paths=sorted({p for pattern in ARCHIVED for p in REPOSITORY.glob(pattern)
                  if p.is_file() and p.relative_to(REPOSITORY).as_posix() not in NOT_ARCHIVED})
    with zipfile.ZipFile(ROOT/'source.zip','w',zipfile.ZIP_DEFLATED) as z:
        for path in paths:
            info=zipfile.ZipInfo(path.relative_to(REPOSITORY).as_posix(),ARCHIVE_TIME)
            info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,path.read_bytes().replace(b'\r\n',b'\n'))
    return len(paths)

def seal():
    files={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(ROOT.rglob('*')) if p.is_file() and p.relative_to(ROOT).as_posix() not in UNSEALED
           and not p.relative_to(ROOT).parts[0].startswith('reproduced-')}
    crlf=[name for name in files if b'\r\n' in (ROOT/name).read_bytes() and not name.endswith(('.gz','.zip'))]
    if crlf:
        raise SystemExit('CRLF line endings would not survive every checkout: '+', '.join(crlf))
    text=json.dumps({'format':'dcop-core-evidence-v1','files':files},indent=2,sort_keys=True)+'\n'
    (ROOT/'manifest.json').write_text(text,encoding='utf-8',newline='\n')
    return len(files)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--compare',type=Path)
    parser.add_argument('--seal',action='store_true',help='Maintainer step: rebuild source.zip and manifest.json')
    args=parser.parse_args()
    if args.seal:
        print(f'Archived {archive()} source files; sealed {seal()} files')
    if args.verify:
        manifest=json.loads((ROOT/'manifest.json').read_text())
        for relative,expected in manifest['files'].items():
            path=ROOT/relative
            if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise SystemExit('Hash mismatch: '+relative)
        print(f'Verified {len(manifest["files"])} recorded files')
    if args.compare:
        count=0
        for source in sorted((ROOT/'results').rglob('*')):
            if not source.is_file() or source.name=='host-timings.json':continue
            other=args.compare/source.relative_to(ROOT/'results')
            if source.read_bytes()!=other.read_bytes():
                raise SystemExit('Regeneration mismatch: '+str(source.relative_to(ROOT)))
            count+=1
        print(f'Reproduced {count} deterministic artifacts exactly; host timings excluded')

if __name__=='__main__':main()
