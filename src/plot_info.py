from flask import json, render_template, Response
from sqlalchemy.sql import text as sql_text
from qwc_services_core.tenant_handler import TenantHandler


class PlotInfo:
    """PlotInfo class

    Query basic and additional plot information from GeoDB.
    """

    # CRS of query position
    QUERY_SRID = 2056

    # buffer around query position in m
    QUERY_BUFFER = 1

    """SQL for basic info query
    input: x, y, srid, buffer
    output: egrid, custom fields (see BASIC_INFO_FIELDS)
    """
    DEFAULT_BASIC_INFO_SQL = """
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
    """

    DEFAULT_BASIC_INFO_BY_EGRID_SQL = """
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
        WHERE g.egrid = :egrid
    """

    # custom info fields as [{<query field>: <label>}]
    DEFAULT_BASIC_INFO_FIELDS = [
        {'gemeinde': 'Gemeinde'},
        {'grundbuch': 'Grundbuch'},
        {'nummer': 'Nummer'},
        {'egrid': 'E-GRID'},
        {'flaechenmass': 'Fläche'},
        {'art_txt': 'Art'}
    ]

    """SQL for Flurnamen query
    input: egrid
    output: flurname
    """
    DEFAULT_FLURNAMEN_SQL = """
        SELECT
            f.flurname
        FROM
            agi_mopublic_pub.mopublic_flurname f
            JOIN agi_mopublic_pub.mopublic_grundstueck g
                ON ST_Intersects(f.geometrie, g.geometrie)
                AND NOT ST_Touches(f.geometrie, g.geometrie)
        WHERE g.egrid = :egrid
        ORDER BY f.flurname;
    """

    """SQL for additional plot information query
    input: egrid
    output: flaechenmass, art, art_txt, grundbuchamt, nfgeometer
    """
    DEFAULT_DETAILED_INFO_SQL = """
        SELECT
            g.flaechenmass, g.art, 'TODO' AS grundbuchamt, 'TODO' AS nfgeometer
        FROM
            agi_mopublic_pub.mopublic_grundstueck g
        WHERE g.egrid = :egrid LIMIT 1;
    """

    """SQL for querying land cover fractions inside plot
    input: egrid
    output: area, area_percent, art, art_txt
    """
    DEFAULT_LAND_COVER_FRACTIONS_SQL = """
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
    """

    """SQL for querying building addresses inside plot
    input: egrid
    output: strassenname, hausnummer, plz, ortschaft
    """
    DEFAULT_BUILDING_ADDRESSES_SQL = """
        SELECT
            a.strassenname, a.hausnummer, a.plz, a.ortschaft
        FROM
            agi_mopublic_pub.mopublic_gebaeudeadresse a
            JOIN agi_mopublic_pub.mopublic_grundstueck g
                ON ST_Contains(g.geometrie, a.lage)
        WHERE g.egrid = :egrid
        ORDER BY a.strassenname, a.hausnummer;
    """

    """SQL for querying SDR infos for Liegenschaft plot
    input: egrid
    output: nummer, art, art_txt, area
    """
    DEFAULT_SDR_INFOS_LIEGENSCHAFT_SQL = """
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
    """

    """SQL for querying Liegenschaften infos for SDR plot
    input: egrid
    output: nummer, art, art_txt, area
    """
    DEFAULT_SDR_INFOS_SDR_SQL = """
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
    """

    # lookup for land cover colors
    DEFAULT_LCSFC_COLORS = {
        'Gebaeude': '#ffc8c8',
        # befestigt
        'Strasse_Weg': '#dcdcdc',
        'Trottoir': '#dcdcdc',
        'Verkehrsinsel': '#dcdcdc',
        'Bahn': '#f0e6c8',
        'Flugplatz': '#dcdcdc',
        'Wasserbecken': '#96c8ff',
        'uebrige_befestigte': '#f0f0f0',
        'Sportanlage_befestigt': '#f0f0f0',
        'Lagerplatz': '#f0f0f0',
        'Boeschungsbauwerk': '#f0f0f0',
        'Gebaeudeerschliessung': '#f0f0f0',
        'Parkplatz': '#f0f0f0',
        # humusiert
        'Acker_Wiese_Weide': '#f0ffc8',
        'Acker_Wiese': '#f0ffc8',
        'Weide': '#f0ffc8',
        'Reben': '#ffffc8',
        'uebrige_Intensivkultur': '#ffffc8',
        'Obstkultur': '#ffffc8',
        'Gartenanlage': '#f0ffc8',
        'Hoch_Flachmoor': '#c8fff0',
        'uebrige_humusierte': '#f0ffc8',
        'Parkanlage_humusiert': '#f0ffc8',
        'Sportanlage_humusiert': '#f0ffc8',
        'Friedhof': '#f0ffc8',
        # Gewaesser
        'stehendes': '#96c8ff',
        'stehendes Gewaesser': '#96c8ff',
        'fliessendes': '#96c8ff',
        'fliessendes Gewaesser': '#96c8ff',
        'Schilfguertel': '#c8fff0',
        # bestockt
        'geschlossener_Wald': '#a0f0a0',
        'uebrige_bestockte': '#c8f0a0',
        'Parkanlage_bestockt': '#c8f0a0',
        'Hecke': '#c8f0a0',
        # vegetationslos
        'Fels': '#ffffff',
        'Gletscher_Firn': '#ffffff',
        'Geroell_Sand': '#ffffff',
        'Abbau_Deponie': '#ffffff',
        'uebrige_vegetationslose': '#ffffff',
        'Steinbruch': '#ffffff',
        'Kiesgrube': '#ffffff',
        'Deponie': '#ffffff',
        'uebriger_Abbau': '#ffffff'
    }

    def __init__(self, config_handler, db_engine, logger):
        """Constructor

        :param DatabaseEngine db_engine: Database engine with DB connections
        :param Logger logger: Application logger
        """
        self.config_handler = config_handler
        self.db_engine = db_engine
        self.logger = logger

    def load_config(self):
        tenant_handler = TenantHandler(self.logger)
        tenant = tenant_handler.tenant()
        config = self.config_handler.tenant_config(tenant)

        db_url = config.get('db_url', 'postgresql:///?service=sogis_services')
        self.db = self.db_engine.db_engine(db_url)

        # BASIC_INFO_SQL
        self.basic_info_sql = config.get(
            'basic_info_sql', self.DEFAULT_BASIC_INFO_SQL)
        self.basic_info_by_egrid_sql = config.get(
            'basic_info_by_egrid_sql', self.DEFAULT_BASIC_INFO_BY_EGRID_SQL
        )

        # BASIC_INFO_FIELDS
        basic_info_fields = config.get(
            'basic_info_fields', self.DEFAULT_BASIC_INFO_FIELDS)
        self.basic_info_fields = []
        for field in basic_info_fields:
            try:
                (name, label), = field.items()
                self.basic_info_fields.append((name, label))
            except Exception as e:
                self.logger.error(
                    "Could not get custom info field from '%s':\n%s"
                    % (field, e)
                )

        # FLURNAMEN_SQL
        self.flurnamen_sql = config.get(
            'flurnamen_sql', self.DEFAULT_FLURNAMEN_SQL
        )

        # DETAILED_INFO_SQL
        self.detailed_info_sql = config.get(
            'detailed_info_sql', self.DEFAULT_DETAILED_INFO_SQL
        )

        # LAND_COVER_FRACTIONS_SQL
        self.land_cover_fractions_sql = config.get(
            'land_cover_fractions_sql', self.DEFAULT_LAND_COVER_FRACTIONS_SQL
        )

        # BUILDING_ADDRESSES_SQL
        self.building_addresses_sql = config.get(
            'building_addresses_sql', self.DEFAULT_BUILDING_ADDRESSES_SQL
        )

        # SDR_INFOS_LIEGENSCHAFT_SQL
        self.sdr_infos_liegenschaft_sql = config.get(
            'sdr_infos_liegenschaft_sql',
            self.DEFAULT_SDR_INFOS_LIEGENSCHAFT_SQL
        )

        # SDR_INFOS_SDR_SQL
        self.sdr_infos_sdr_sql = config.get(
            'sdr_infos_sdr_sql', self.DEFAULT_SDR_INFOS_SDR_SQL
        )

        # LCSFC_COLORS
        self.lcsfc = config.get(
            'lcsfc_colors', self.DEFAULT_LCSFC_COLORS
        )

    def basic_info(self, x, y):
        """Return basic plot information at coordinates as JSON.

        :param float x: X coordinate in LV95
        :param float y: Y coordinate in LV95
        """
        self.load_config()
        try:
            sql = sql_text(self.basic_info_sql)

            conn = self.db.connect()

            result = conn.execute(
                sql, {"x": x, "y": y, "srid": self.QUERY_SRID, "buffer": self.QUERY_BUFFER}
            )
            plots = self.format_basic_info(result, conn)
            conn.close()

            return {
                'plots': plots,
                'success': True
            }
        except Exception as e:
            self.logger.error(e)
            return {
                'error': str(e),
                'success': False
            }

    def basic_info_egrid(self, egrid):
        """Return basic plot information given the plot EGRID.

        :param string egrid: The plot EGRID
        """
        self.load_config()
        try:
            sql = sql_text(self.basic_info_by_egrid_sql)

            conn = self.db.connect()

            result = conn.execute(
                sql, {"egrid": egrid, "srid": self.QUERY_SRID, "buffer": self.QUERY_BUFFER}
            )
            plots = self.format_basic_info(result, conn)
            conn.close()

            return {
                'plots': plots,
                'success': True
            }
        except Exception as e:
            self.logger.error(e)
            return {
                'error': str(e),
                'success': False
            }

    def format_basic_info(self, result, conn):
        """ Format the basic info results. """
        plots = []
        for row in result:
            # get values for custom fields
            fields = []
            for name, label in self.basic_info_fields:
                if name == '_flurnamen_':
                    # custom query for Flurnamen
                    value = ", ".join(
                        self.get_flurnamen(row.egrid, conn)
                    )
                elif name == 'flaechenmass':
                    # custom format for area
                    value = "%s m<sup>2</sup>" % self.format_number(row.flaechenmass)
                elif name in row._mapping:
                    # value from basic info query
                    value = getattr(row, name)
                else:
                    self.logger.warning(
                        "Missing field '%s' in query result" % name
                    )
                    value = "ERROR"

                fields.append({
                    'key': label,
                    'value': value
                })

            plots.append({
                'egrid': row.egrid,
                'label': "%s Nr. %s" % (row.art_txt, row.nummer),
                'fields': fields,
                'geom': row.geom,
                'bbox': [row.xmin, row.ymin, row.xmax, row.ymax]
            })
        return plots

    def detailed_info(self, egrid):
        """Return additional plot information for EGRID as HTML.

        :param str egrid: EGRID
        """
        self.load_config()
        try:
            info = {}

            sql = sql_text(self.detailed_info_sql)

            conn = self.db.connect()

            result = conn.execute(sql, {"egrid": egrid})
            for row in result:
                land_cover = self.get_land_cover_fractions(egrid, conn)

                # calculate rounding difference to flaechenmass
                total_area = 0
                for lc in land_cover:
                    total_area += round(lc['area'])
                rounding_difference = abs(
                    round(row.flaechenmass) - total_area
                )

                info = {
                    'egrid': egrid,
                    'area': row.flaechenmass,
                    'landcover': land_cover,
                    'rounding_difference': rounding_difference,
                    'flurnamen': ", ".join(self.get_flurnamen(egrid, conn)),
                    'addresses': self.get_building_addresses(egrid, conn),
                    'sdr': self.get_sdr_infos(egrid, row.art, conn),
                    'grundbuchamt': row.grundbuchamt,
                    'nfgeometer': row.nfgeometer
                }

            conn.close()

            if not info:
                return Response(
                    "<div><h3>EGRID %s not found</h3></div>" % egrid,
                    content_type='text/html; charset=utf-8',
                    status=404
                )

            # get pie chart
            pie_chart = self.chartist_pie_chart(info.get('landcover'))

            html = render_template(
                'detailed_info.html', info=info, pie_chart=pie_chart,
                lcsfc_colors=self.lcsfc, format_number=self.format_number
            )

            return Response(
                html,
                content_type='text/html; charset=utf-8',
            )
        except Exception as e:
            self.logger.error(e)
            return Response(
                "<div><h3>Error</h3>%s</div>" % str(e),
                content_type='text/html; charset=utf-8',
                status=500
            )

    def get_flurnamen(self, egrid, conn):
        """Get Flurnamen for plot with EGRID.

        :param str egrid: EGRID
        :param Connection conn: DB connection
        """
        flurnamen = []

        sql = sql_text(self.flurnamen_sql)

        result = conn.execute(sql, {"egrid": egrid})
        for row in result:
            flurnamen.append(row.flurname)

        return flurnamen

    def get_land_cover_fractions(self, egrid, conn):
        """Get land cover fractions inside plot with EGRID.

        :param str egrid: EGRID
        :param Connection conn: DB connection
        """
        land_cover = []

        sql = sql_text(self.land_cover_fractions_sql)

        result = conn.execute(sql, {"egrid": egrid})
        for row in result:
            # lookup color
            lcsfc = self.lcsfc.get(row.art_txt, '#ffffff')

            if round(row.area, 0) == 0:
                continue

            land_cover.append({
                'type': row.art_txt,
                'area': row.area,
                'area_percent': row.area_percent,
                'color': lcsfc
            })

        return land_cover

    def get_building_addresses(self, egrid, conn):
        """Get building addresses inside plot with EGRID.

        :param str egrid: EGRID
        :param Connection conn: DB connection
        """
        addresses = []

        sql = sql_text(self.building_addresses_sql)

        result = conn.execute(sql, {"egrid": egrid})
        for row in result:
            addresses.append({
                'street': row.strassenname,
                'number': row.hausnummer,
                'zip': row.plz,
                'city': row.ortschaft
            })

        return addresses

    def get_sdr_infos(self, egrid, plot_type, conn):
        """Get any SDR infos for plot with EGRID.

        :param str egrid: EGRID
        :param int plot_type: Type of plot (0: Liegenschaft, else SDR)
        :param Connection conn: DB connection
        """
        sdr_infos = []

        if plot_type == 0:
            # Liegenschaft: get SDRs

            sql = sql_text(self.sdr_infos_liegenschaft_sql)

            result = conn.execute(sql, {"egrid": egrid})
            for row in result:
                sdr_infos.append({
                    'number': row.nummer,
                    'type': row.art_txt,
                    'area': row.area
                })
        else:
            # SDR: get Liegenschaften

            sql = sql_text(self.sdr_infos_sdr_sql)

            result = conn.execute(sql, {"egrid": egrid})
            for row in result:
                sdr_infos.append({
                    'number': row.nummer,
                    'type': row.art_txt,
                    'area': row.area
                })

        return sdr_infos

    def chartist_pie_chart(self, land_cover):
        """Return Chartist config for pie chart for land cover fractions.

        :param list[obj] land_cover: Land cover fractions
        """
        # collect values
        series = []
        labels = []
        for land in land_cover:
            value = round(land['area_percent'], 1)
            series.append({
                'value': value,
                'className': "lcsfc-%s" % land['type']
            })
            labels.append("%s %s%%" % (land['type'], value))

        return {
            'series': series,
            'labels': labels
        }

    def format_number(self, value):
        """Add thousands separator to number value.

        :param float value: Number value
        """
        return '{0:,}'.format(value).replace(",", "'")
