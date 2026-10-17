"""Run in ArcGIS Pro Python: direct Esri checks and fresh GDB exports, never repair inputs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--void-gpkg',type=Path)
    p.add_argument('--national-gpkg',type=Path)
    p.add_argument('--comparison-gpkg',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--dry-run',action='store_true',help='Inspect input files and plan only; no ArcGIS run')
    a=p.parse_args()
    paths=[(label,path) for label,path in [('void',a.void_gpkg),('national',a.national_gpkg),('comparison',a.comparison_gpkg)] if path]
    if not paths:p.error('provide at least one input GPKG')
    if a.output.exists():p.error('output directory already exists')
    for _,path in paths:
        if not path.is_file():p.error('input missing: '+str(path))
    manifest=dict(dry_run=a.dry_run,geometry_repair=False,inputs=[dict(kind=k,name=v.name,sha256=digest(v)) for k,v in paths],jobs=[])
    if a.dry_run:
        a.output.mkdir(parents=True)
        manifest['executed']=False
        manifest['arcpy_available']=importlib.util.find_spec('arcpy') is not None
        (a.output/'plan.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return
    if importlib.util.find_spec('arcpy') is None:
        p.error('arcpy unavailable; run in the ArcGIS Pro Python environment; no checks executed')
    import arcpy
    arcpy.env.overwriteOutput=False
    a.output.mkdir(parents=True)
    out=a.output.resolve()
    target=str(out/'checks.gdb')
    arcpy.management.CreateFileGDB(str(out),'checks.gdb')
    manifest['arcgis_install_info']=arcpy.GetInstallInfo()

    def describe(path):
        desc=arcpy.Describe(path);sr=desc.spatialReference
        return dict(count=int(arcpy.management.GetCount(path)[0]),shape_type=desc.shapeType,
                    spatial_reference_name=sr.name,wkid=sr.factoryCode,
                    xy_resolution=sr.XYResolution,xy_tolerance=sr.XYTolerance)

    def check(path,name):
        table=str(Path(target)/name)
        rec=dict(method='ESRI',result_table=name)
        try:
            arcpy.management.CheckGeometry(path,table,'ESRI')
            names=[f.name for f in arcpy.ListFields(table) if f.type!='OID']
            rec['rows']=[dict(zip(names,row)) for row in arcpy.da.SearchCursor(table,names)]
            rec['row_count']=len(rec['rows']);rec['success']=True
        except Exception as e:
            rec['success']=False;rec['error']=str(e)
        rec['messages']=arcpy.GetMessages()
        return rec

    expected={'void':['void_candidates'],
        'national':['forest_plan_districts_provisional','forest_wide_basins_provisional','forest_unassigned_review'],
        'comparison':['district025_unchanged','district025_candidate']}
    try:
        for kind,gpkg in paths:
            with arcpy.EnvManager(workspace=str(gpkg.resolve())):
                available=arcpy.ListFeatureClasses() or []
            for index,wanted in enumerate(expected[kind]):
                matches=[x for x in available if x==wanted or x.rsplit('.',1)[-1]==wanted]
                if len(matches)!=1:
                    manifest['jobs'].append(dict(kind=kind,layer=wanted,executed=False,error='exact layer missing or ambiguous',available=available))
                    continue
                source=str(gpkg.resolve()/matches[0])
                name=kind+'_'+str(index+1)
                rec=dict(kind=kind,layer=wanted,input_metadata=describe(source),
                    direct_source_check=check(source,name+'_source_check'))
                destination=str(Path(target)/(name+'_export'))
                sr=arcpy.Describe(source).spatialReference
                try:
                    # Fixed documented settings for a controlled, fresh export.
                    with arcpy.EnvManager(outputCoordinateSystem=sr,
                            XYResolution='0.000000001 DecimalDegrees',
                            XYTolerance='0.000000008983152841195215 DecimalDegrees'):
                        arcpy.conversion.ExportFeatures(source,destination)
                    rec['export_metadata']=describe(destination)
                    rec['export_check']=check(destination,name+'_export_check')
                    if kind in ('void','comparison'):
                        fields=[f.name for f in arcpy.ListFields(destination) if f.type not in ('Geometry','Blob','Raster')]
                        features=[dict(attributes=dict(zip(fields,row[:-1])),geometry=json.loads(row[-1]))
                                  for row in arcpy.da.SearchCursor(destination,fields+['SHAPE@JSON'])]
                        reference=(features[0]['geometry'].get('spatialReference') if features else None) or {'wkid':sr.factoryCode}
                        payload=dict(geometryType='esriGeometryPolygon',spatialReference=reference,features=features)
                        (out/(name+'_export.json')).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                except Exception as e:
                    rec['export_success']=False;rec['export_error']=str(e);rec['export_messages']=arcpy.GetMessages()
                manifest['jobs'].append(rec)
                (out/'results.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    finally:
        manifest['inputs_unchanged']=all(digest(path)==record['sha256'] for (_,path),record in zip(paths,manifest['inputs']))
        manifest['executed']=True
        manifest['limits']='No repair. Error tables generally identify features, not problem coordinates. Successful runs are evidence only for these measured settings.'
        (out/'results.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')


if __name__=='__main__':main()
