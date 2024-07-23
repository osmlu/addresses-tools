# Luxembourg address import

Not perfect:

 - centre of largest building on parcel. Up to 50 addresses on one parcel (rives de Clausen); all share the same position, which makes them easy to identify.
 - When a parcel gets split, the address ends on both pieces. Sometimes many doubles.

The data is sent to the cadastre by the local communes, and some are better at this than others. There are extra, missing and/or out of date addresses.

Street name typos, > 1000 corrections.
 ( `find filters/ enhance/ rules/ -type f | xargs cat | wc -l`)
✅ Create workflow (csventrifuge),
✅ publish on github, github.com/grischard/csventrifuge
✅ publish latest actual corrected csv on stereo.dev.openstreetmap.org as cron
✅ publish latest actual corrected geojson on stereo.dev.openstreetmap.org as cron (ogr2ogr)

Import once, how? Import only addresses that aren't in OSM? Does the address exist on osm already?

If it's a new address, add automatically. If an updated address hasn't been touched there since it was imported, update automatically. Remember versions of the same address id?

Analyse differences automatically and report these back to the Cadastre? How? Danish experience?

Update, manually? Show differences? Regio-osm?

Is the address node over a closed way that already has an address?

81->51 localities have Maison, of which only 16 have >10 houses:
```sql
select count(numero) as numeros, localite from addresses
where rue like 'Maison'
group by localite order by numeros desc
```
~~If street = Maison -> use addr:hamlet or, for very small places, addr:place? addr:place for all that use maison? Place is more used.
	Decide once and for all Maisons should have addr:city, addr:place or both or addr:hamlet which actually seems perfect? addr:place is more used.
	I think I've come to the decision that addr:place is when there's an extra place (rue chose, Zone industrielle machin) and hamlet when there are no street names in the address.~~
	**:arrow_right: I've finally come to the decision to always use addr:place for 'Maison', and drop addr:hamlet**

## Prelude in :angry:

### 🖕Addresses are not unique, e.g. when a parcel got split up, both parts get the old address.
2026->2023->2020->2023->2046->2045->2176->2008->2000->1960->1921->1478->1413->1321->1306 results
Look at unique id_caclr_bat:
```shell=bash
cut -d , -f 7 luxembourg-addresses.csv | sort | uniq -d | wc -l
 ```
 
 Often, OSM has the "correct" position for non-unique ones. TODO calculate in SQL how many are in doubt.
 
### 🖕Addresses agglutinated at same position.
Addresses go on the biggest building of the parcel. If there's more than one address on the parcel, it's a mess. See Atrium Business Park.

Thankfully the latitudes are (for the vast majority) unique, so we can merge on that:

```shell=bash
# non-unique easting+northing in metres
cut -d , -f 10-11 luxembourg-addresses.csv | sed -e 's/,/./' | cut -d . -f 1,3 | sort | uniq -d | wc -l
```

List them (dirty, improve):
```shell=bash
grep -f <(grep -f <(cut -d , -f 10-11 luxembourg-addresses.csv | sed -e 's/,/./' | sort | uniq -d | cut -d . -f 1,2) luxembourg-addresses.csv | cut -d , -f 8 | sort | uniq) luxembourg-addresses.csv | sort
```
    
✅ Merge them into something for osm: do like : `select rue, string_agg(numero, ',') as numero, code_postal, id_caclr_rue, string_agg(id_caclr_bat::text, ';') as id_caclr_bat, lat_wgs84, lon_wgs84, commune from addresses where rue = 'Rue du Puits Romain' group by rue, code_postal, id_caclr_rue, lat_wgs84, lon_wgs84, commune;`

 Often, OSM has the "correct" position for agglutinated ones. TODO calculate in SQL how many are in doubt.


### ✅ 13->14->15 weirdoes like 37AA or 1BIS
```sql
select numero, rue, localite from addresses where numero ~ '[A-Z]{2}';
```
✅ Import as they are, but be aware of them.

###  ✅ garbage in numbers
```sql
select numero, rue, localite from addresses where numero ~ '\.$';
```
8->2->0->1->0
✅ -> reported, filtered 

#### 🖕 Addresses with no house number
132->144->61->59->59->41->40->38->38

