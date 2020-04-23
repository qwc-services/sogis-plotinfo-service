import os
import sys

from flask import Flask
from flask_restplus import reqparse, Resource

from oereb_info import OerebInfo
from plot_info import PlotInfo
from plot_owner import PlotOwner

# add parent dir to path, so shared modules can be imported
path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../'))
sys.path.insert(1, path)

from service_lib.api import Api, CaseInsensitiveArgument  # noqa: E402
from service_lib.app import app_nocache  # noqa: E402
from service_lib.database import DatabaseEngine  # noqa: E402


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

# create DB engine
db_engine = DatabaseEngine()

# create plot info
plot_info = PlotInfo(db_engine, app.logger)
# create ÖREB info
oereb_info = OerebInfo(app.logger)
# create plot owner info
plot_owner = PlotOwner(db_engine, app.logger)

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
    def get(self, egrid):
        """Plot owner

        Return additional plot owner information for EGRID.
        """
        args = plot_owner_parser.parse_args()
        return plot_owner.info(egrid, args['token'])


# local webserver
if __name__ == '__main__':
    print("Starting PlotInfo service...")
    app.run(host='localhost', port=5022, debug=True)
