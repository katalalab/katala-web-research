#!/usr/bin/env python3
"""Record unmodified Python Meta engine outputs into an owned ephemeral sideband."""
import json
import sys
import threading
from pathlib import Path
from unittest.mock import patch
from katala_web_research import cli, providers

requests=[];outputs={};lock=threading.Lock()
OriginalPool=providers.ThreadPoolExecutor
class RecordingPool(OriginalPool):
    def submit(self, callback, *args, **kwargs):
        index=len(requests)
        requests.append({"provider":args[0],"query":args[1],"limit":args[2]})
        def observed():
            results,run=callback(*args,**kwargs)
            raw=[result.to_dict() for result in results]
            for result in raw:
                for key in ["engine_health_score","engine_latency_ms","engine_result_count"]:result["metadata"].pop(key)
            with lock:outputs[str(index)]={"results":raw,"run":run.to_dict()}
            return results,run
        return super().submit(observed)

if __name__=="__main__":
    destination=Path(sys.argv[1]);code=0
    try:
        with patch.object(providers,"ThreadPoolExecutor",RecordingPool):
            if sys.argv[2:]==["--library"]:
                params=json.load(sys.stdin)
                print(json.dumps({"results":[r.to_dict() for r in providers.MetaSearch().search(params["query"],limit=params["limit"])]},ensure_ascii=False))
            else:code=cli.main(sys.argv[2:])
    finally:destination.write_text(json.dumps({"requests":requests,"outputs":outputs},ensure_ascii=False))
    raise SystemExit(code)