```shell=bash
grep -c ,, luxembourg-addresses.csv
```
39 -> 35 of these are more or less house names and have nothing else in that 'street'
```sql
select * from addresses as ass where numero is null and not exists(select rue from addresses where numero is not null and id_caclr_rue = ass.id_caclr_rue)
```
20->6->3 are places that exist and are missing a number. All three need a survey!
```sql
select * from addresses as ass where numero is null and exists(select rue from addresses where numero is not null and id_caclr_rue = ass.id_caclr_rue)
```
:arrow_right: don't import them (yet)
:arrow_right: solve it manually
:arrow_right: see if there are house numbers at the same position?
:arrow_right: see how the situation evolves? -> It's not really improving that quickly...

## Act 1: cleanup

If it exists, does it have all the tags? Postcode, country, locality, street, etc. - some of these shitty addresses only contain housenumber, for example - which is now fixed.

Many have no place or postcode. Detect the incomplete ones. Look up closest neighbour with the same housenumber. If pretty unambiguous, autocomplete. Otherwise, warn.

### Clean up:
 
-  ✅ associatedStreet
-  ✅ addr:interpolation, we're going to get all addresses anyway, they are void.
-  ✅ Postcode starting with L or L-. Overpass wizard `"addr:postcode"~"^L-"`
-  ✅ addr:* on unclosed ways
-  ✅ Validate that all streets exist. Otherwise check nearby?
  ✅`select * from osm_potential_addresses where "addr:street" not in (select rue from addresses);`
      - 5 that are all missing or wrong in CACLR
-  ✅Validate that all localites exist. Otherwise check nearby.
  ✅`select "addr:city" as city from osm_potential_addresses where "ref:caclr" not like 'missing' or NULL except select localite from addresses order by city;`
  - ref:caclr with no address, https://overpass-turbo.eu/s/15zF

#### Cleanup housenumber:

-  ✅Lots of garbage. Some of those are wrong in more than one way.
  ✅ `select * from osm_potential_addresses where "addr:housenumber" !~ '^[1-9][0-9]{0,2}[A-Z]{0,3}(-*[1-9][0-9]{0,2}[A-Z]{0,3}){0,4}$'`
-  ✅lowercase, e.g. "79a" becomes "79A"
  ✅ `select * from osm_potential_addresses where "addr:housenumber" ~ '[a-z]'`
-  ✅ whitespace, e.g. "79 - 79A" becomes "79-79A"
  ✅ `select * from osm_potential_addresses where "addr:housenumber" ~ ' '`
-  ✅ Leading 0, e.g. 07 becomes 7
  ✅ `select * from osm_potential_addresses where "addr:housenumber" ~ '^0'`
-  ✅ Agglutinated addresses
  ✅`select * from osm_potential_addresses where "addr:housenumber" ~ '[,]'`
-  ✅ Automatically replace with points if all corresponding caclr points are within building and are not at same position?
  -  ✅ Manually check the rest...
  -  ✅ `select "addr:housenumber" from osm_potential_addresses where "addr:housenumber" ~ '[;]'`
  -  ✅ `select "addr:housenumber" from osm_potential_addresses where "addr:housenumber" ~ '[/]'`
-  ✅ Not house numbers, ✅ BP10, ✅ Hall 4
	-  ✅ `select "addr:housenumber" from osm_potential_addresses where "addr:housenumber" ~ '^[A-Z]'`
	-  ✅ Script some of the cleanup? Strip whitespace, capitalise? -> **normalize-housenumber.py**
-  ✅ Fix place when it's missing. Nearest neighbour.
	  *	`select "addr:housenumber", "addr:street", "addr:city" from osm_potential_addresses where "addr:housenumber" is not null and "addr:city" is null`
      * If there's just one match within 200m -> shut up and take my money!
      * -> **enrich_missingcity.py**
	  * If there's 0 or 1+ match -> manual fix
* 🖕[974->517->118->78 :muscle:] No match in CACLR
		House number doesn't exist? City doesn't exist? Street doesn't exist? Typo? Corner cases? Neighbour street?
		Some of those are simply not in CACLR but exist.
		See: autocorrect-streetname.py. Maybe do something similar for corner cases?
        This doesn't detect cases where an address does exist elsewhere, like off-by-one errors in a terrace.
