"""Bounded, expiring public filing parse cache. Never stores SEC clients/contact."""
from dataclasses import asdict
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time

from .models import Fact

PARSER_VERSION = "v07-1"


class ParsedFilingCache:
    def __init__(self, directory: Path, *, max_bytes=64*1024*1024,
                 ttl_seconds=7*86400, clock=time.time):
        self.directory=Path(directory)
        self.max_bytes=max_bytes
        self.ttl_seconds=ttl_seconds
        self.clock=clock

    @staticmethod
    def key(document, filing, mappings=()):
        metadata=json.dumps([PARSER_VERSION,asdict(filing),[asdict(m) for m in mappings]],sort_keys=True).encode()
        return hashlib.sha256(hashlib.sha256(document).digest()+metadata).hexdigest()

    def get(self, key):
        path=self.directory/(key+".json")
        try:
            stat=path.stat()
            if self.clock()-stat.st_mtime>=self.ttl_seconds or stat.st_size>min(self.max_bytes,16*1024*1024):
                return None
            payload=json.loads(path.read_bytes())
            if not isinstance(payload,list) or len(payload)!=2:
                return None
            groups=[]
            for entries in payload:
                facts=[]
                for record in entries:
                    record["dimensions"]=tuple(tuple(d) for d in record.get("dimensions",()))
                    f=Fact(**record)
                    if isinstance(f.value,bool) or not isinstance(f.value,(int,float)) or not math.isfinite(f.value):
                        return None
                    date.fromisoformat(f.end)
                    if f.start:
                        date.fromisoformat(f.start)
                    if f.presentation_value is not None and (isinstance(f.presentation_value,bool)
                            or not isinstance(f.presentation_value,(int,float)) or not math.isfinite(f.presentation_value)):
                        return None
                    if any(len(pair)!=2 or not all(isinstance(v,str) for v in pair) for pair in f.dimensions):
                        return None
                    facts.append(f)
                groups.append(facts)
            return tuple(groups)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return None

    def put(self, key, facts, disclosures):
        data=json.dumps([[asdict(f) for f in facts],[asdict(f) for f in disclosures]],allow_nan=False).encode()
        if len(data)>min(self.max_bytes,16*1024*1024):
            return
        temporary=None
        try:
            self.directory.mkdir(parents=True,exist_ok=True)
            target=self.directory/(key+".json")
            temporary=target.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            temporary.write_bytes(data)
            temporary.replace(target)
            os.utime(target,(self.clock(),self.clock()))
            entries=[]
            for path in self.directory.glob("*.json"):
                try:
                    stat=path.stat()
                    if self.clock()-stat.st_mtime>=self.ttl_seconds:
                        path.unlink(missing_ok=True)
                    else:
                        entries.append((stat.st_mtime,stat.st_size,path))
                except OSError:
                    continue
            total=sum(size for _,size,_ in entries)
            for _,size,path in sorted(entries):
                if total<=self.max_bytes:
                    break
                path.unlink(missing_ok=True)
                total-=size
        except OSError:
            pass  # A full/unwritable cache must never block financial retrieval.
        finally:
            if temporary:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
