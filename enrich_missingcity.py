#!/usr/bin/env python

# I think this does something fishy with recursion. Be very careful with fixme:CACLR tags when

from xmltodict import parse, unparse
import requests
import psycopg2
from psycopg2.extras import DictCursor
from collections import OrderedDict
import logging

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger(__name__)

# Luxembourg is area 3602171347
# Kopstal is area 3600407931

overpass_query = """
[out:xml][timeout:99][maxsize:1073741824];
area(3602171347)->.searchArea;
(
node["addr:housenumber"]["addr:city"!~".*"]["addr:hamlet"!~".*"]["addr:place"!~".*"](area.searchArea);
way["addr:housenumber"]["addr:city"!~".*"]["addr:hamlet"!~".*"]["addr:place"!~".*"](area.searchArea);
relation["addr:housenumber"]["addr:city"!~".*"]["addr:hamlet"!~".*"]["addr:place"!~".*"](area.searchArea);
);
(._;>;);
out center meta qt;
"""

# Careful, it's POINT(lon lat), so POINT(6 49)
# Always use %s for sql escaping!
# If you have no table 'addresses', run csventrifuge
postgis_query = """
with index_query as (
  select
    st_distance(ST_Transform(geom, 2169), ST_Transform(ST_GeomFromText('POINT(%(lon)s %(lat)s)',4326),2169)) as distance,
    numero, rue, localite
  from addresses
  where numero LIKE %(numero)s
  and rue LIKE %(rue)s
  order by geom <-> ST_GeomFromText('POINT(%(lon)s %(lat)s)',4326) limit 10
)
select * from index_query where distance < 20 order by distance limit 10;
"""

overpass_interpreter = 'https://overpass-api.de/api/interpreter'
# overpass_interpreter = 'https://stereo.lu/missing-cityname.osm'

osmdata = requests.get(overpass_interpreter, data=overpass_query).text

# print(osmdata)

d = parse(
    osmdata, force_list=('tag', 'node', 'way', 'relation')
    )
conn = psycopg2.connect("dbname=gis user=stereo", cursor_factory=DictCursor)
cur = conn.cursor()


def handletags(taglist, lat, lon):
    try:
        numero = [tag['@v'] for tag in taglist if tag['@k'] == 'addr:housenumber'][0]
        rue = [tag['@v'] for tag in taglist if tag['@k'] == 'addr:street'][0]
    except IndexError:
        print('oops, no number or street! Time to write debug code')
        print(lat)
        print(lon)
        print(taglist)
        return False
    cur.execute(postgis_query, {'lon': lon, 'lat': lat, 'numero': numero, 'rue': rue})
    rows = cur.fetchall()
    if len(rows) == 1:
        row = rows[0]
        if row['rue'] == "Maison":
            place = "hamlet"
        else:
            place = "city"
        taglist.append(OrderedDict(
            [('@k', 'addr:'+place), ('@v', row['localite'])]
            ))
            # Don't add other stuff (postcode, country, etc.) here -
            # it might already be there!! Run a separate overpass query in a separate script.
    else:
        warning = 'found {} rows for {} {} at {} {}'.format(len(rows), numero, rue, lat, lon)
        taglist.append(OrderedDict([('@k', 'fixme:CACLR'), ('@v', warning)]))
        log.warning(warning)
    return True


address_nodes = d['osm']['node']
for a_n in address_nodes:
    lat = float(a_n['@lat'])
    lon = float(a_n['@lon'])
    if 'tag' in a_n:
        if handletags(a_n['tag'], lat, lon):
            a_n['@action'] = 'modify'

address_ways = d['osm']['way']
for a_w in address_ways:
    lat = float(a_w['center']['@lat'])
    lon = float(a_w['center']['@lon'])
    if 'tag' in a_w:
        if handletags(a_w['tag'], lat, lon):
            del a_w['center']
            a_w['@action'] = 'modify'

try:
    address_relations = d['osm']['relation']
except KeyError:
    pass
else:
    for a_r in address_relations:
        lat = float(a_r['center']['@lat'])
        lon = float(a_r['center']['@lon'])
        if handletags(a_r['tag'], lat, lon):
            del a_r['center']
            a_r['@action'] = 'modify'

with open('enriched_city.osm', 'w') as f:
    f.write(unparse(d, pretty=True))
# print(unparse(d, pretty=True))
