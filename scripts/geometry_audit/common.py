"""Read-only geometry audit helpers; EPSG:6668, no snapping or repair."""
import argparse
import collections
import csv
import hashlib
import json
import sqlite3
import struct
import time
import zipfile
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import Polygon, mapping
from shapely.ops import orient
import pyproj

GEOD = pyproj.Geod(ellps='GRS80')
LAYERS = {'district': ('forest_plan_districts_provisional', 'district_code'),
          'basin': ('forest_wide_basins_provisional', 'basin_code'),
          'unassigned': ('forest_unassigned_review', 'municipality_code')}

def hashfile(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def parts(g):
    if g.geom_type == 'Polygon':
        yield g
    elif hasattr(g, 'geoms'):
        for p in g.geoms:
            yield from parts(p)

def area(g):
    return sum(abs(GEOD.geometry_area_perimeter(orient(p, 1))[0]) for p in parts(g))

def holes(g):
    return [Polygon(r) for p in parts(g) for r in p.interiors]

def ring_area(r):
    # Release threshold metric; keep distinct from ellipsoidal reporting metric.
    a = np.asarray(r.coords)
    lam = np.radians(a[:, 0]); s = np.sin(np.radians(a[:, 1]))
    return float(abs(.5 * 6371008.8**2 * np.sum(np.diff(lam) * (s[:-1] + s[1:]))))

def exteriors(g):
    return sorted(hashlib.sha256(np.asarray(p.exterior.coords, dtype='<f8').tobytes()).hexdigest() for p in parts(g))

def hole_signature(g):
    return collections.Counter(hashlib.sha256(shapely.to_wkb(shapely.normalize(h))).hexdigest() for h in holes(g))

def decode(b):
    order = '<' if b[3] & 1 else '>'
    srid = struct.unpack(order + 'i', b[4:8])[0]
    off = 8 + {0:0,1:32,2:48,3:48,4:64}[(b[3] >> 1) & 7]
    return srid, shapely.from_wkb(b[off:])

def load(p):
    db = sqlite3.connect(p.resolve().as_uri() + '?mode=ro', uri=True)
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    result = {}
    for table, col, srid in db.execute('SELECT table_name,column_name,srs_id FROM gpkg_geometry_columns'):
        assert srid == 6668, (p, table, srid)
        cursor = db.execute(f'SELECT * FROM "{table}"')
        names = [x[0] for x in cursor.description]
        rows = []
        for vals in cursor:
            row = dict(zip(names, vals)); b = row.pop(col)
            actual, g = decode(b)
            assert actual == srid and g.is_valid and not g.is_empty, (p, table, row.get('fid'))
            row['geometry'] = g; rows.append(row)
        result[table] = rows
    db.close()
    return result

class Audit:
    def __init__(self, out):
        self.out = out; self.rows = []; self.features = []; self.hole_rows = []

    def feature(self, g, props):
        # Include line/point differences too; these may have zero area.
        if not g.is_empty: self.features.append((g, props))

    def compare(self, stage, key, expected, actual, force_overlay=False):
        exact = bool(shapely.equals_exact(expected, actual, 0, normalize=True))
        lost = shapely.GeometryCollection() if exact and not force_overlay else expected.difference(actual)
        added = shapely.GeometryCollection() if exact and not force_overlay else actual.difference(expected)
        row = dict(stage=stage, key=str(key), normalized_exact=exact,
                   lost_empty=bool(lost.is_empty), added_empty=bool(added.is_empty),
                   lost_m2=area(lost), added_m2=area(added),
                   expected_holes=len(holes(expected)), actual_holes=len(holes(actual)))
        self.rows.append(row)
        for direction, g in [('lost',lost), ('added',added)]:
            self.feature(g, dict(stage=stage,key=str(key),direction=direction,area_m2=area(g)))
        return row

    def overlaps(self, stage, records, key):
        geoms = [r['geometry'] for r in records]; tree = shapely.STRtree(geoms)
        count = 0; total = 0.; nonempty = 0
        for i,g in enumerate(geoms):
            for j in tree.query(g):
                j = int(j)
                if j <= i: continue
                x = g.intersection(geoms[j])
                if x.is_empty: continue
                if not list(parts(x)): continue # shared boundary is not overlap
                nonempty += 1; a = area(x)
                if a > 0: count += 1; total += a
                self.feature(x,dict(stage=stage,key=str(records[i][key])+'/'+str(records[j][key]),direction='overlap',area_m2=a))
            if (i+1)%25==0: print('overlap progress',stage,i+1,len(geoms),flush=True)
        return dict(stage=stage, polygon_intersection_pairs=nonempty, positive_area_pairs=count, pairwise_area_m2=total)

    def write(self, summary, template=None):
        for name, rows in [('comparison',self.rows), ('holes',self.hole_rows)]:
            (self.out/(name+'.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
            keys = sorted(set().union(*(r.keys() for r in rows)))
            with (self.out/(name+'.csv')).open('w',newline='',encoding='utf-8') as f:
                w=csv.DictWriter(f,fieldnames=keys,lineterminator="\n");w.writeheader();w.writerows(rows)
        (self.out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        features=[dict(type='Feature',geometry=mapping(g),properties=p) for g,p in self.features]
        (self.out/'differences.geojson').write_text(json.dumps(dict(type='FeatureCollection',features=features),ensure_ascii=False)+'\n')
        path=self.out/'differences.gpkg';db=sqlite3.connect(path)
        db.execute('PRAGMA application_id=1196444487');db.execute('PRAGMA user_version=10300')
        if template is not None:
            src=sqlite3.connect(template.resolve().as_uri()+'?mode=ro',uri=True)
            for n in ['gpkg_spatial_ref_sys','gpkg_contents','gpkg_geometry_columns']:
                db.execute(src.execute('SELECT sql FROM sqlite_master WHERE name=?',(n,)).fetchone()[0])
            db.executemany('INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)',src.execute('SELECT * FROM gpkg_spatial_ref_sys').fetchall())
            src.close()
        else:
            db.execute('CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT NOT NULL,srs_id INTEGER NOT NULL PRIMARY KEY,organization TEXT NOT NULL,organization_coordsys_id INTEGER NOT NULL,definition TEXT NOT NULL,description TEXT)')
            db.execute('CREATE TABLE gpkg_contents (table_name TEXT NOT NULL PRIMARY KEY,data_type TEXT NOT NULL,identifier TEXT UNIQUE,description TEXT DEFAULT "",last_change DATETIME NOT NULL,min_x DOUBLE,min_y DOUBLE,max_x DOUBLE,max_y DOUBLE,srs_id INTEGER REFERENCES gpkg_spatial_ref_sys(srs_id))')
            db.execute('CREATE TABLE gpkg_geometry_columns (table_name TEXT NOT NULL,column_name TEXT NOT NULL,geometry_type_name TEXT NOT NULL,srs_id INTEGER NOT NULL,z INTEGER NOT NULL,m INTEGER NOT NULL,PRIMARY KEY(table_name,column_name),FOREIGN KEY(table_name) REFERENCES gpkg_contents(table_name),FOREIGN KEY(srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id))')
            db.executemany('INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)',[
                ('Undefined Cartesian',-1,'NONE',-1,'undefined',''),
                ('Undefined geographic',0,'NONE',0,'undefined',''),
                ('JGD2011',6668,'EPSG',6668,pyproj.CRS.from_epsg(6668).to_wkt(version='WKT1_GDAL'),'')])
        db.execute('CREATE TABLE differences(fid INTEGER PRIMARY KEY,geom BLOB,stage TEXT,key TEXT,direction TEXT,area_m2 REAL)')
        bounds=shapely.total_bounds([g for g,p in self.features]) if self.features else [None]*4
        db.execute('INSERT INTO gpkg_contents(table_name,data_type,identifier,description,last_change,min_x,min_y,max_x,max_y,srs_id) VALUES (?,?,?,?,?,?,?,?,?,?)',('differences','features','differences','Read-only audit differences; no repair',time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),*bounds,6668))
        db.execute('INSERT INTO gpkg_geometry_columns VALUES (?,?,?,?,?,?)',('differences','geom','GEOMETRY',6668,0,0))
        for g,p in self.features:
            blob=b'GP\x00\x01'+struct.pack('<i',6668)+shapely.to_wkb(g,byte_order=1)
            db.execute('INSERT INTO differences VALUES(NULL,?,?,?,?,?)',(blob,p['stage'],p['key'],p['direction'],p['area_m2']))
        db.commit();assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.close()
