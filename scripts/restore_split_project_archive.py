"""Restore numbered 7z volumes into a new directory and verify embedded ZIPs."""
import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
import py7zr

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--parts-dir',type=Path,required=True);ap.add_argument('--prefix',required=True);ap.add_argument('--count',type=int,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    out=a.output.resolve();out.mkdir(exist_ok=False)
    ps=[a.parts_dir/(a.prefix+'.'+str(i).zfill(3)) for i in range(1,a.count+1)]
    assert all(p.is_file() for p in ps)
    manifest=dict(parts=[dict(name=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in ps])
    combined=out/'combined.7z'
    with combined.open('xb') as target:
        for p in ps:
            with p.open('rb') as f:shutil.copyfileobj(f,target)
    manifest['combined_7z']=dict(bytes=combined.stat().st_size,sha256=sha(combined))
    with py7zr.SevenZipFile(combined) as z:
        names=z.getnames();assert all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in names)
        z.extractall(out/'restored')
    manifest['restored_zips']=[]
    for p in (out/'restored').rglob('*.zip'):
        with zipfile.ZipFile(p) as z:assert z.testzip() is None
        manifest['restored_zips'].append(dict(path=str(p.relative_to(out)),bytes=p.stat().st_size,sha256=sha(p),zip_crc='pass'))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
