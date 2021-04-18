#!/usr/bin/env python
#
#

import psycopg2
import json
from clint import arguments
from clint.textui import colored, progress
from pathlib import Path

PATH = "./streetlist/"

QUERIES = {
    "similar": """select array_to_json(array_agg(row_to_json(data)))::text
    from (
      select distance, name_cadastre, name_osm from
      (select *, rank() over (partition by cl.commune,cl.name_cadastre order by cl.distance) as rank from
          (select distinct c.commune, c.rue as name_cadastre, o.rue as name_osm, levenshtein(o.rue, c.rue) as distance from
              (select commune,rue from road_names_cad except select commune,rue from road_names_osm) c,
              (select commune,rue from road_names_osm except select commune,rue from road_names_cad) o
              WHERE o.commune = c.commune
              AND levenshtein(o.rue, c.rue) <4
              AND c.commune = %s
          ) cl) s
      where s.rank=1 order by s.name_cadastre
    ) data;""",
    #########
    "missing": """select array_to_json(array_agg(row_to_json(data)))::text
    from (select r.village, r.rue from road_names_cad r,
        (
            (select commune,rue from road_names_cad except select commune,rue from road_names_osm)
            except
            (
                SELECT c.commune, c.rue FROM
                (select commune,rue from road_names_cad except select commune,rue from road_names_osm) c,
                (select commune,rue from road_names_osm except select commune,rue from road_names_cad) o
                WHERE o.commune = c.commune
                AND levenshtein(o.rue, c.rue) < 4
            )
        ) cad
        WHERE r.commune = cad.commune
        AND cad.commune = %s
        AND cad.rue = r.rue
    group by r.village,r.rue
    order by r.village,r.rue) data;
    """,
    #########
    "extra": """select array_to_json(array_agg(row_to_json(data)))::text
    from (select r.rue from road_names_osm r,
        (
            (select commune,rue from road_names_osm except select commune,rue from road_names_cad)
            except
            (
                SELECT c.commune, c.rue FROM
                (select commune,rue from road_names_cad except select commune,rue from road_names_osm) o,
                (select commune,rue from road_names_osm except select commune,rue from road_names_cad) c
                WHERE o.commune = c.commune
                AND levenshtein(o.rue, c.rue) < 4
            )
        ) osm
        WHERE r.commune = osm.commune
        AND osm.commune = %s
        AND osm.rue = r.rue
    group by r.rue
    order by r.rue) data;
    """,
}


def main():
    debug = False
    args = arguments.Args()
    if args.get(0) == "-d":
        debug = True
        print(colored.yellow("DEBUG turned on"))

    # Try to connect

    try:
        conn = psycopg2.connect("dbname='gis'")
    except Exception as exc:
        print(
            colored.red("DEBUG: I am unable to connect to the database: ", exc.args[0])
        )

    cur = conn.cursor()
    try:
        cur.execute("""select distinct commune from road_names_cad order by commune;""")
    except Exception as exc:
        print(colored.red("DEBUG: I can't SELECT the communes: ", exc.args[0]))

    communes = cur.fetchall()
    if len(communes) != 102:
        if debug:
            print(
                colored.red(
                    "DEBUG: Got the wrong number of communes! Expected 106 rows, got {}".format(
                        len(communes)
                    )
                )
            )
    if debug:
        print(colored.green("DEBUG: Got {} communes! Progress:".format(len(communes))))

    # Get the json for all communes

    for commune in progress.bar(
        [communelist[0] for communelist in communes],
        label="Communes handled ",
        expected_size=102,
        width=102,
    ):
        if debug:
            print(colored.blue("DEBUG: " + commune))
        for queryname, query in QUERIES.items():
            if debug:
                print(colored.green("DEBUG:     {} {}".format(queryname, commune)))
            try:
                cur.execute(query, [commune])
            except Exception as exc:
                print(
                    "DEBUG: I can't retrieve {} for {}! ".format(queryname, commune),
                    exc.args[0],
                )
            myjson = str(cur.fetchall()[0][0])
            if myjson != "None":
                if debug:
                    # print myjson
                    # pretty print
                    myjson = json.dumps(
                        json.loads(myjson),
                        indent=4,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ": "),
                    )
            else:
                if debug:
                    print(
                        colored.yellow(
                            "DEBUG: 0 results for {} query in {}".format(
                                queryname, commune
                            )
                        )
                    )
                myjson = "{}"

            filename = Path(PATH + queryname + "/" + commune.replace("/", "-sur-", 1) + ".json")
            filename.touch(exist_ok=True)  # will create file, if it exists will do nothing
            file = open(filename)
            with open(filename, "w"
            ) as out_file:
                out_file.write(myjson)


if __name__ == "__main__":
    main()
