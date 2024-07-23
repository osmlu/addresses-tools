#!/usr/bin/env python

from xmltodict import parse, unparse
import requests
import psycopg2
from psycopg2.extras import DictCursor
from collections import OrderedDict

overpass_query = """
[out:xml][timeout:99][maxsize:1073741824];
area(3602171347)->.searchArea;
(
  node["addr:street"!~".*"]["ref:caclr"!~".*"]["addr:place"!~".*"]["addr:housenumber"](area.searchArea);
  way["addr:street"!~".*"]["ref:caclr"!~".*"]["addr:place"!~".*"]["addr:housenumber"](area.searchArea);
  relation["addr:street"!~".*"]["ref:caclr"!~".*"]["addr:place"!~".*"]["addr:housenumber"](area.searchArea););
(._;>;);
out center meta qt;
"""

# Careful, it's POINT(lon lat), so POINT(6 49)
# Always use %s for sql escaping!
postgis_query = """
with index_query as (
  select
    st_distance(ST_Transform(geom, 2169), ST_Transform(ST_GeomFromText('POINT(%s %s)',4326),2169)) as distance,
    numero, rue, localite, code_postal, id_caclr_bat, commune
  from addresses
  where numero LIKE %s
  order by geom <-> ST_GeomFromText('POINT(%s %s)',4326) limit 10
)
select * from index_query where distance < 40 order by distance limit 10;
"""

overpass_interpreter = "https://overpass-api.de/api/interpreter"
# overpass_interpreter = 'https://overpass.openstreetmap.fr/api/interpreter'
# overpass_interpreter = 'https://stereo.lu/missing-streetname.osm'

osmdata = requests.get(overpass_interpreter, data=overpass_query).text

d = parse(osmdata, force_list=("tag", "node", "way", "relation"))
conn = psycopg2.connect("dbname=osmlu user=stereo", cursor_factory=DictCursor)
cur = conn.cursor()


def handletags(taglist, lat, lon):
    for tag in taglist:
        if tag["@k"] == "addr:housenumber":
            cur.execute(postgis_query, (lon, lat, tag["@v"], lon, lat))
            rows = cur.fetchall()
            if len(rows) == 1:
                row = rows[0]
                if row["rue"] == "Maison":
                    taglist.append(
                        OrderedDict([("@k", "addr:place"), ("@v", row["localite"])])
                    )
                else:
                    taglist.append(
                        OrderedDict([("@k", "addr:street"), ("@v", row["rue"])])
                    )
                    # Don't add other stuff (postcode, country, etc.) here -
                    # it might already be there!! Run a separate overpass query.
            else:
                taglist.append(
                    OrderedDict(
                        [
                            ("@k", "fixme:CACLR"),
                            (
                                "@v",
                                "found {} rows for {} at {} {}".format(
                                    len(rows), tag["@v"], lat, lon
                                ),
                            ),
                        ]
                    )
                )
            return True
    # else:
    #     print('oops')
    #     return False



try:
    address_nodes = d["osm"]["node"]
except KeyError:
    pass
else:
    for a_n in address_nodes:
        lat = float(a_n["@lat"])
        lon = float(a_n["@lon"])
        if "tag" in a_n:
            if handletags(a_n["tag"], lat, lon):
                a_n["@action"] = "modify"


try:
    address_ways = d["osm"]["way"]
except KeyError:
    pass
else:
    for a_w in address_ways:
        lat = float(a_w["center"]["@lat"])
        lon = float(a_w["center"]["@lon"])
        if "tag" in a_w:
            if handletags(a_w["tag"], lat, lon):
                del a_w["center"]
                a_w["@action"] = "modify"

try:
    address_relations = d["osm"]["relation"]
except KeyError:
    pass
else:
    for a_r in address_relations:
        lat = float(a_r["center"]["@lat"])
        lon = float(a_r["center"]["@lon"])
        if handletags(a_r["tag"], lat, lon):
            del a_r["center"]
            a_r["@action"] = "modify"

with open("enriched_street.osm", "w") as f:
    f.write(unparse(d, pretty=True))
# print(unparse(d, pretty=True))
