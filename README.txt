1. ../csventrifuge/run.sh
2. ../updatedb.sh
3. ./normalise-housenumbers.py
4. upload in josm
5. ./enrich_missingstreet.py
6. upload in josm
7. ./enrich_missingcity.py
8. upload in josm
9. ./enrich_missingpostcode.py
10. ./autocorrect-streetname.py

If you get a KeyError: 'osm' it means there's nothing to do :]. Copy the try/except from relations.

If you need a local housenumber file:
 wget -N http://osm.kewl.lu/luxembourg.osm/luxembourg.osm.bz2; bzip2 --decompress --force luxembourg.osm.bz2 ;osmfilter --keep="addr:housenumber=" luxembourg.osm -o=housenumber.osm