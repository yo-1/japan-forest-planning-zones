"""Compare forest releases without changing inputs or publishing artifacts."""
import argparse,collections,json,time
from pathlib import Path
import numpy as np
import shapely,pyproj
from shapely.geometry import Polygon
from .common import Audit,load,parts,area,holes,ring_area,exteriors,hole_signature,LAYERS,hashfile

def main():
    ap=argparse.ArgumentParser(description='Read-only audit of pinned v0.1/v0.2 forest GeoPackages')
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--municipalities',type=Path,required=True)
    for name in ['candidate-v01','candidate-v02','forest-v01','forest-v02']:
        ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False)
    audit=Audit(out);files=[];public={};candidate={};start=time.time()
    for version,tag in [('v0.1','v01'),('v0.2','v02')]:
        forest=getattr(a,'forest_'+tag).resolve();city=getattr(a,'candidate_'+tag).resolve()
        for p in [forest,city]:files.append(dict(path=str(p),sha256=hashfile(p),crs='EPSG:6668'))
        public[version]=load(forest)
        candidate[version]=load(city)['plane_rectangular_municipalities_2026']
    original=a.municipalities.resolve()
    orig=load(original)['plane_rectangular_municipalities_2026']
    files.append(dict(path=str(original),sha256=hashfile(original),crs='EPSG:6668'))
    orig_by={r['fid']:r for r in orig}
    for version,records in candidate.items():
        assert set(orig_by)=={r['fid'] for r in records}
        for r in records:
            audit.compare('municipality_original_to_'+version,r['fid'],orig_by[r['fid']]['geometry'],r['geometry'])
    one={r['fid']:r for r in candidate['v0.1']}
    assert set(one)=={r['fid'] for r in candidate['v0.2']}
    for r in candidate['v0.2']:
        assert r['N03_007']==one[r['fid']]['N03_007']
        audit.compare('municipality_v01_to_v02',r['fid'],one[r['fid']]['geometry'],r['geometry'])
    # Independent regrouping from published municipality attributes.
    for kind,field in [('district','forest_district_code'),('basin','wide_basin_code')]:
        table,key=LAYERS[kind]; groups=collections.defaultdict(list)
        for r in candidate['v0.1']:
            if r[field]:groups[r[field]].append(r['geometry'])
        targets={r[key]:r['geometry'] for r in public['v0.1'][table]}
        assert set(groups)==set(targets)
        for code,geoms in groups.items():
            expected=shapely.union_all(geoms)
            audit.compare('municipality_to_v01_'+kind,code,expected,targets[code])
        print('completed regroup',kind,round(time.time()-start),flush=True)
    overlap_results=[]; repairs=[]
    for kind,(table,key) in LAYERS.items():
        before={r[key]:r for r in public['v0.1'][table]};after={r[key]:r for r in public['v0.2'][table]}
        assert len(before)==len(public['v0.1'][table]) and set(before)==set(after)
        for code,b in before.items():
            a=after[code];g=b['geometry'];h=a['geometry']
            r=audit.compare('v01_to_v02_'+kind,code,g,h)
            hs0=hole_signature(g);hs1=hole_signature(h)
            repairs.append(dict(kind=kind,key=code,exterior_coordinate_bytes_unchanged=exteriors(g)==exteriors(h),holes_removed=sum((hs0-hs1).values()),holes_added=sum((hs1-hs0).values()),**{k:r[k] for k in ['lost_empty','added_empty','lost_m2','added_m2']}))
            for version,geom in [('v0.1',g),('v0.2',h)]:
                for index,p in enumerate(parts(geom)):
                    for hi,ring in enumerate(p.interiors):
                        hole=Polygon(ring);ellipsoid=area(hole);threshold=ring_area(ring)
                        audit.hole_rows.append(dict(version=version,kind=kind,key=code,part=index,hole=hi,ellipsoidal_m2=ellipsoid,release_metric_m2=threshold,below_1m2_release_metric=threshold<1))
                        if version=='v0.2' and kind!='unassigned':
                            audit.feature(hole,dict(stage='retained_hole_'+kind,key=str(code),direction='retained_hole',area_m2=ellipsoid))
        if kind!='unassigned':
            for version in ['v0.1','v0.2']:
                overlap_results.append(audit.overlaps(version+'_'+kind+'_overlaps',public[version][table],key))
                unknown=public[version][LAYERS['unassigned'][0]]
                for r in public[version][table]:
                    for u in unknown:
                        if not shapely.box(*r['geometry'].bounds).intersects(shapely.box(*u['geometry'].bounds)):continue
                        x=r['geometry'].intersection(u['geometry'])
                        if list(parts(x)):
                            audit.feature(x,dict(stage=version+'_'+kind+'_unassigned_intrusion',key=str(r[key])+'/'+str(u['municipality_code']),direction='intrusion',area_m2=area(x)))
        print('completed repairs and intersections',kind,round(time.time()-start),flush=True)
    # Corrected district aggregates must agree with corrected basin per basin code.
    groups=collections.defaultdict(list)
    for r in public['v0.2'][LAYERS['district'][0]]:groups[r['basin_code']].append(r['geometry'])
    targets={r['basin_code']:r['geometry'] for r in public['v0.2'][LAYERS['basin'][0]]}
    assert set(groups)==set(targets)
    for code,geoms in groups.items():
        audit.compare('v02_districts_to_basin',code,shapely.union_all(geoms),targets[code])
        print('corrected consistency',code,round(time.time()-start),flush=True)
    stages={}
    for r in audit.rows:
        s=stages.setdefault(r['stage'],dict(count=0,exact_empty=0,nonempty=0,lost_m2=0.,added_m2=0.))
        s['count']+=1;s['exact_empty']+=int(r['lost_empty'] and r['added_empty']);s['nonempty']+=int(not(r['lost_empty'] and r['added_empty']))
        s['lost_m2']+=r['lost_m2'];s['added_m2']+=r['added_m2']
    summary=dict(crs='EPSG:6668 (JGD2011 longitude/latitude)',tolerance=dict(coordinate=0,area_pass_threshold=None,policy='Nonempty differences remain reported, even at numerical scale; no snapping or repair'),area_metric='GRS80 ellipsoidal area; holes also measured with release spherical cylindrical equal-area metric R=6371008.8',versions=dict(shapely=shapely.__version__,geos=shapely.geos_version_string,pyproj=pyproj.__version__,numpy=np.__version__),inputs=files,stages=stages,overlaps=overlap_results,repairs=repairs,holes={v:{k:dict(count=len(rs:=[r for r in audit.hole_rows if r['version']==v and r['kind']==k]),below_1m2=sum(r['below_1m2_release_metric'] for r in rs),ellipsoidal_area_m2=sum(r['ellipsoidal_m2'] for r in rs)) for k in LAYERS} for v in ['v0.1','v0.2']},unassigned_intrusions=[p for g,p in audit.features if p['direction']=='intrusion'],elapsed_seconds=time.time()-start)
    audit.write(summary,original)
    print(json.dumps({k:v for k,v in summary.items() if k not in ['inputs','repairs']},ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
