#!/usr/bin/env python

# I think this does something fishy with recursion. Be very careful with fixme:CACLR tags when

import logging
from collections import OrderedDict

import psycopg2
import requests
from psycopg2.extras import DictCursor

from xmltodict import parse, unparse
import urllib

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger(__name__)

# Luxembourg is area 3602171347
# Kopstal is area 3600407931

overpass_query = """
[out:xml][timeout:99][maxsize:1073741824];
area(3602171347)->.searchArea;
nwr["addr:housenumber"]["addr:postcode"!~".*"](area.searchArea);
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
    numero, rue, localite, code_postal
  from addresses
  where numero LIKE %(numero)s
  and rue LIKE %(rue)s
  and localite LIKE %(city)s
  order by geom <-> ST_GeomFromText('POINT(%(lon)s %(lat)s)',4326) limit 10
)
select * from index_query where distance < 200 order by distance limit 10;
"""

overpass_interpreter = "https://overpass-api.de/api/interpreter"
# overpass_interpreter = 'https://stereo.lu/missing-cityname.osm'

osmdata = requests.get(overpass_interpreter, data=overpass_query).text

# print(osmdata)

d = parse(osmdata, force_list=("tag", "node", "way", "relation"))
conn = psycopg2.connect("dbname=osmlu user=stereo", cursor_factory=DictCursor)
cur = conn.cursor()


def handletags(taglist, lat, lon):
    try:
        numero = [tag["@v"] for tag in taglist if tag["@k"] == "addr:housenumber"][0]
        rue = [tag["@v"] for tag in taglist if tag["@k"] == "addr:street"][0]
    except IndexError:
        # we're not an address, abort
        return True
    try:
        city = [tag["@v"] for tag in taglist if tag["@k"] == "addr:city"][0]
    except IndexError:
        error = "{} {} at {} {} has neither city nor hamlet".format(
            numero, rue, lat, lon
        )
        log.error(error)
        return False
    cur.execute(
        postgis_query,
        {"lon": lon, "lat": lat, "numero": numero, "rue": rue, "city": city},
    )
    rows = cur.fetchall()
    if len(rows) > 0:
        if all(x["code_postal"] == rows[0]["code_postal"] for x in rows):
            # unique postcode found in results
            # found 1 postcode, or >1 postcode but all are equal
            cp = rows[0]["code_postal"]
            taglist.append(OrderedDict([("@k", "addr:postcode"), ("@v", cp)]))
            # Don't add other stuff (city, street, etc.) here -
            # it might already be there!! Run a separate overpass query in a separate script.
            if len(rows) > 1:
                log.warning(
                    "found {} rows for {} {} {} at {} {} but all are equal to {}".format(
                        len(rows), numero, rue, city, lat, lon, cp
                    )
                )
        else:
            warning = "found {} rows for {} {} {} at {} {} but all are not equal to {}".format(
                len(rows), numero, rue, city, lat, lon, rows[0]["code_postal"]
            )
            taglist.append(OrderedDict([("@k", "fixme:CACLR"), ("@v", warning)]))
            log.warning(warning)
    else:
        warning = "found {} rows for {} {} {} at {} {}".format(
            len(rows), numero, rue, city, lat, lon
        )
        taglist.append(OrderedDict([("@k", "fixme:CACLR"), ("@v", warning)]))
        log.warning(warning)
    return True
    # Why am I not returning taglist here?


address_nodes = d["osm"]["node"]
for a_n in address_nodes:
    lat = float(a_n["@lat"])
    lon = float(a_n["@lon"])
    if "tag" in a_n:
        if handletags(a_n["tag"], lat, lon):
            a_n["@action"] = "modify"

address_ways = d["osm"]["way"]
for a_w in address_ways:
    try:
        lat = float(a_w["center"]["@lat"])
        lon = float(a_w["center"]["@lon"])
    except KeyError:
        log.error("No center in this way: " + urllib.parse.urlencode(a_w))
    if "tag" in a_w:
        if handletags(a_w["tag"], lat, lon):
            del a_w["center"]
            a_w["@action"] = "modify"

with open("enriched_postcode.osm", "w") as f:
    f.write(unparse(d, pretty=True))
# print(unparse(d, pretty=True))
