#!/usr/bin/env python
from xmltodict import parse, unparse
import re
import requests


"""
This program normalises housenumbers in an overpass query.

Upload the output with josm.

https://overpass-api.de/api/interpreter?data=%5Bout%3Axml%5D%5Btimeout%3A25%5D%3Barea%283602171347%29%2D%3E%2EsearchArea%3B%28node%5B%22addr%3Ahousenumber%22%5D%5B%22addr%3Ahousenumber%22%21%7E%22%5E%5B1%2D9%5D%5B0%2D9%5D%7B0%2C2%7D%5BA%2DZ%5D%7B0%2C3%7D%28%5B%2D%5D%2A%5B1%2D9%5D%5B0%2D9%5D%7B0%2C2%7D%5BA%2DZ%5D%7B0%2C3%7D%29%7B0%2C12%7D%24%22%5D%28area%2EsearchArea%29%3Bway%5B%22addr%3Ahousenumber%22%5D%5B%22addr%3Ahousenumber%22%21%7E%22%5E%5B1%2D9%5D%5B0%2D9%5D%7B0%2C2%7D%5BA%2DZ%5D%7B0%2C3%7D%28%5B%2D%5D%2A%5B1%2D9%5D%5B0%2D9%5D%7B0%2C2%7D%5BA%2DZ%5D%7B0%2C3%7D%29%7B0%2C12%7D%24%22%5D%28area%2EsearchArea%29%3Brelation%5B%22addr%3Ahousenumber%22%5D%5B%22addr%3Ahousenumber%22%21%7E%22%5E%5B1%2D9%5D%5B0%2D9%5D%7B0%2C2%7D%5BA%2DZ%5D%7B0%2C3%7D%28%5B%2D%5D%2A%5B1%2D9%5D%5B0%2D9%5D%7B0%2C2%7D%5BA%2DZ%5D%7B0%2C3%7D%29%7B0%2C12%7D%24%22%5D%28area%2EsearchArea%29%3B%29%3Bout%3B%3E%3Bout%20skel%20qt%3B%0A
"""


def handletags(taglist):
    # Valid worst case: 1BIS-2BBB
    re_validaddress = re.compile(
        "^[1-9][0-9]{0,2}[A-Z]{0,3}([-][1-9][0-9]{0,2}[A-Z]{0,3}){0,1}$"
    )
    iterate = False
    for tag in taglist:
        if iterate == True:
            break
        if tag["@k"] == "addr:housenumber":
            iterate = True  # stop looping over tags after this one
            # Don't touch if address already valid
            if re_validaddress.match(tag["@v"]):

                return False
            # This is where the magic happens
            # lowercase, e.g. "79a" becomes "79A"
            # whitespace, e.g. "79 - 79A" becomes "79-79A"
            re_whitespace = re.compile(" ")
            # Bad connector, 91/93 or 25;26 or 12,14
            re_badconnector = re.compile("[;/&.,]")

            orig_v = tag["@v"]

            tag["@v"] = re_whitespace.sub(
                "", re_badconnector.sub("-", tag["@v"])
            ).upper()

            # Sanity check
            if not re_validaddress.match(tag["@v"]):
                print("Oops! Weird address: {}".format(orig_v))
                return False

            return True
    return False


overpass_query = """
[out:xml][timeout:25];
area(3602171347)->.searchArea;
(
  node["addr:housenumber"]["ref:caclr"!~".*"]["addr:housenumber"!~"^[1-9][0-9]{0,2}[A-Z]{0,3}([-]*[1-9][0-9]{0,2}[A-Z]{0,3}){0,12}$"](area.searchArea);
  way["addr:housenumber"]["ref:caclr"!~".*"]["addr:housenumber"!~"^[1-9][0-9]{0,2}[A-Z]{0,3}([-]*[1-9][0-9]{0,2}[A-Z]{0,3}){0,12}$"](area.searchArea);
  relation["addr:housenumber"]["ref:caclr"!~".*"]["addr:housenumber"!~"^[1-9][0-9]{0,2}[A-Z]{0,3}([-]*[1-9][0-9]{0,2}[A-Z]{0,3}){0,12}$"](area.searchArea);
);
(._;>;);
out meta qt;
"""

overpass_interpreter = "https://overpass-api.de/api/interpreter"
# overpass_interpreter = 'https://overpass.openstreetmap.fr/api/interpreter'
# overpass_interpreter = 'https://stereo.lu/missing-streetname.osm'

osmdata = requests.get(overpass_interpreter, data=overpass_query).text

d = parse(osmdata, force_list=("tag", "node", "way", "relation"))

d["osm"]["@upload"] = "false"

# Ignore KeyError on tag if we have untagged node/way

try:
    address_nodes = d["osm"]["node"]
except KeyError:
    pass
else:
    for a_n in address_nodes:
        try:
            if handletags(a_n["tag"]):
                a_n["@action"] = "modify"
        except KeyError:
            pass

try:
    address_ways = d["osm"]["way"]
except KeyError:
    pass
else:
    for a_w in address_ways:
        try:
            if handletags(a_w["tag"]):
                a_w["@action"] = "modify"
        except KeyError:
            pass

try:
    address_relations = d["osm"]["relation"]
except KeyError:
    pass
else:
    for a_r in address_relations:
        if handletags(a_r["tag"]):
            del a_r["center"]
            a_r["@action"] = "modify"

with open("housenumber-normalised.osm", "w") as f:
    f.write(unparse(d, pretty=True))
