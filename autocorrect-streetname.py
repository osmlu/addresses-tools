#!/usr/bin/env python
from xmltodict import parse, unparse
import psycopg2
import urllib
from psycopg2.extras import DictCursor
from collections import OrderedDict
import requests

import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

"""
This program tries to autocorrect street names in an OpenStreetMap dump.

Prepare a .osm file with only the objects you want to go over
wget -4 -N http://osm.kewl.lu/luxembourg.osm/luxembourg.osm.bz2
bzip2 --decompress --force luxembourg.osm.bz2 # force overwrites
osmfilter --keep="addr:housenumber=" luxembourg.osm -o=housenumber.osm

Or use overpass, which is slow.

Doing it this way is stupid; a rewrite should use the addresses in postgresql directly.
But overpass gets us a 'center' and osm xml for free, and I'm lazy.

Upload the output with josm.
"""

overpass_query = """
[out:xml][timeout:99][maxsize:1073741824];
area(3602171347)->.searchArea;
nwr["ref:caclr"!~".*"]["addr:street"](area.searchArea);
// v-- leave this out and update *modified* data in josm. Script takes ages otherwise.
// (._;>;);
out center meta qt;
"""


# # slow match:
#   select
#     st_distance(ST_Transform(geom, 2169), ST_Transform(ST_GeomFromText('POINT(%(lon)s %(lat)s)',4326),2169)) as distance,
#     numero, rue, localite
#   from addresses
#   where
#   rue LIKE %(rue)s
#   order by geom <-> ST_GeomFromText('POINT(%(lon)s %(lat)s)',4326) limit 30
postgis_query_match = """
with index_query as (
  select rue from addresses where rue like %(rue)s
)
select * from index_query limit 1;
"""

# remove where numero if you don't want the safety
# st_distance(ST_Transform(geom, 2169), ST_Transform(ST_GeomFromText('POINT(%(lon)s %(lat)s)',4326),2169)) as distance,
postgis_query_candidates = """
with index_query as (
  select
    numero, rue, localite,
    similarity(upper(rue), upper(%(rue)s)) as sim
  from addresses
  where numero LIKE %(numero)s
  order by geom <-> ST_GeomFromText('POINT(%(lon)s %(lat)s)',4326) limit 30
)
select distinct rue, sim from index_query where sim > 0.5 order by sim limit 30;
"""

overpass_interpreter = "https://overpass-api.de/api/interpreter"
# overpass_interpreter = 'https://overpass.openstreetmap.fr/api/interpreter'
# overpass_interpreter = "https://stereo.lu/housenumber.osm"

osmdata = requests.get(overpass_interpreter, data=overpass_query)
osmdata.encoding = 'utf-8'
osmdata = osmdata.text

log.debug(f"Osmdata: \n%s", osmdata)

# f = open("housenumber.osm", "r")
# osmdata = f.read()

d = parse(osmdata, force_list=("tag", "node", "way", "relation"))
d["osm"]["@upload"] = "false"
conn = psycopg2.connect("dbname=osmlu user=stereo", cursor_factory=DictCursor)
cur = conn.cursor()


def handletags(taglist, lat, lon):
    try:
        numero = [tag["@v"] for tag in taglist if tag["@k"] == "addr:housenumber"][0]
        rue = [tag["@v"] for tag in taglist if tag["@k"] == "addr:street"][0]
        # cp = [tag["@v"] for tag in taglist if tag["@k"] == "addr:postcode"][0]
    except IndexError:
        # we're not an address, abort
        return False
    cur.execute(postgis_query_match, {"lon": lon, "lat": lat, "rue": rue})
    matchrows = cur.fetchall()
    if len(matchrows) != 1:  # meaning no match
        log.info(f"Gonna look for {numero} {rue} at {lat} {lon}")
        cur.execute(
            postgis_query_candidates,
            {"lon": lon, "lat": lat, "rue": rue, "numero": numero},
        )
        candirows = cur.fetchall()
        if len(candirows) == 0:  # no match at all
            warning = "found {} rows for {} {} at {} {}".format(
                len(candirows), numero, rue, lat, lon
            )
            log.warning(warning)
            taglist.append(OrderedDict([("@k", "fixme:CACLR"), ("@v", warning)]))
        if len(candirows) == 1:  # unique match
            newrue = candirows[0]["rue"]
            for tag in taglist:
                if tag["@k"] == "addr:street":
                    tag["@v"] = newrue
                    break
        elif len(candirows) >= 1:  # oooh, more than one candidate
            candidates = [row["rue"] for row in candirows]
            warning = "found {} rows for {} {} at {} {} : {}".format(
                len(candirows), numero, rue, lat, lon, candidates
            )
            log.warning(warning)
            taglist.append(OrderedDict([("@k", "fixme:CACLR"), ("@v", warning)]))
        return True
    else:  # street name is already valid, don't touch
        log.debug(f"Full match for street {rue}")
        return False


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

address_relations = d["osm"]["relation"]
for a_r in address_relations:
    try:
        lat = float(a_r["center"]["@lat"])
        lon = float(a_r["center"]["@lon"])
    except KeyError:
        log.error("No center in this relation: " + urllib.parse.urlencode(a_r))
    if handletags(a_r["tag"], lat, lon):
        del a_r["center"]
        a_r["@action"] = "modify"

with open("streetname-autocorrect.osm", "w") as f:
    f.write(unparse(d, pretty=True))