```sql
SELECT url,
        osm_user, 
       "addr:housenumber" AS numero, 
       "addr:street"      AS rue, 
       "addr:postcode"    AS codepostal, 
       "addr:city"        AS localite, 
       "note", "note:caclr", "ref:caclr",
       way
FROM   osm_potential_addresses 
       LEFT JOIN addresses 
              ON addresses.numero = osm_potential_addresses."addr:housenumber" 
              AND addresses.localite = osm_potential_addresses."addr:city" 
              AND addresses.rue = osm_potential_addresses."addr:street" 
WHERE  addresses.localite IS NULL 
       AND osm_potential_addresses."ref:caclr" is null
       --AND osm_potential_addresses."note:caclr" IS NULL 
        AND osm_potential_addresses."addr:housenumber" NOT LIKE '%-%'
--         AND osm_potential_addresses."addr:city" NOT LIKE 'Luxembourg'
ORDER  BY localite, rue, numero;
```
* 🖕[87] Bozos with no house number or name (fully drop them?):
  (:warning: **adapting** `osm_potential_addresses`):
```sql
WITH osm_potential_addresses AS (
        SELECT osm_id, osm_user, concat('https://osm.org/way/' , osm_id) as url, "addr:housenumber", "addr:street", "addr:housename", "addr:postcode", "addr:city", "addr:country", "ref:caclr", "note", "note:caclr", "fixme", way
        FROM planet_osm_polygon
        WHERE 
           "addr:street" IS NOT NULL
        UNION SELECT osm_id, osm_user,  concat('https://osm.org/node/' , osm_id) as url, "addr:housenumber", "addr:housename", "addr:street", "addr:postcode", "addr:city", "addr:country", "ref:caclr", "note", "note:caclr", "fixme", way
        FROM planet_osm_point
        where
           "addr:street" IS NOT NULL
        )
        
select distinct osm_id, url, "addr:street" as rue, "addr:housename" as housename, fixme, note, "note:caclr", "ref:caclr" from osm_potential_addresses where "addr:street" is not null and "addr:housenumber" is null and "addr:housename" is null;
```
overpass (slightly different results, I don't know why): 
    `("addr:place"=* or "addr:street"=*) and "addr:housenumber"!=* and "addr:housename"!=* in Luxembourg`
* 🖕Match in CACLR but far away - [32455 -> 648 -> 699] results. Maybe use a buffer for buildings, not the centroid?
```sql
select * from (SELECT   osm.*, 
         caclr.id_caclr_bat, 
         St_distance(St_centroid(osm.way), St_transform(caclr.geom, 3857)) AS dist, 
         St_transform(caclr.geom, 3857)                                    AS caclr_geom, 
         St_astext(St_shortestline(St_centroid(osm.way), St_transform(caclr.geom, 3857))) as line
FROM     osm_potential_addresses osm, 
         addresses caclr 
WHERE    osm."ref:caclr" IS NULL 
AND      osm."addr:housenumber" = caclr.numero 
AND      osm."addr:city" = caclr.localite 
AND      osm."addr:postcode" = caclr.code_postal::text 
AND      osm."addr:street" = caclr.rue 
ORDER BY dist DESC) as foo where dist > 30;
```

* 🖕 [596 -> 616] Match in CACLR but in another parcel, and more than 30m away. Off by one errors, etc.
```sql
select * from (SELECT
         round(St_distance(St_centroid(osm.way), St_transform(caclr.geom, 3857))) AS dist, 
		 osm.*, 
         caclr.id_caclr_bat, 
         St_transform(caclr.geom, 3857)                                    AS caclr_geom, 
         St_astext(St_shortestline(St_centroid(osm.way), St_transform(caclr.geom, 3857))) as line,
         caclr.*,
         parcelles.*
FROM     osm_potential_addresses osm, 
         addresses caclr,
         parcelles 
WHERE    osm."ref:caclr" IS NULL 
AND      osm."addr:housenumber" = caclr.numero 
AND      osm."addr:city" = caclr.localite
AND      osm."addr:postcode" = caclr.code_postal::text 
AND      osm."addr:street" = caclr.rue 
and      caclr.id_parcelle = parcelles.id_parcell
and not  st_intersects(osm.way, St_transform(parcelles.wkb_geometry, 3857))
ORDER BY dist DESC) as foo where dist > 10;
```

🖕[1101->514] double addresses in osm

```sql
    select "addr:housenumber", "addr:street", "addr:city", count(*)
    from osm_potential_addresses
    where "addr:housenumber" is not null
    group by "addr:housenumber", "addr:street", "addr:city"
    HAVING count(*) > 1
    order by count desc, "addr:city", "addr:street", "addr:housenumber"
```

or overpass:

    way["building"!~".*"]["addr:housenumber"]({{bbox}});

- but it turns out it's also been used a lot on shops, sites, schools... French contact:housenumber solution?

OSM Inspector: https://tools.geofabrik.de/osmi/?view=addresses&lon=6.15464&lat=49.65275&zoom=11&overlays=no_addr_street,street_not_found,place_not_found,misformatted_housenumber,addrx_on_nonclosed_way

Osmose: https://osmose.openstreetmap.fr/fr/map/#country=luxembourg&item=2060

🖕[~0] fix cases where `ref:caclr=missing` is maybe a lie. Add a `note:caclr` if it's still true.

```sql
SELECT
		 osm.url,
		 osm_user,
		 osm."addr:housenumber",
		 caclr.numero,
		 osm."addr:street",
		 caclr.rue,
		 osm."addr:city",
		 caclr.localite,
		 osm."note:caclr",
		 osm."note", 
		 caclr.id_caclr_bat
FROM     osm_potential_addresses osm, 
         addresses caclr
WHERE    osm."ref:caclr" like 'missing' 
AND      st_intersects(osm.way, St_transform(caclr.geom, 3857))
--and      osm."addr:housenumber" not like caclr.numero
order by localite, rue, numero
```

## Act 2

Do the matching by commune to reduce false positives.

Other scripts:
	Norway - http://osm.beebeetle.com/addrnodeimportstatus.php https://github.com/rubund/addrnodeimport
	Denmark - rasher awol, mostly another guy
	Germany - Regio-OSM, newly added positions
	Flanders - sander17, no positions
	https://github.com/balrog-kun/osm-addr-tools/tree/master can be useful if we rewrite the street name matching...
	https://wiki.openstreetmap.org/wiki/Import/Catalogue/NYC_Buildings_Addresses conflated manually. Great, guys.
	https://wiki.openstreetmap.org/wiki/Import/Catalogue/Address_import_for_Biella#Data_Merge_Workflow didn't really have conflation to do
	https://wiki.openstreetmap.org/wiki/Address_import_from_RUIAN vague on conflation
	https://wiki.openstreetmap.org/wiki/Canton_of_Bern_Address_Import uses the conflation plugin. Interesting workflow.

Matching what's already there (how did I count these?):	5374 nodes, 25916 polygons


Matching sieve:
	Same caclr number
		join on caclr number
	Same number, street, postcode = 3319 nodes 19886 ways
	Same number, steet, postcode in unaccented uppercase = ?
	Same number, street within 40 metres = ?
	Same number, steet in unaccented uppercase within 40 metres = ?
	Same number, street, city (but there's a lot of commune/locality snafu) = 3132 nodes 13357 ways commune, 3550 nodes 19978 ways localite
	Same unique number and trigram-similar street name within 40 metres = ?

Find candidates for each matching criteria - number, street, fuzzy street, commune, locality, postcode, nearby.... if you get caught in a higher sieve, you and your match don't participate in lower sieves.

Sort sieves by the thickest addresses (lots of evidence) to the thinnest.

For the incomplete addresses that can be matched, add missing information. Check for the closest address with the same basic information within a radius?

? For those that can't be uniquely identified, mark all possible choices as dontimport.

## DA CAPO

Do we have caclr-tagged addresses where the info doesn't match caclr?

```sql
select osm_potential_addresses.osm_id, osm_potential_addresses."addr:housenumber", addresses.numero, osm_potential_addresses."addr:street", addresses.rue, osm_potential_addresses."ref:caclr", osm_potential_addresses."addr:city",addresses.localite
from osm_potential_addresses, addresses
where osm_potential_addresses."ref:caclr" = addresses.id_caclr_bat
and (
osm_potential_addresses."addr:street" != addresses.rue
or
osm_potential_addresses."addr:city" != addresses.localite
)
```

Do the CACLR references we have still exist?

```sql
select distinct "ref:caclr" from osm_potential_addresses where "ref:caclr" not in ('missing', 'wrong') except select id_caclr_bat from addresses order by "ref:caclr";
```

Is the address new? (look at caclr id)(are caclr id incremental?)
If it isn't new, has it moved or otherwise been changed? (How do we detect that? Hash the data for a caclr id?)
Is it in OSM? Check if marked. Warn if not. (What did I mean by marked?)
Was it from our import? Update import.
Was it manually imported at the previous position? Move it.
Was it manually tagged differently? Keep those tags.

Spelling differences, postcode differences, street differences (7 arpents/huberty)...

The imports have to happen quickly. Get the new information from the source asap, to minimise differences.

Should we import caclr id? Can we do the object tracking differently? It would make our life and cross-checking a lot easier. If a house has changed street name and numbering, we're screwed without caclr id.

See also: http://www.openstreetmap.org/user/PlaneMad/diary/38475

Has the address been deleted in CACLR or osm?

## Applause

Osmose - http://osmose.openstreetmap.fr/fr/errors/?country=luxembourg&item=2060 (too many to map) but especially http://osmose.openstreetmap.fr/fr/errors/?source=762&item=2060&class=1
	- ✅ 315 housenumbers with no streets, enrich manually? But mind addr:place for Maison.
	- 44 housenames with no other address. Merge after import, easier. Most of those are really name=* anyway.
	- 3164 without addr:city - can be enriched automatically with street, housenumber and position and close neighbours.
	- 3696 without postcode - can be enriched automatically with street, housenumber and position and close neighbours.

- How many have the commune instead of the localité in addr:city? Generate concave hull of addresses to double-check? Check disagreements with CACLR? Check nearest neighbour?


We're going to have places where people entered the commune in the city field... validate with closest other address for tuples that don't exist?

Validate that all CP exist. Otherwise check nearby.
	select "addr:postcode" as postcode from planet_osm_polygon where "addr:country" not in ('BE', 'DE', 'FR') except select code_postal::text from addresses order by postcode; -> 28 rows
	select "addr:postcode" as postcode from planet_osm_point where "addr:country" not in ('BE', 'DE', 'FR') except select code_postal::text from addresses order by postcode; -> 12 rows
Validate that all street-cp pairs exist. Otherwise check nearby.
Validate that we know all the places and localities -> osmi

Addresses where place has been added: way 29479525 -> should go to suburb?

We have an address but the street can't be found -> maproulette?

Can we create something like https://maps.aimpulse.com/osm/addresses/ ?

### Merge addresses with buildings

After each import run:
	IF (there is a building with no address tags
		OR
	    there is a building with the same address tags)
	 	AND
	    there are no other address nodes within this building
	THEN
		tag the building with that address node's tags
		delete that address node

### Watch for changes

	Maintain a list of object IDs
	Check for them in dumps
	Issue a warning with object IDs and changeset IDs if they get changed and it's not by the import bot
	Changes can be accepted, accepted and sent upstream, one-click reverted in josm, edited in josm (which will create a new change, GOTO 1).

### QA

Addresses that exist on both sides but are in very different positions. -> regio-osm or sql query above
 - Exclude addresses that have been distributed on one cadastral parcel.
 - Sort by distance, look at furthest distance?
 - Filter out points that are within the same PCN building polygon?
 - Filter out points that are within the same PCN parcel polygon?
 - Show distance in QA list? Dietmar does this.

## Toolbox

```sql
    WITH osm_potential_addresses AS (
        SELECT osm_id, osm_user, concat('https://osm.org/way/' , osm_id) as url, "addr:housenumber", "addr:street", "addr:postcode", "addr:city", "addr:country", "ref:caclr", "note", "note:caclr", "fixme", way
        FROM planet_osm_polygon
        WHERE "addr:housenumber" IS NOT NULL
          AND "addr:street" IS NOT NULL
          AND "addr:postcode" IS NOT NULL
          AND "addr:city" IS NOT NULL
		  AND "addr:country" like 'LU' or NULL
        UNION SELECT osm_id, osm_user,  concat('https://osm.org/node/' , osm_id) as url, "addr:housenumber", "addr:street", "addr:postcode", "addr:city", "addr:country", "ref:caclr", "note", "note:caclr", "fixme", way
        FROM planet_osm_point
        WHERE "addr:housenumber" IS NOT NULL
          AND "addr:street" IS NOT NULL
          AND "addr:postcode" IS NOT NULL
          AND "addr:city" IS NOT NULL
		  AND "addr:country" like 'LU' or NULL
        )