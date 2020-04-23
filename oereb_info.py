import os

from flask import make_response, Response, stream_with_context
import requests


class OerebInfo:
    """OerebInfo class

    Get ÖREB XMLs and PDF reports.

    Uses an ÖREB-Webservice to get XMLs and an ÖREB PDF-Service
    to generate PDFs from these XMLs.
    """

    def __init__(self, logger):
        """Constructor

        :param Logger logger: Application logger
        """
        self.logger = logger

        # ÖREB-Webservice config
        self.oereb_json_url = os.getenv('OEREB_JSON_URL')
        self.oereb_xml_url = os.getenv('OEREB_XML_URL')
        self.oereb_pdf_url = os.getenv('OEREB_PDF_URL')
        if self.oereb_json_url is None:
            raise Exception("Environment variable OEREB_JSON_URL is not set")
        if self.oereb_xml_url is None:
            raise Exception("Environment variable OEREB_XML_URL is not set")
        if self.oereb_pdf_url is None:
            raise Exception("Environment variable OEREB_PDF_URL is not set")

    def xml(self, egrid):
        """Return ÖREB XML for EGRID.

        :param str egrid: EGRID
        """
        egrid = os.getenv('__OEREB_TEST_EGRID', egrid)
        try:
            # forward to ÖREB XML service
            req = self.xml_response(egrid)

            response = Response(
                stream_with_context(req.iter_content(chunk_size=1024)),
                status=req.status_code
            )
            if 'content-type' in req.headers:
                response.headers['content-type'] = req.headers['content-type']
        except Exception as e:
            self.logger.error(e)
            response = make_response(
                "<ServiceException>Internal error</ServiceException>"
            )
            response.headers['Content-Type'] = 'text/xml; charset=utf-8'

        return response

    def json(self, egrid):
        """Return ÖREB JSON for EGRID.

        :param str egrid: EGRID
        """
        egrid = os.getenv('__OEREB_TEST_EGRID', egrid)
        try:
            # forward to ÖREB JSON service
            req = self.json_response(egrid)

            response = Response(
                stream_with_context(req.iter_content(chunk_size=1024)),
                status=req.status_code
            )
            if 'content-type' in req.headers:
                response.headers['content-type'] = req.headers['content-type']
        except Exception as e:
            self.logger.error(e)
            response = {
                'error': str(e),
                'success': False
            }

        return response

    def pdf(self, egrid):
        """Return ÖREB PDF report for EGRID.

        Gets XML for EGRID from XML service and forwards it to the PDF service.

        :param str egrid: EGRID
        """
        egrid = os.getenv('__OEREB_TEST_EGRID', egrid)
        try:
            # forward to ÖREB PDF service
            req = self.pdf_response(egrid)

            response = Response(
                stream_with_context(req.iter_content(chunk_size=1024)),
                status=req.status_code
            )
            if 'content-type' in req.headers:
                response.headers['content-type'] = req.headers['content-type']
            if 'content-disposition' in req.headers:
                response.headers['content-disposition'] = req.headers[
                    'content-disposition']
        except Exception as e:
            self.logger.error(e)
            response = Response(
                '{"message": "Internal error"}',
                content_type='application/json; charset=utf-8',
                status=500
            )

        return response

    def xml_response(self, egrid):
        """Send XML request to ÖREB XML service and return response.

        :param str egrid: EGRID
        """
        url = self.oereb_xml_url.format(egrid=egrid)
        headers = {
            'accept': 'application/xml'
        }
        self.logger.info("Forward XML request to %s", url)
        return requests.get(url, headers=headers, timeout=120, stream=True)

    def json_response(self, egrid):
        """Send JSON request to ÖREB JSON service and return response.

        :param str egrid: EGRID
        """
        url = self.oereb_json_url.format(egrid=egrid)
        headers = {
            'accept': 'application/json'
        }
        self.logger.info("Forward JSON request to %s", url)
        return requests.get(url, headers=headers, timeout=120, stream=True)

    def pdf_response(self, egrid):
        """Send PDF request to ÖREB PDF service and return response.

        :param str egrid: EGRID
        """
        url = self.oereb_pdf_url.format(egrid=egrid)
        headers = {
            'accept': 'application/pdf'
        }
        self.logger.info("Forward PDF request to %s", url)
        return requests.get(url, headers=headers, timeout=120, stream=True)
