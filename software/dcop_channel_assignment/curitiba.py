"""Rebuild Curitiba map inputs from a locally retained IBGE source snapshot."""

import argparse
import hashlib
import html
import json
from pathlib import Path
import unicodedata
import gzip
import urllib.request
from datetime import datetime, timezone

from shapely.geometry import shape

from .geography import from_geojson
from .translation import to_dcop


METRO = 'Curitiba|Adrianopolis|Agudos do Sul|Almirante Tamandare|Araucaria|Balsa Nova|Bocaiuva do Sul|Campina Grande do Sul|Campo do Tenente|Campo Largo|Campo Magro|Cerro Azul|Colombo|Contenda|Doutor Ulysses|Fazenda Rio Grande|Itaperucu|Lapa|Mandirituba|Pien|Pinhais|Piraquara|Quatro Barras|Rio Branco do Sul|Rio Negro|Sao Jose dos Pinhais|Quitandinha|Tijucas do Sul|Tunas do Parana'.split('|')
CORE = 'Almirante Tamandare|Araucaria|Campina Grande do Sul|Campo Largo|Campo Magro|Colombo|Curitiba|Fazenda Rio Grande|Itaperucu|Pinhais|Piraquara|Quatro Barras|Rio Branco do Sul|Sao Jose dos Pinhais'.split('|')

SOURCES = {
    'parana-source.geojson': 'https://servicodados.ibge.gov.br/api/v3/malhas/estados/41?formato=application/vnd.geo%2Bjson&qualidade=maxima&intrarregiao=municipio&periodo=2022',
    'municipalities-source.json': 'https://servicodados.ibge.gov.br/api/v1/localidades/estados/41/municipios',
}


def download(directory):
    directory.mkdir(parents=True,exist_ok=True)
    if any((directory/name).exists() for name in SOURCES):
        raise ValueError('Download requires a fresh directory; preserve existing source snapshots')
    for name,url in SOURCES.items():
        payload = urllib.request.urlopen(url,timeout=60).read()
        if payload[:2] == b'\x1f\x8b':
            payload = gzip.decompress(payload)
        json.loads(payload)
        (directory/name).write_bytes(payload)
    record_sources(directory)


def record_sources(directory):
    dump(directory/'provenance.json', {
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'boundary_reference_period':2022,
        'membership_source':'https://www.amep.pr.gov.br/FAQ/Municipios-da-Regiao-Metropolitana-de-Curitiba',
        'membership_checked_on':'2026-09-23',
        'crs_note':'IBGE geographic longitude/latitude; retained without reprojection',
        'transformations':['gzip decompression where needed','select AMEP municipality membership by IBGE name and code','retain geometry unchanged','derive positive-length boundary intersections without snapping'],
        'sources':{name:{'url':url,'sha256':hashlib.sha256((directory/name).read_bytes()).hexdigest()}
                   for name,url in SOURCES.items()},
        'software':{'shapely':'2.1.2','networkx':'3.4.2'},
        'rights_note':'Public IBGE geographic data, attributed to IBGE; not relicensed as repository software. No separate license identifier supplied by API response.',
    })


def normalized(name):
    return ''.join(c for c in unicodedata.normalize('NFD', name) if not unicodedata.combining(c))


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')


