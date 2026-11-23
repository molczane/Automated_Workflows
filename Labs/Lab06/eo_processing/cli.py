"""Command line entry point. All example commands fit on a single line."""
import argparse
import json
from pathlib import Path
import shutil
import sys
from . import __version__
from .common import file_hash, read_json, write_json
from . import database as db
from .planning import freeze, load_manifest, environment
from .runner import run, reconcile


def demo(workspace):
    workspace = Path(workspace).resolve()
    if workspace.exists():
        raise FileExistsError("Demo workspace already exists; run its batch.json or choose a new workspace")
    source = Path(__file__).parent/"data"/"fixtures"
    workspace.mkdir(parents=True)
    shutil.copytree(source,workspace/"inputs")
    database=workspace/"catalogue.sqlite"
    db.initialize(database)
    db.register_bundle(database,workspace/"inputs")
    manifest=read_json(workspace/"inputs"/"manifest.json")
    jobs=[]
    for m in manifest["members"]:
        e=next(iter(m["bands"].values()))
        jobs.append({"member_id":m["member_id"]+"-mndwi","item_id":m["item_file"][:-5],
                     "aoi_bbox":e["plan"]["aoi_bbox"],"product":"mndwi","parameters":{"threshold":0.0}})
    config={"database":"catalogue.sqlite","workspace":".","max_attempts":2,"jobs":jobs}
    write_json(workspace/"batch_config.json",config)
    return freeze(workspace/"batch_config.json",workspace/"batch.json")


def check_core():
    root=Path(__file__).parent
    path=root/"data"/"core_manifest.json"
    expected=read_json(path)
    changed=[name for name,sha in expected.items() if not (root/name).is_file() or file_hash(root/name)!=sha]
    actual={p.relative_to(root).as_posix() for p in root.rglob("*") if p.suffix in (".py",".sql")}
    changed+=sorted(actual-set(expected))
    return {"version":__version__,"identical_to_class_release":not changed,"changed_files":changed}


def main(argv=None):
    p=argparse.ArgumentParser(description="Automated Workflows optical processing, Version 1")
    p.add_argument("--version",action="version",version=__version__)
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor",help="Show runtime and shared core verification")
    sub.add_parser("check-core",help="Check that shared classroom code is unchanged")
    for name in ("init","inputs","integrity"):
        sp=sub.add_parser(name);sp.add_argument("--database",required=True)
    sp=sub.add_parser("migrate");sp.add_argument("--database",required=True);sp.add_argument("--destination",required=True)
    sp=sub.add_parser("demo");sp.add_argument("--workspace",required=True)
    sp=sub.add_parser("register");sp.add_argument("--database",required=True);sp.add_argument("--bundle",required=True)
    sp=sub.add_parser("search");sp.add_argument("--bbox",nargs=4,type=float,required=True);sp.add_argument("--interval",required=True);sp.add_argument("--max-items",type=int,default=20);sp.add_argument("--out",required=True)
    sp=sub.add_parser("acquire");sp.add_argument("--config",required=True);sp.add_argument("--destination",required=True)
    sp=sub.add_parser("plan");sp.add_argument("--config",required=True);sp.add_argument("--out",required=True)
    sp=sub.add_parser("run");sp.add_argument("--manifest",required=True);sp.add_argument("--retry-failed",action="store_true");sp.add_argument("--reason");sp.add_argument("--simulate",choices=("crash-before-publish","interrupt-before-publish"))
    sp=sub.add_parser("status");sp.add_argument("--manifest",required=True);sp.add_argument("--out")
    sp=sub.add_parser("assess");sp.add_argument("--manifest",required=True);sp.add_argument("--minimum-valid-fraction",type=float,default=0.5)
    sp=sub.add_parser("report");sp.add_argument("--manifest",required=True);sp.add_argument("--out",required=True)
    sp=sub.add_parser("reconcile");sp.add_argument("--manifest",required=True);sp.add_argument("--attempt",required=True);sp.add_argument("--reason",required=True)
    args=p.parse_args(argv)
    try:
        command=args.command
        code=0
        if command=="doctor":
            result={"environment":environment(),"core":check_core()}
        elif command=="check-core":
            result=check_core();code=0 if result["identical_to_class_release"] else 2
        elif command=="init":
            result={"database":db.initialize(args.database)}
        elif command=="migrate":
            result=db.migrate_copy(args.database,args.destination)
        elif command=="demo":
            result=demo(args.workspace)
        elif command=="register":
            result=db.register_bundle(args.database,args.bundle)
        elif command=="search":
            from .acquisition import search
            result=search(args.bbox,args.interval,args.max_items)
            write_json(args.out,result)
        elif command=="acquire":
            from .acquisition import acquire
            result=acquire(args.config,args.destination)
        elif command=="plan":
            result=freeze(args.config,args.out)
        elif command=="run":
            result=run(args.manifest,args.retry_failed,args.reason,args.simulate)
            code=0 if result["complete"] else 2
            result={**result,"members":[{**{k:r[k] for k in ("member_id","state","reason","attempts_used")},
                    "last_attempt":r["attempts"][-1] if r["attempts"] else None} for r in result["members"]]}
        elif command=="reconcile":
            result=reconcile(args.manifest,args.attempt,args.reason)
        elif command=="assess":
            from .qc import assess
            result=assess(args.manifest,args.minimum_valid_fraction)
        elif command in ("status","report"):
            from .reporting import status,report
            result=status(args.manifest) if command=="status" else report(args.manifest,args.out)
            if command=="status" and args.out:
                write_json(args.out,result)
                result={"saved":str(Path(args.out).resolve()),"counts":result["counts"]}
        elif command=="inputs":
            with db.connect(args.database,readonly=True) as c:
                result=[dict(r) for r in c.execute("SELECT artifact_id,json_extract(lineage_json,'$.item_id') AS item_id,json_extract(lineage_json,'$.asset_key') AS band,json_extract(lineage_json,'$.aoi.bbox') AS bbox FROM processing_artifacts WHERE source_artifact_id IS NOT NULL ORDER BY item_id,band")]
        elif command=="integrity":
            with db.connect(args.database,readonly=True) as c:
                result={"integrity":c.execute("PRAGMA integrity_check").fetchone()[0],"foreign_key_violations":[list(r) for r in c.execute("PRAGMA foreign_key_check")]}
        print(json.dumps(result,indent=2,allow_nan=False))
        return_code=code
    except Exception as exc:
        print(json.dumps({"status":"failed","error_type":type(exc).__name__,"error":str(exc)}),file=sys.stderr)
        return_code=1
    if return_code:
        raise SystemExit(return_code)


if __name__=="__main__":
    main()
