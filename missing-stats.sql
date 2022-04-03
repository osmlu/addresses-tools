COPY

(select streetcount.commune, COALESCE(streetcount.count, '0') as streetcount, COALESCE(typocount.count, '0') as typocount, COALESCE(missingcount.count, '0') as missingcount, now() as date from

(select t.commune, count(t.rue) as count from
        (select commune,rue from road_names_cad
        GROUP BY commune,rue
        ) t
group by t.commune) streetcount

LEFT OUTER JOIN

(select t.commune, count(t.name_cadastre) from
        (select c.commune, count(c.rue) as name_cadastre from
            (select commune,rue from road_names_cad except select commune,rue from road_names_osm) c,
            (select commune,rue from road_names_osm except select commune,rue from road_names_cad) o
            WHERE o.commune = c.commune
            AND levenshtein(o.rue, c.rue) <4
            group by c.commune, c.rue -- limit count to 1 per cadastre street
            order by c.commune, name_cadastre
        ) t
group by t.commune) typocount

on (streetcount.commune = typocount.commune)

LEFT OUTER JOIN

(select t.commune, count(t.rue) from
        (select commune,rue from road_names_cad except select commune,rue from road_names_osm
        GROUP BY commune,rue
        ) t
group by t.commune) missingcount

on (streetcount.commune = missingcount.commune)

order by streetcount.commune)

TO STDOUT DELIMITER ',' CSV HEADER;