def render(document, path, dark=False):
    """Geographic preview only: highlight Curitiba, never imply solved channels."""
    geometries = [shape(f['geometry']) for f in document['features']]
    x0 = min(g.bounds[0] for g in geometries)
    y0 = min(g.bounds[1] for g in geometries)
    x1 = max(g.bounds[2] for g in geometries)
    y1 = max(g.bounds[3] for g in geometries)
    scale = min(850 / ((x1-x0)*0.91), 680 / (y1-y0))
    def point(x, y):
        return f'{65+(x-x0)*scale*0.91:.2f},{100+(y1-y)*scale:.2f}'
    background, foreground = ('#101827', '#e5e7eb') if dark else ('#ffffff', '#172033')
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 850"><rect width="1000" height="850" fill="{background}"/>',
             f'<g font-family="sans-serif" fill="{foreground}"><text x="35" y="35" font-size="24">Curitiba metropolitan region: municipal boundaries</text>',
             '<text x="35" y="63" font-size="14">IBGE 2022 geometry; AMEP membership. Orange = Curitiba. No channel assignment.</text></g>']
    for feature, geometry in zip(document['features'], geometries):
        fill = '#f59e0b' if feature['properties']['codarea'] == '4106902' else ('#334155' if dark else '#dbeafe')
        polygons = [geometry] if geometry.geom_type == 'Polygon' else geometry.geoms
        for polygon in polygons:
            commands = []
            for ring in [polygon.exterior, *polygon.interiors]:
                commands.append('M' + ' L'.join(point(x,y) for x,y in ring.coords) + ' Z')
            parts.append(f'<path d="{" ".join(commands)}" fill="{fill}" fill-rule="evenodd" stroke="{foreground}" stroke-width="0.8"><title>{html.escape(feature["properties"]["name"])}</title></path>')
        p = geometry.representative_point()
        x,y = point(p.x,p.y).split(',')
        parts.append(f'<text x="{x}" y="{y}" text-anchor="middle" font-family="sans-serif" font-size="9" fill="{foreground}">{html.escape(feature["properties"]["name"])}</text>')
    parts.append('</svg>')
    path.write_text('\n'.join(parts), encoding='utf-8')


def build(directory: Path, figures: Path):
    provenance = json.loads((directory/'provenance.json').read_text(encoding='utf-8'))
    for name in SOURCES:
        actual = hashlib.sha256((directory/name).read_bytes()).hexdigest()
        if actual != provenance['sources'][name]['sha256']:
            raise ValueError(f'Source snapshot hash mismatch: {name}')
    source = json.loads((directory/'parana-source.geojson').read_text(encoding='utf-8'))
    municipalities = json.loads((directory/'municipalities-source.json').read_text(encoding='utf-8'))
    names = {str(m['id']): m['nome'] for m in municipalities}
    summaries = {}
    for slug, members in [('metropolitan-29', METRO), ('central-core-14', CORE)]:
        features = []
        for f in source['features']:
            code = str(f['properties']['codarea'])
            if normalized(names[code]) in members:
                features.append({'type':'Feature', 'properties':{'codarea':code,'name':names[code]}, 'geometry':f['geometry']})
        if {normalized(f['properties']['name']) for f in features} != set(members):
            raise ValueError('Incomplete metropolitan membership')
        document = {'type':'FeatureCollection', 'features':sorted(features,key=lambda f:f['properties']['codarea'])}
        scenario = from_geojson(document, scenario_id=slug)
        instance = to_dcop(scenario)
        dump(directory/f'{slug}.geojson', document)
        summary = {'scenario_id':slug, 'regions':len(scenario.regions), 'edges':len(scenario.edges),
                   'connected':True, 'planar':True, 'adjacency':scenario.edges,
                   'factors':len(instance.factors), 'cost_mode':'synthetic-zero',
                   'geojson_sha256':hashlib.sha256((directory/f'{slug}.geojson').read_bytes()).hexdigest()}
        dump(directory/f'{slug}.graph.json',summary)
        summaries[slug] = summary
        figures.mkdir(parents=True,exist_ok=True)
        for dark in (False,True):
            render(document,figures/f'curitiba-{slug}-{"dark" if dark else "light"}.svg',dark)
    print(json.dumps({key:{k:v for k,v in value.items() if k != 'adjacency'} for key,value in summaries.items()},indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=Path('data/geography/curitiba-metropolitan'))
    parser.add_argument('--figures',type=Path,default=Path('docs/assets/img'))
    parser.add_argument('--download',action='store_true',help='Fetch sources into a fresh data directory')
    args = parser.parse_args()
    if args.download:
        download(args.data)
    build(args.data,args.figures)
