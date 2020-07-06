#!/usr/bin/env python
from xmltodict import parse, unparse
import re

"""
This program matches housenumbers by a range of criterias, sending
leftovers to the next set of criterias.

Prepare a .osm file with only the objects you want to go over
wget -4 -N http://osm.kewl.lu/luxembourg.osm/luxembourg.osm.bz2
bzip2 --decompress --force luxembourg.osm.bz2 # force overwrites
osmfilter --keep="addr:housenumber=" luxembourg.osm -o=housenumber.osm

What pairing algorithm do we use for unclear matches? Gale-Shapley would
avoid osm address A matching with cadastre address X if address B is a better
match for X, but I think that our dataset should be unambiguous enough anyway.
Choosing the closest addresses as possible matches should give pretty good
results.

So the idea is:

	Same caclr number
	Same (number, street, postcode) = 3319 nodes 19886 ways
	Same (number, street) within 40 metres = ?
    (This is probably where it's reasonable to stop)
	Same unique number and trigram-similar street name within 40 metres = ?
	Same number, street, city (but there's a lot of commune/locality snafu) = 3132 nodes 13357 ways commune, 3550 nodes 19978 ways localite

We can outsource some of this to postgis? Do it all in postgis?

"""

xml = open("housenumber.osm", "r")
org_xml = xml.read()

d = parse(
    org_xml,
    force_list={'tag': True}
)

matched =

for s in sieve_list:

    address_nodes = d['osm']['node']
    for a_n in address_nodes:
        s.handle(a_n)


    address_ways = d['osm']['way']
    for a_w in address_ways:
        lat = float(a_w['center']['@lat'])
        lon = float(a_w['center']['@lon'])
