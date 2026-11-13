"""Read-only, bounded live metadata checks. No cookies or access-control workarounds.
Run: python probe_platforms.py URL [URL ...]
Optional: --output /data/platform-tests.json
"""
import argparse
import concurrent.futures
import json
import subprocess
import sys
from datetime import datetime,timezone
from importlib.metadata import version

CODE='''
import json,sys
from app import extractor
from app.urls import normalize
from app.errors import classify
try:
    url,platform=normalize(sys.argv[1])
    job={'url':url,'platform':platform,'mode':'video','options':{},'entry_index':None}
    info=extractor.extract(job)
    if extractor.is_collection(info):
        entries=extractor.entries(info,20)
        result={'status':'metadata_ok','entries':len(entries),'title':info.get('title')}
    else:
        extractor.verify_media(info,'video')
        meta=extractor.metadata(info);meta.pop('thumbnail',None)
        result={'status':'metadata_ok','metadata':meta}
except Exception as e:
    code,message,retryable=classify(e)
    result={'status':'failed','error_code':code,'message':message}
print(json.dumps(result,ensure_ascii=False))
'''

def probe(item):
    platform,url=item
    try:
        r=subprocess.run([sys.executable,'-c',CODE,url],capture_output=True,text=True,timeout=75)
        result=json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode==0 else {'status':'process_failed'}
    except subprocess.TimeoutExpired: result={'status':'failed','error_code':'PROBE_TIMEOUT','message':'75초 내 완료되지 않아 검증을 중단했습니다.'}
    return {'platform':platform,'url':url,**result,'download_test':'not_attempted_metadata_only'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Check metadata only for URLs you are authorized to access.');parser.add_argument('urls', nargs='+');parser.add_argument('--output');args=parser.parse_args()
    from app.urls import normalize
    samples=[(normalize(url)[1],url) for url in args.urls]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        results=list(executor.map(probe,samples))
    from yt_dlp.extractor import gen_extractor_classes
    threads=[c.IE_NAME for c in gen_extractor_classes() if 'threads' in c.IE_NAME.lower()]
    results.append({'platform':'threads','status':'extractor_unavailable' if not threads else 'untested','extractors':threads,'download_test':'not_attempted'})
    report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'yt_dlp':version('yt-dlp'),'tests':results}
    output=json.dumps(report,ensure_ascii=False,indent=2)
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(output+'\n')
    print(output)
