import os

from flask import Flask, jsonify
from flask_restx import reqparse, Resource

from oereb_info import OerebInfo
from plot_info import PlotInfo
from plot_owner import PlotOwner
from land_reg import LandRegExtract

from qwc_services_core.api import Api, CaseInsensitiveArgument
from qwc_services_core.app import app_nocache
from qwc_services_core.auth import auth_manager, optional_auth, get_identity
from qwc_services_core.database import DatabaseEngine
from qwc_services_core.runtime_config import RuntimeConfig


# Flask application
app = Flask(__name__)
app_nocache(app)
api = Api(app, version='1.0', title='PlotInfo service API',
          description="""API for SO!MAP PlotInfo service.

Query additional plot information at a geographic position and create \
PDF reports for them.

Grundstücksinformation:
  * Basisinformationen
  * Amtliche Vermessung
  * ÖREB-Kataster
          """,
          default_label='PlotInfo operations', doc='/api/')
app.config.SWAGGER_UI_DOC_EXPANSION = 'list'

# disable verbose 404 error message
app.config['ERROR_404_HELP'] = False

# setup the Flask-JWT-Extended extension
jwt = auth_manager(app)

config_handler = RuntimeConfig("plotinfo", app.logger)
db_engine = DatabaseEngine()

# create plot info
plot_info = PlotInfo(config_handler, db_engine, app.logger)
# create ÖREB info
oereb_info = OerebInfo(config_handler, app.logger)
# create plot owner info
plot_owner = PlotOwner(config_handler, db_engine, app.logger)
# create land register extract
land_reg = LandRegExtract(config_handler, db_engine, app.logger)

# request parser
pos_parser = reqparse.RequestParser(argument_class=CaseInsensitiveArgument)
pos_parser.add_argument('x', type=float, required=True)
pos_parser.add_argument('y', type=float, required=True)

plot_owner_parser = reqparse.RequestParser(argument_class=CaseInsensitiveArgument)
plot_owner_parser.add_argument('token')


# routes
@api.route('/', endpoint='root')
class QueryPos(Resource):
    @api.param('x', 'X coordinate in LV95', required=True)
    @api.param('y', 'Y coordinate in LV95', required=True)
    @api.expect(pos_parser)
    def get(self):
        """Basic plot info

        Return basic plot information at coordinates.
        """
        args = pos_parser.parse_args()
        return plot_info.basic_info(args['x'], args['y'])


@api.route('/query/<egrid>')
class QueryEgrid(Resource):
    @api.param('egrid', 'EGRID', required=True)
    def get(self, egrid):
        """Basic plot info

        Return basic plot information by egrid.
        """
        return plot_info.basic_info_egrid(egrid)


@api.route('/plot/<egrid>')
@api.param('egrid', 'EGRID')
class QueryPlot(Resource):
    def get(self, egrid):
        """Detailed plot info

        Return additional plot information for EGRID.
        """
        return plot_info.detailed_info(egrid)


@api.route('/oereb/xml/<egrid>')
@api.param('egrid', 'EGRID')
class OerebXML(Resource):
    def get(self, egrid):
        """Get ÖREB XML

        Return ÖREB XML for EGRID.
        """
        return oereb_info.xml(egrid)


@api.route('/oereb/json/<egrid>')
@api.param('egrid', 'EGRID')
class OerebJSON(Resource):
    def get(self, egrid):
        """Get ÖREB JSON

        Return ÖREB JSON for EGRID.
        """
        return oereb_info.json(egrid)


@api.route('/oereb/pdf/<egrid>')
@api.param('egrid', 'EGRID')
class OerebPDF(Resource):
    def get(self, egrid):
        """Get ÖREB PDF

        Return ÖREB PDF report for EGRID.
        """
        return oereb_info.pdf(egrid)


@api.route('/plot_owner/captcha/<egrid>')
@api.param('egrid', 'EGRID')
class PlotOwnerCaptcha(Resource):
    def get(self, egrid):
        """Plot owner

        Return HTML with embedded captcha for plot owner info request.
        """
        return plot_owner.captcha(egrid)


@api.route('/plot_owner/<egrid>')
@api.param('egrid', 'EGRID')
class PlotOwner(Resource):
    @api.param('token', 'reCAPTCHA response token')
    @api.expect(plot_owner_parser)
    @optional_auth
    def get(self, egrid):
        """Plot owner

        Return additional plot owner information for EGRID.
        """
        args = plot_owner_parser.parse_args()
        return plot_owner.info(get_identity(), egrid, args['token'])


@api.route('/landreg/<egrid>')
@api.param('egrid', 'EGRID')
class LandReg(Resource):
    def get(self, egrid):
        """Land register extract

        Returns the land register extract for the specified egrid as PDF
        """
        return land_reg.pdf(egrid)


""" readyness probe endpoint """
@app.route("/ready", methods=['GET'])
def ready():
    return jsonify({"status": "OK"})


""" liveness probe endpoint """
@app.route("/healthz", methods=['GET'])
def healthz():
    return jsonify({"status": "OK"})


# local webserver
if __name__ == '__main__':
    print("Starting PlotInfo service...")
    app.run(host='localhost', port=os.environ.get("FLASK_RUN_PORT", 5000), debug=True)
