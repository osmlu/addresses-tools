#!/usr/bin/env python
from xmltodict import parse, unparse
import psycopg2
import urllib
from psycopg2.extras import DictCursor
from collections import OrderedDict
import requests

import logging

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

"""
This program tries to autocorrect addr:city in an OpenStreetMap dump.

Many Luxembourg localities are loosely defined, with addresses on both sides
of any border you can imagine. It's a mess! This tries to find addresses which
have no match in CACLR, and see if they're maybe in the wrong locality.

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
nwr["ref:caclr"!~".*"]["addr:street"]["addr:housenumber"]["addr:city"](area.searchArea);
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
  select rue from addresses
  where numero like %(numero)s
  and rue like %(rue)s
  and localite like %(localite)s
)
select * from index_query limit 1;
"""

# remove where numero if you don't want the safety
# st_distance(ST_Transform(geom, 2169), ST_Transform(ST_GeomFromText('POINT(%(lon)s %(lat)s)',4326),2169)) as distance,
postgis_query_candidates = """
with index_query as (
  select
  numero, rue, localite, st_distance(ST_Transform(geom, 2169), ST_Transform(ST_GeomFromText('POINT(%(lon)s %(lat)s)',4326),2169)) as dist
  from addresses
  where numero LIKE %(numero)s
  and rue LIKE %(rue)s
)
select distinct numero, rue, localite from index_query where dist < 50 limit 30;
"""

# overpass_interpreter = "https://overpass-api.de/api/interpreter"
# overpass_interpreter = 'https://overpass.openstreetmap.fr/api/interpreter'
overpass_interpreter = "https://stereo.lu/housenumber.osm"

# osmdata = requests.get(overpass_interpreter, data=overpass_query)
# osmdata.encoding = 'utf-8'
# osmdata = osmdata.text

f = open("housenumber.osm", "r")
osmdata = f.read()

d = parse(osmdata, force_list=("tag", "node", "way", "relation"))
d["osm"]["@upload"] = "false"
conn = psycopg2.connect("dbname=gis user=stereo", cursor_factory=DictCursor)
cur = conn.cursor()

uniques = 0
multiples = 0


def handletags(taglist, lat, lon):
    try:
        numero = [tag["@v"] for tag in taglist if tag["@k"] == "addr:housenumber"][0]
        rue = [tag["@v"] for tag in taglist if tag["@k"] == "addr:street"][0]
        localite = [tag["@v"] for tag in taglist if tag["@k"] == "addr:city"][0]
        # cp = [tag["@v"] for tag in taglist if tag["@k"] == "addr:postcode"][0]
    except IndexError:
        # we're not an address, abort
        return False
    # try:
    #     caclr  = [tag["@v"] for tag in taglist if tag["@k"] == "ref:caclr"][0]
    #     # We've got a ref:caclr, no fixes needed, eject
    #     return False
    # except IndexError:
    #     pass
    # log.debug(f"Numero: {numero}, rue:  {rue}, localite: {localite}, lat: {lat}, lon: {lon}")
    cur.execute(
        postgis_query_match,
        {"lon": lon, "lat": lat, "numero": numero, "rue": rue, "localite": localite},
    )
    matchrows = cur.fetchall()
    if len(matchrows) != 1:  # meaning no match
        cur.execute(
            postgis_query_candidates,
            {"lon": lon, "lat": lat, "numero": numero, "rue": rue},
        )
        candirows = cur.fetchall()
        if len(candirows) == 0:  # no match at all
            warning = "found {} rows for {} {} in {} at {} {}".format(
                len(candirows), numero, rue, localite, lat, lon
            )
            log.warning(warning)
            taglist.append(OrderedDict([("@k", "fixme:CACLR"), ("@v", warning)]))
        if len(candirows) == 1:  # unique match
            uniques += 1
            newloc = candirows[0]["localite"]
            for tag in taglist:
                if tag["@k"] == "addr:city":
                    tag["@v"] = newloc
                    break
            log.debug(
                "Found unique match for {} {} {}, is now in {}".format(
                    numero, rue, localite, newloc
                )
            )
        elif len(candirows) >= 1:  # oooh, more than one candidate
            multiples += 1
            candidates = [row["localite"] for row in candirows]
            warning = "found {} rows for {} {} in {} at {} {} : {}".format(
                len(candirows), numero, rue, localite, lat, lon, candidates
            )
            log.warning(warning)
            taglist.append(OrderedDict([("@k", "fixme:CACLR"), ("@v", warning)]))
        return True
    else:  # address is already valid, don't touch
        # log.debug("CACLR match for {} {} {}, no changes needed".format(numero, rue, localite) )
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

with open("localite-autocorrect.osm", "w") as f:
    f.write(unparse(d, pretty=True))

log.info(f"Uniques: {uniques}. Multiples: {multiples}")
