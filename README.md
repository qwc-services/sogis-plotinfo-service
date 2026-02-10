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


Configuration
-------------

The static config files are stored as JSON files in `$CONFIG_PATH` with subdirectories for each tenant,
e.g. `$CONFIG_PATH/default/*.json`. The default tenant name is `default`.

### Plotinfo Service config

* [JSON schema](schemas/sogis-plotinfo-service.json)
* File location: `$CONFIG_PATH/<tenant>/plotinfoConfig.json`

Example:

```json
  "config": {
    "oereb_json_url": "http://example.com/main/oereb/extract/reduced/json/geometry/{egrid}",
    "oereb_xml_url": "http://example.com/main/oereb/extract/reduced/xml/geometry/{egrid}",
    "oereb_pdf_url": "http://example.com/main/oereb/extract/reduced/pdf/geometry/{egrid}",
    "gbdbs_service_url": "http://example.com/gbdbs/gbdbs",
    "basic_info_sql": "<see below>",
    "basic_info_fields": "<see below>",
    "flurnamen_sql": "<see below>",
    "detailed_info_sql": "<see below>",
    "land_cover_fractions_sql": "<see below>",
    "building_addresses_sql": "<see below>",
    "sdr_infos_liegenschaft_sql": "<see below>",
    "sdr_infos_sdr_sql": "<see below>",
    "lcsfc_colors": "<see below>"
  }
```

See [Queries](#queries) for setting the query environment variables and their defaults.

Set `oereb_json_url` to the full JSON ÖREB-Webservice URL with a placeholder for the EGRID.

Set `oereb_xml_url` to the full XML ÖREB-Webservice URL with a placeholder for the EGRID.

Set `oereb_pdf_url` to the full PDF ÖREB-Webservice URL with a placeholder for the EGRID.

Set `gbdbs_service_url` to the full GBDBS Service URL.

Set `hide_owner_addresses` to `true` to hide all addresses of plot owners (default: `false`).

Set `recaptcha_site_key` and `recaptcha_secret_key` to your Google reCAPTCHA keys.
Captcha verification for plot owner info is enabled if `recaptcha_site_key` is set.

Set `recaptcha_min_score` to the minimum reCAPTCHA score (`0.0` - `1.0`) required for viewing the plot owner info (default: `0.5`).

See [reCAPTCHA documentation](https://developers.google.com/recaptcha/docs/v3). Register keys [here](https://g.co/recaptcha/v3).


### Environment variables

Config options in the config file can be overridden by equivalent uppercase environment variables.


Queries
-------

### Basic plot info

**SQL for basic info query:**

* config: `basic_info_sql`
* input: `x`, `y`, `srid`, `buffer`
* output: `egrid`, `nummer`, `art_txt`, optional custom fields (see `basic_info_fields`)

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

Custom info fields for basic info query can be set via `basic_info_fields` as list of `[{"<query field>": "<label>"}]`.

Add these query fields to the SELECT fields in the `basic_info_sql` query.

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

**SQL for Flurnamen query for plot with EGRID:**

* config: `flurnamen_sql`
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

**SQL for additional plot information query for EGRID:**

* config: `detailed_info_sql`
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

**SQL for querying land cover fractions inside plot with EGRID:**

* ENV: `land_cover_fractions_sql`
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

**SQL for querying building addresses inside plot with EGRID:**

* config: `building_addresses_sql`
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

**SQL for querying SDR infos for Liegenschaft plot (`art == 0`) with EGRID:**

* config: `sdr_infos_liegenschaft_sql`
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

**SQL for querying Liegenschaften infos for SDR plot (`art != 0`) with EGRID:**

* config: `sdr_infos_sdr_sql`
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

An optional lookup for custom land cover colors can be set via `lcsfc_colors` as a dict `{"<type>": "<CSS color>"}`.

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

Run locally
-----------

Install dependencies and run:

    export CONFIG_PATH=<CONFIG_PATH>
    uv run src/server.py

To use configs from a `qwc-docker` setup, set `CONFIG_PATH=<...>/qwc-docker/volumes/config`.

Set `FLASK_DEBUG=1` for additional debug output.

Set `FLASK_RUN_PORT=<port>` to change the default port (default: `5000`).

API documentation:

    http://localhost:5000/api/

Examples:

    # Basic plot info
    http://localhost:5000/?x=2607892&y=1228159

    # Additional plot info
    http://localhost:5000/plot/CH870679603216

    # ÖREB JSON
    http://localhost:5000/oereb/json/CH870679603216

    # ÖREB XML
    http://localhost:5000/oereb/xml/CH870679603216

    # ÖREB PDF
    http://localhost:5000/oereb/pdf/CH870679603216

    # Plot owner info
    http://localhost:5000/plot_owner/CH870679603216

    # Get HTML with embedded captcha for plot owner info request (called from QWC PlotOwnerInfo plugin):
    http://localhost:5000/plot_owner/captcha/CH870679603216

    # Plot owner info with captcha verification (called from QWC PlotOwnerInfo plugin):
    http://localhost:5000/plot_owner/CH870679603216?token=<captcha_token>
    
Docker usage
------------

The Docker image is published on [Dockerhub](https://hub.docker.com/r/sourcepole/sogis-plotinfo-service).

See sample [docker-compose.yml](https://github.com/qwc-services/qwc-docker/blob/master/docker-compose-example.yml) of [qwc-docker](https://github.com/qwc-services/qwc-docker).
