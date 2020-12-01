from xml.dom.minidom import parseString

from flask import Response, stream_with_context
import requests
from sqlalchemy.sql import text as sql_text
from qwc_services_core.tenant_handler import TenantHandler
from plot_info import PlotInfo


class LandRegExtract:
    """LandRegExtract class

    Land registrer extract as a PDF.
    """

    def __init__(self, config_handler, db_engine, logger):
        """Constructor

        :param DatabaseEngine db_engine: Database engine with DB connections
        :param Logger logger: Application logger
        """
        self.config_handler = config_handler
        self.db_engine = db_engine
        self.logger = logger

    def pdf(self, egrid):
        """Submit query

        Return map print
        """
        tenant_handler = TenantHandler(self.logger)
        tenant = tenant_handler.tenant()
        config = self.config_handler.tenant_config(tenant)

        project = config.get("landreg_project", "grundbuch")
        qgis_server_url = config.get('qgis_server_url')

        # Available print templates and sizes
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetProjectSettings",
        }

        url = qgis_server_url.rstrip("/") + "/" + project
        req = requests.get(url, params=params)

        layouts = {}
        try:
            capabilities = parseString(req.text)
            templates = capabilities.getElementsByTagName("WMS_Capabilities")[0]\
                                    .getElementsByTagName("Capability")[0]\
                                    .getElementsByTagName("ComposerTemplates")[0]
            for template in templates.getElementsByTagName("ComposerTemplate"):
                name = template.getAttribute("name")
                composerMap = template.getElementsByTagName("ComposerMap")[0]
                layouts[name] = {
                    "width": float(composerMap.getAttribute("width")),
                    "height": float(composerMap.getAttribute("height")),
                    "mapname": composerMap.getAttribute("name")
                }
        except Exception as e:
            return {
                'error': 'Failed to query layouts: ' + str(e),
                'success': False
            }

        # Specified print template
        template = config.get("landreg_print_template")
        crs = config.get("landreg_srs", "EPSG:2056")
        try:
            layout = layouts[template]
        except:
            return {
                'error': 'Invalid template specified: ' + template,
                'success': False
            }

        # Prapare params for print
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetPrint",
            "FORMAT": "PDF",
            "TEMPLATE": template,
            "DPI": str(config.get("landreg_dpi", "300")),
            "SRS": crs,
            "map0:GRID_INTERVAL_X": str(config.get("landreg_grid_x", "")),
            "map0:GRID_INTERVAL_Y": str(config.get("landreg_grid_y", "")),
            "LAYERS": config.get("landreg_print_layer", ""),
            "OPACITIES": config.get("landreg_print_layer_opacities", "")
        }
        if not params["OPACITIES"]:
            params["OPACITIES"] = ",".join( map(lambda item: "255", params["LAYERS"].split(",")))

        # Determine extent and scale
        basic_info_by_egrid_sql = config.get(
            'basic_info_by_egrid_sql', PlotInfo.DEFAULT_BASIC_INFO_BY_EGRID_SQL
        )

        conn = None
        try:
            db = self.db_engine.db_engine(config.get('db_url'))
            sql = sql_text(basic_info_by_egrid_sql)
            conn = db.connect()
            result = conn.execute(
                sql, egrid=egrid, srid=int(crs.replace("EPSG:", "")), buffer=1
            )
            row = result.fetchone()
            if row is None:
                return {
                    'error': 'EGRID not found: ' + egrid,
                    'success': False
                }
            bbox = [float(row['xmin']), float(row['ymin']), float(row['xmax']), float(row['ymax'])]
        except Exception as e:
            self.logger.error(e)
            return {
                'error': str(e),
                'success': False
            }
        finally:
            if conn:
                conn.close()

        # Compute actual scale
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        scale_w = (layout["width"] / 1000) / width
        scale_h = (layout["height"] / 1000) / height
        scale_fitw = scale_w < scale_h
        scaleden = 1. / min(scale_w, scale_h)

        # Fit to allowed scales
        allowed_scale_denoms = config.get("landreg_allowed_scale_denoms", [])
        if allowed_scale_denoms:
            # Minimal allowed scale greater or equal scaleden
            try:
                fitscaleden = next(x for x in allowed_scale_denoms if x >= scaleden)
            except:
                fitscaleden = allowed_scale_denoms[len(allowed_scale_denoms) - 1]
            factor = fitscaleden / scaleden
            center = [0.5 * (bbox[0] + bbox[2]), 0.5 * (bbox[1] + bbox[3])]
            # Scale bounding box, while preserving layout aspect ratio
            if scale_fitw:
                newwidth = factor * width
                newheight = newwidth * layout["height"] / layout["width"]
            else:
                newheight = factor * height
                newwidth = newheight * layout["width"] / layout["height"]

            bbox = [
                center[0] - 0.5 * newwidth,
                center[1] - 0.5 * newheight,
                center[0] + 0.5 * newwidth,
                center[1] + 0.5 * newheight
            ]

        params[layout["mapname"] + ":EXTENT"] = ",".join(map(str, bbox))
        params[layout["mapname"] + ":SCALE"] = str(round(fitscaleden))

        # Determine extra print params
        extra_labels = config.get("landreg_extra_labels", {})
        if extra_labels:
            conn = None
            try:
                db = self.db_engine.db_engine(config.get('db_url'))
                sql = sql_text(extra_labels["query"])
                conn = db.connect()
                result = conn.execute(
                    sql, egrid=egrid, srid=int(crs.replace("EPSG:", "")), x=(0.5 * (bbox[0] + bbox[2])), y=(0.5 * (bbox[1] + bbox[3])), xmin=bbox[0], ymin=bbox[1], xmax=bbox[2], ymax=bbox[3]
                )
                row = result.fetchone()
                if row is not None:
                    for label in extra_labels["fields"]:
                        params[label.upper()] = row[label]
            except Exception as e:
                return {
                    'error': "Error querying extra fields: " + str(e),
                    'success': False
                }
            finally:
                if conn:
                    conn.close()

        # Forward to QGIS server
        url = qgis_server_url.rstrip("/") + "/" + project
        req = requests.post(url, timeout=120, data=params)
        self.logger.info("Forwarding request to %s\n%s" % (req.url, params))

        response = Response(
            stream_with_context(
                req.iter_content(chunk_size=1024)
            ), status=req.status_code
        )
        response.headers['content-type'] = req.headers['content-type']
        if req.headers['content-type'] == 'application/pdf':
            response.headers['content-disposition'] = \
                'attachment; filename=' + project + '.' + params['FORMAT'].lower()

        return response

