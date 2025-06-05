PlotInfo service
================

Query additional plot information at a geographic position and create PDF reports for them.

Grundstücksinformation:
  * Basisinformationen
  * Amtliche Vermessung
  * ÖREB-Kataster
  * Eigentümerinformationen

Uses an [ÖREB-Webservice](https://www.cadastre.ch/de/manual-oereb/service/webservice.html) to generate ÖREB JSONs, XMLs and PDFs.

Uses a [GBDBS Service](https://www.egris.admin.ch/dam/data/egris/begleitgruppe/2015-01-21/gbdbs-auskunft-d.pdf) for plot owner info requests.


Dependencies
------------

* [ÖREB-Webservice](https://www.cadastre.ch/de/manual-oereb/service/webservice.html)
* [GBDBS Service](https://www.egris.admin.ch/dam/data/egris/begleitgruppe/2015-01-21/gbdbs-auskunft-d.pdf)


Queries
-------

### Basic plot info

SQL for basic info query:

* ENV: `BASIC_INFO_SQL`
* input: `x`, `y`, `srid`, `buffer`
* output: `egrid`, `nummer`, `art_txt`, optional custom fields (see `BASIC_INFO_FIELDS`)

Example:
```sql
SELECT
    g.egrid, g.nummer, g.art_txt, g.flaechenmass,
    ST_AsText(ST_Simplify(g.geometrie, 0.01)) AS geom,
    gem.gemeindename || ' (' || gem.bfs_nr || ')' AS gemeinde,
    'TODO' as grundbuch,
    ST_XMin(g.geometrie) as xmin,
    ST_YMin(g.geometrie) as ymin,
    ST_XMax(g.geometrie) as xmax,
    ST_YMax(g.geometrie) as ymax
FROM
    agi_mopublic_pub.mopublic_grundstueck g
    JOIN agi_mopublic_pub.mopublic_gemeindegrenze gem
        ON gem.bfs_nr = g.bfs_nr
WHERE ST_Intersects(
    g.geometrie,
    ST_Buffer(
        ST_SetSRID(ST_Point(:x, :y), :srid),
        :buffer
    )
);
```

Custom info fields for basic info query as list of `[{"<query field>": "<label>"}]`:

* ENV: `BASIC_INFO_FIELDS`

Add these query fields to the SELECT fields in the `BASIC_INFO_SQL` query.

The query field `flaechenmass` is formatted as `1'234 m²`.

The special query field `_flurnamen_` is used to get values from a separate Flurnamen query.

Example:
```json
[
  {"gemeinde": "Gemeinde"},
  {"grundbuch": "Grundbuch"},
  {"nummer": "Nummer"},
  {"egrid": "E-GRID"},
  {"flaechenmass": "Fläche"},
  {"art_txt": "Art"},
  {"_flurnamen_": "Flurnamen"}
]
```

SQL for Flurnamen query for plot with EGRID:

* ENV: `FLURNAMEN_SQL`
* input: `egrid`
* output: `flurname`

Example:
```sql
SELECT
    f.flurname
FROM
    agi_mopublic_pub.mopublic_flurname f
    JOIN agi_mopublic_pub.mopublic_grundstueck g
        ON ST_Intersects(f.geometrie, g.geometrie)
        AND NOT ST_Touches(f.geometrie, g.geometrie)
WHERE g.egrid = :egrid
ORDER BY f.flurname;
```

### Detailed plot info

SQL for additional plot information query for EGRID:

* ENV: `DETAILED_INFO_SQL`
* input: `egrid`
* output: `flaechenmass`, `art`, `grundbuchamt`, `nfgeometer`

Example:
```sql
SELECT
    g.flaechenmass, g.art, 'TODO' AS grundbuchamt, 'TODO' AS nfgeometer
FROM
    agi_mopublic_pub.mopublic_grundstueck g
WHERE g.egrid = :egrid LIMIT 1;
```

SQL for querying land cover fractions inside plot with EGRID:

* ENV: `LAND_COVER_FRACTIONS_SQL`
* input: `egrid`
* output: `area`, `area_percent`, `art`, `art_txt`

Example:
```sql
WITH bodenbedeckung AS (
    SELECT
        ST_Area(ST_Intersection(b.geometrie, g.geometrie))
            AS b_area,
        ST_Area(g.geometrie) AS g_area,
        b.art, b.art_txt
    FROM
        agi_mopublic_pub.mopublic_bodenbedeckung b
        JOIN agi_mopublic_pub.mopublic_grundstueck g
            ON ST_Intersects(b.geometrie, g.geometrie)
            AND NOT ST_Touches(b.geometrie, g.geometrie)
    WHERE g.egrid = :egrid
)
SELECT
    SUM(b_area) AS area, SUM(b_area/g_area) * 100 AS area_percent,
    art, art_txt
FROM bodenbedeckung b
GROUP BY art, art_txt
ORDER BY area DESC;
```

SQL for querying building addresses inside plot with EGRID:

* ENV: `BUILDING_ADDRESSES_SQL`
* input: `egrid`
* output: `strassenname`, `hausnummer`, `plz`, `ortschaft`

Example:
```sql
SELECT
    a.strassenname, a.hausnummer, a.plz, a.ortschaft
FROM
    agi_mopublic_pub.mopublic_gebaeudeadresse a
    JOIN agi_mopublic_pub.mopublic_grundstueck g
        ON ST_Contains(g.geometrie, a.lage)
WHERE g.egrid = :egrid
ORDER BY a.strassenname, a.hausnummer;
```

SQL for querying SDR infos for Liegenschaft plot (`art == 0`) with EGRID:

* ENV: `SDR_INFOS_LIEGENSCHAFT_SQL`
* input: `egrid`
* output: `nummer`, `art`, `art_txt`, `area`

Example:
```sql
SELECT
    sdr.nummer, sdr.art, sdr.art_txt,
    ST_Area(ST_Intersection(sdr.geometrie, g.geometrie)) AS area
FROM
    agi_mopublic_pub.mopublic_grundstueck sdr
    JOIN agi_mopublic_pub.mopublic_grundstueck g
        ON ST_Intersects(sdr.geometrie, g.geometrie)
        AND NOT ST_Touches(sdr.geometrie, g.geometrie)
WHERE
    g.egrid = :egrid AND sdr.art != 0 AND g.art = 0
ORDER BY
    ST_Area(ST_Intersection(sdr.geometrie, g.geometrie)) DESC;
```

SQL for querying Liegenschaften infos for SDR plot (`art != 0`) with EGRID:

* ENV: `SDR_INFOS_SDR_SQL`
* input: `egrid`
* output: `nummer`, `art`, `art_txt`, `area`

Example:
```sql
SELECT
    g.nummer, g.art, g.art_txt,
    ST_Area(ST_Intersection(sdr.geometrie, g.geometrie)) AS area
FROM
    agi_mopublic_pub.mopublic_grundstueck g
    JOIN agi_mopublic_pub.mopublic_grundstueck sdr
        ON ST_Intersects(g.geometrie, sdr.geometrie)
        AND NOT ST_Touches(g.geometrie, sdr.geometrie)
WHERE
    sdr.egrid = :egrid AND sdr.art != 0 AND g.art = 0
ORDER BY
    ST_Area(ST_Intersection(sdr.geometrie, g.geometrie)) DESC;
```

Optional lookup for custom land cover colors as dict `{"<type>": "<CSS color>"}`:

* ENV: `LCSFC_COLORS`

Example:
```json
{
  "Gebaeude": "#ffc8c8",

  "Strasse_Weg": "#dcdcdc",
  "Trottoir": "#dcdcdc",
  "Verkehrsinsel": "#dcdcdc",
  "Bahn": "#f0e6c8",
  "Flugplatz": "#dcdcdc",
  "Wasserbecken": "#96c8ff",
  "uebrige_befestigte": "#f0f0f0",
  "Sportanlage_befestigt": "#f0f0f0",
  "Lagerplatz": "#f0f0f0",
  "Boeschungsbauwerk": "#f0f0f0",
  "Gebaeudeerschliessung": "#f0f0f0",
  "Parkplatz": "#f0f0f0",

  "Acker_Wiese_Weide": "#f0ffc8",
  "Acker_Wiese": "#f0ffc8",
  "Weide": "#f0ffc8",
  "Reben": "#ffffc8",
  "uebrige_Intensivkultur": "#ffffc8",
  "Obstkultur": "#ffffc8",
  "Gartenanlage": "#f0ffc8",
  "Hoch_Flachmoor": "#c8fff0",
  "uebrige_humusierte": "#f0ffc8",
  "Parkanlage_humusiert": "#f0ffc8",
  "Sportanlage_humusiert": "#f0ffc8",
  "Friedhof": "#f0ffc8",

  "stehendes": "#96c8ff",
  "stehendes Gewaesser": "#96c8ff",
  "fliessendes": "#96c8ff",
  "fliessendes Gewaesser": "#96c8ff",
  "Schilfguertel": "#c8fff0",

  "geschlossener_Wald": "#a0f0a0",
  "uebrige_bestockte": "#c8f0a0",
  "Parkanlage_bestockt": "#c8f0a0",
  "Hecke": "#c8f0a0",

  "Fels": "#ffffff",
  "Gletscher_Firn": "#ffffff",
  "Geroell_Sand": "#ffffff",
  "Abbau_Deponie": "#ffffff",
  "uebrige_vegetationslose": "#ffffff",
  "Steinbruch": "#ffffff",
  "Kiesgrube": "#ffffff",
  "Deponie": "#ffffff",
  "uebriger_Abbau": "#ffffff"
}
```


Configuration
-------------

Environment variables:

| Variable                  | Description                                             |
|---------------------------|---------------------------------------------------------|
| `JWT_SECRET_KEY`          | JWT secret key for token based authentication, shared with QWC Services |
| `GEODB_URL`               | GeoDB connection for info queries (default: `postgresql:///?service=sogis_services`) |
| `BASIC_INFO_SQL`          | SQL for basic info query                                |
| `BASIC_INFO_FIELDS`       | List of custom fields for basic plot info               |
| `FLURNAMEN_SQL`           | SQL for Flurnamen query                                 |
| `DETAILED_INFO_SQL`       | SQL for additional plot information query               |
| `LAND_COVER_FRACTIONS_SQL`| SQL for land cover fractions query                      |
| `BUILDING_ADDRESSES_SQL`  | SQL for building addresses query                        |
| `SDR_INFOS_LIEGENSCHAFT_SQL` | SQL for SDR for Liegenschaft query                   |
| `SDR_INFOS_SDR_SQL`       | SQL for Liegenschaften for SDR query                    |
| `LCSFC_COLORS`            | Lookup for custom land cover colors (default: see above)|
| `OEREB_JSON_URL`*         | ÖREB-Webservice URL for generating JSON                 |
| `OEREB_XML_URL`*          | ÖREB-Webservice URL for generating XML                  |
| `OEREB_PDF_URL`*          | ÖREB-Webservice URL for generating PDF                  |
| `GBDBS_SERVICE_URL`*      | GBDBS Service URL for requesting plot owner info XML    |
| `HIDE_OWNER_ADDRESSES`    | Hide addresses of plot owners (default: `False`)        |
| `RECAPTCHA_SITE_KEY`      | Public key for Google reCAPTCHA service                 |
| `RECAPTCHA_SECRET_KEY`    | Secret key for Google reCAPTCHA verification            |
| `RECAPTCHA_MIN_SCORE`     | Minimum reCAPTCHA score required (default: `0.5`)       |
| `GBDBS_VERSION`           | GBDBS version (default: `2.1`)                          |
| `BEZUG_INHALT`            | Value of BezugInhalt in the GBDBS request (default: IndexMitEigentum) |

* mandatory

See [Queries](#queries) for setting the query environment variables and their defaults.

Set the `OEREB_JSON_URL` environment variable to the full JSON ÖREB-Webservice URL with a placeholder for the EGRID,
e.g. 'http://example.com/main/oereb/extract/reduced/json/geometry/{egrid}'.

Set the `OEREB_XML_URL` environment variable to the full XML ÖREB-Webservice URL with a placeholder for the EGRID,
e.g. 'http://example.com/main/oereb/extract/reduced/xml/geometry/{egrid}'.

Set the `OEREB_PDF_URL` environment variable to the full PDF ÖREB-Webservice URL with a placeholder for the EGRID,
e.g. 'http://example.com/main/oereb/extract/reduced/pdf/geometry/{egrid}'.

Set the `GBDBS_SERVICE_URL` environment variable to the full GBDBS Service URL,
e.g. 'http://example.com/gbdbs/gbdbs'.

Set the `HIDE_OWNER_ADDRESSES` environment variable to `True` to hide all addresses of plot owners (default: `False`).

Set the `RECAPTCHA_SITE_KEY` and `RECAPTCHA_SECRET_KEY` environment variables to your Google reCAPTCHA keys.
Captcha verification for plot owner info is enabled if `RECAPTCHA_SITE_KEY` is set.

Set the `RECAPTCHA_MIN_SCORE` environment variable to the minimum reCAPTCHA score (`0.0` - `1.0`) required for viewing the plot owner info (default: `0.5`).

See [reCAPTCHA documentation](https://developers.google.com/recaptcha/docs/v3). Register keys [here](https://g.co/recaptcha/v3).


Usage
-----

Start PlotInfo service:

    OEREB_JSON_URL=... OEREB_XML_URL=... OEREB_PDF_URL=... GBDBS_SERVICE_URL=... python src/server.py

API documentation:

    http://localhost:5022/api/

Basic plot info:

    http://localhost:5022/?x=2607892&y=1228159

Additional plot info:

    http://localhost:5022/plot/CH870679603216

ÖREB JSON:

    http://localhost:5022/oereb/json/CH870679603216

ÖREB XML:

    http://localhost:5022/oereb/xml/CH870679603216

ÖREB PDF:

    http://localhost:5022/oereb/pdf/CH870679603216

Plot owner info:

    http://localhost:5022/plot_owner/CH870679603216

Get HTML with embedded captcha for plot owner info request (called from QWC2 PlotOwnerInfo):

    http://localhost:5022/plot_owner/captcha/CH870679603216

Plot owner info with captcha verification (called from QWC2 PlotOwnerInfo):

    http://localhost:5022/plot_owner/CH870679603216?token=<captcha_token>


Development
-----------

Install dependencies and run service:

    uv run src/server.py

With config path:

    CONFIG_PATH=/PATH/TO/CONFIGS/ uv run src/server.py
