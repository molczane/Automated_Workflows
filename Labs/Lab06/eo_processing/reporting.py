"""A portable HTML/JSON report from verified catalogue evidence."""
import base64
import html
import io
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from . import database as db
from .common import now, write_json
from .planning import load_manifest
from .runner import inspect_member


def preview(paths, product_name):
    roles = [r for r in ("index","water","valid_mask") if r in paths]
    roles += [r for r in paths if r not in roles]
    fig, axes = plt.subplots(1,len(roles),figsize=(4*len(roles),3.6),squeeze=False)
    for ax, role in zip(axes[0], roles):
        with rasterio.open(paths[role]) as src:
            data = src.read(1,masked=True)
            extent = [src.bounds.left/1000,src.bounds.right/1000,src.bounds.bottom/1000,src.bounds.top/1000]
        cmap = "BrBG" if role == "index" else "Blues" if role == "water" else "Greens"
        cmap = plt.get_cmap(cmap).copy()
        cmap.set_bad("#d9d9d9")
        if role in ("water", "valid_mask"):
            lower, upper = 0, 1
        elif role == "index" and product_name in ("mndwi", "ndvi", "ndmi", "ndsi", "nbr"):
            lower, upper = -1, 1
        else:
            values = data.compressed()
            lower = float(values.min()) if values.size else 0
            upper = float(values.max()) if values.size else 1
            if upper == lower:
                upper = lower + 1
        image = ax.imshow(data,extent=extent,cmap=cmap,vmin=lower,vmax=upper,interpolation="nearest")
        ax.set_title(product_name.upper() if role=="index" else role.replace("_"," "))
        ax.set_xlabel("Easting (km)")
        ax.set_ylabel("Northing (km)")
        ax.ticklabel_format(useOffset=False, style="plain")
        fig.colorbar(image,ax=ax,shrink=0.8)
    fig.tight_layout()
    stream=io.BytesIO()
    fig.savefig(stream,format="png",dpi=110)
    plt.close(fig)
    return base64.b64encode(stream.getvalue()).decode()


def status(manifest_path):
    manifest = load_manifest(manifest_path)
    rows=[]
    with db.connect(manifest["runtime"]["database"],readonly=True) as c:
        for member in manifest["frozen"]["members"]:
            row = inspect_member(c,member,manifest["frozen"]["max_attempts"])
            row["product"] = member["spec"]["product"]["name"]
            row["grid"] = member["spec"]["grid"]
            if row["result"]:
                q = c.execute("SELECT * FROM latest_scientific_qc WHERE attempt_id=?",(row["result"]["attempt_id"],)).fetchone()
                row["qc"] = dict(q) if q else None
            else:
                row["qc"] = None
            rows.append(row)
    return {"batch_id":manifest["batch_id"],"generated_at":now(),"members":rows,
            "counts":{state:sum(r["state"]==state for r in rows) for state in ("ready","complete","blocked","unresolved","failed")}}


def report(manifest_path, directory):
    snapshot=status(manifest_path)
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    write_json(directory/"report.json",snapshot)
    esc=lambda x:html.escape(str(x))
    cards=[]
    for row in snapshot["members"]:
        result=row["result"]
        qc=row["qc"]
        body=f"<h2>{esc(row['member_id'])}</h2><p>Execution / availability: {esc(row['state'])}. {esc(row['reason'])}</p>"
        body+=f"<p>Product: {esc(row['product'])}. Scientific QC: {esc(qc['outcome'] if qc else 'not assessed')}.</p>"
        if qc:
            body+=f"<p>{esc(qc['reason'])} Assessment {qc['assessment_id']}, {esc(qc['assessed_at'])}.</p>"
        if result:
            metrics=result["receipt"]["metrics"]
            body+=f"<p>Raw coverage: {metrics['raw_valid_fraction']:.1%}. Usable coverage: {metrics['valid_fraction']:.1%} of {metrics['aoi_pixels']} AOI pixels.</p>"
            product_metrics=metrics["product_metrics"]
            if "candidate_water_area_m2" in product_metrics:
                body+=f"<p>Candidate water: {product_metrics['candidate_water_area_m2']/1e6:.4f} km² within {product_metrics['observed_area_m2']/1e6:.4f} km² observed. Unknown pixels contribute to neither class.</p>"
            body+=f"<img alt='Product and validity maps' src='data:image/png;base64,{preview(result['paths'],row['product'])}'>"
            body+=f"<details><summary>Producing attempt, outputs and measured QC</summary><pre>{esc(json.dumps(result,indent=2))}</pre></details>"
        body+=f"<details><summary>Request, grid and attempt history</summary><pre>{esc(json.dumps({k:v for k,v in row.items() if k not in ('result',)},indent=2))}</pre></details>"
        cards.append("<article>"+body+"</article>")
    document="""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Lab 06 processing report</title><style>body{font:16px/1.55 system-ui,sans-serif;background:#edf2f5;color:#173042;max-width:1200px;margin:30px auto;padding:0 20px}h1{font-size:32px}h2{font-size:22px}article{background:white;padding:24px;margin:22px 0;border-radius:12px;border:1px solid #d4e0e6}img{width:100%;height:auto}pre{overflow:auto;font-size:12px;background:#f3f6f8;padding:14px}summary{cursor:pointer}p{max-width:100ch}.intro{color:#405e70}</style>"""
    document+=f"<h1>Optical processing · Version 1</h1><p class='intro'>Verified {esc(snapshot['generated_at'])}. {len(snapshot['members'])} expected requests. This is a saved report; run report again to refresh file evidence.</p>"
    document+="<p class='intro'>Gray areas on maps are unknown observations or outside the AOI. On the valid mask, 0 means an AOI pixel is unusable and 1 means usable. Automatic QC acceptance means the recorded checks passed. It does not establish classification accuracy. Water extent comparisons require common valid coverage.</p>"
    document+="".join(cards)+"</html>"
    (directory/"index.html").write_text(document,encoding="utf-8")
    return {"html":str(directory/"index.html"),"json":str(directory/"report.json"),"counts":snapshot["counts"]}
