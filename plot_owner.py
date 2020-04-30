from datetime import datetime
from xml.dom.minidom import parseString

from flask import json, render_template, Response
import requests
from qwc_services_core.tenant_handler import TenantHandler


class PlotOwner:
    """PlotOwner class

    Query plot owner information from a GBDBS service.
    """

    EIGENTUMSFORM_LOOKUP = {
        'AlleinEigentum': "Alleineigentum",
        'GesamtEigentum': "Gesamteigentum",
        'MitEigentum': "Miteigentum",
        'GewoehnlichesMiteigentum': "Verselbständigtes Miteigentum",
        'StockwerksEinheit': "Stockwerkeigentum"
    }

    GBDBS_REQUEST_TEMPLATE = """
        <?xml version="1.0"?>
        <soapenv:Envelope
            xmlns:ns="http://schemas.geo.admin.ch/BJ/TGBV/GBDBS/2.1"
            xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
            <soapenv:Header/>
            <soapenv:Body>
                <ns:GetParcelsByIdRequest>
                    <ns:version>2.1</ns:version>
                    <ns:transactionId>{transaction_id}</ns:transactionId>
                    <ns:BezugInhalt>IndexMitEigentum</ns:BezugInhalt>
                    <ns:includeHistory>false</ns:includeHistory>
                    <ns:Id>{egrid}::::</ns:Id>
                </ns:GetParcelsByIdRequest>
            </soapenv:Body>
        </soapenv:Envelope>
    """

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

        self.gbdbs_service_url = config.get('gbdbs_service_url')
        self.hide_owner_addresses = config.get('hide_owner_addresses', False)
        self.site_key = config.get('recaptcha_site_key', '')
        self.secret_key = config.get('recaptcha_secret_key', '')

    def captcha(self, egrid):
        """Return HTML with embedded captcha for plot owner info request.

        :param str egrid: EGRID
        """
        self.load_config()
        return Response(
            render_template(
                'plot_owner_captcha.html', egrid=egrid, site_key=self.site_key
            ),
            content_type='text/html; charset=utf-8',
        )

    def verify_captcha(self, captcha_token):
        """Verify captcha response token.

        Only enabled if RECAPTCHA_SITE_KEY is set.

        :param str captcha_token: Captcha response token for verification
        """
        if self.site_key == '':
            # skip validation if captcha is not enabled
            self.logger.info(
                "RECAPTCHA_SITE_KEY is not set, skipping verification"
            )
            return True

        # send request to reCAPTCHA API
        self.logger.info("Verifying captcha response token")
        url = 'https://www.google.com/recaptcha/api/siteverify'
        params = {
            'secret': self.secret_key,
            'response': captcha_token
        }
        response = requests.post(
            url, data=params, timeout=60
        )

        if response.status_code != requests.codes.ok:
            # handle server error
            self.logger.error(
                "Could not verify captcha response token:\n\n%s" %
                response.text
            )
            return False

        # check response
        res = json.loads(response.text)
        if res['success']:
            self.logger.info("Captcha verified")
            return True
        else:
            self.logger.warning("Captcha verification failed: %s" % res)

        return False

    def info(self, egrid, captcha_token):
        """Return flattened plot owner information for EGRID as JSON.

        :param str egrid: EGRID
        :param str captcha_token: Captcha response token for verification
        """
        self.load_config()
        try:
            if not self.verify_captcha(captcha_token):
                return {
                    'error': "Captcha verification failed",
                    'success': False
                }

            owner_info = self.get_owner_info(egrid)
            if 'error' in owner_info:
                raise Exception(owner_info['error'])

            grundstuecke = owner_info.get('grundstuecke')
            personen = owner_info.get('personen')
            rechte = owner_info.get('rechte')

            # get Grundstueck info for EGRID
            grundstueck = None
            for id, g in grundstuecke.items():
                if g.get('egrid') == egrid:
                    grundstueck = g
                    break

            if grundstueck is None:
                return {
                    'error': "EGRID %s not found" % egrid,
                    'success': False
                }

            # collect eigentuemer info
            eigentum = self.collect_eigentuemer(
                grundstueck, rechte, personen, grundstuecke, True
            )

            # update eigentumsform
            eigentumsform = self.lookup_eigentumsform(
                eigentum.get('eigentumsform')
            )
            if eigentum.get('eigentum_art') == 'StockwerksEinheit':
                eigentumsform = (
                    "%s (%s)" % (
                        eigentumsform,
                        self.lookup_eigentumsform(eigentum.get('eigentum_art'))
                    )
                )

            # result
            result = {
                'grundstueck': eigentum.get('grundstueck'),
                'eigentumsform': eigentumsform,
                'eigentuemer': eigentum.get('eigentuemer'),
            }
            if 'beschreibung' in eigentum:
                result['beschreibung'] = eigentum.get('beschreibung')

            return {
                'eigentum': result,
                'success': True
            }
        except Exception as e:
            self.logger.error(e)
            return {
                'error': str(e),
                'success': False
            }

    def get_owner_info(self, egrid):
        """Get owner info for EGRID from GBDBS service response.

        :param str egrid: EGRID
        """
        try:
            if self.gbdbs_service_url is None:
                raise Exception(
                    "Environment variable GBDBS_SERVICE_URL is not set"
                )

            # prepare GBDBS request XML
            transaction_id = (
                "SOMAP-%s" % datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
            )
            xml_data = self.GBDBS_REQUEST_TEMPLATE.format(
                transaction_id=transaction_id, egrid=egrid
            ).strip()

            # get XML from GBDBS service
            url = self.gbdbs_service_url
            headers = {
                'content-type': 'text/xml; charset=utf-8',
                'accept': 'application/xml'
            }
            self.logger.info(
                "POST GBDBS XML request to %s (%s)" % (url, egrid)
            )
            response = requests.post(
                url, data=xml_data, headers=headers, timeout=60
            )

            if response.status_code != requests.codes.ok:
                # handle server error
                raise Exception("GBDBS Server Error:\n\n%s" % response.text)

            # parse XML
            doc = parseString(response.text)
            response_node = self.find(
                doc, 'Envelope/Body/GetParcelsByIdResponse'
            )

            # collect Grundstueck
            grundstuecke = self.collect_grundstuecke(response_node)

            # collect Person
            personen = self.collect_personen(response_node)

            # collect Recht for EGRID
            rechte = self.collect_rechte(response_node, egrid)

            return {
                'egrid': egrid,
                'grundstuecke': grundstuecke,
                'personen': personen,
                'rechte': rechte
            }

        except Exception as e:
            self.logger.error(e)
            return {
                'error': "Could not load XML for EGRID %s" % egrid
            }

    def collect_grundstuecke(self, response_node):
        """Collect Grundstueck from response

        :param obj response_node: Result node GetParcelsByIdResponse
        """
        grundstuecke = {}

        for node in response_node.getElementsByTagNameNS('*', 'Grundstueck'):
            nummer = self.node_value(node, '//Nummer')
            if nummer is None:
                # skip Grundstueck in Dienstbarkeit
                continue

            # get type from tag name of first child element
            art = None
            for child in node.childNodes:
                if child.nodeType == child.ELEMENT_NODE:
                    art = child.nodeName.split(':')[-1]
                    break

            """
            parse Grundstueck Nummer:
              '<egrid>:<nr>:<nummer_zusatz>:<bfsnr>:<?>'

              e.g. CH207506973252:575::2407:
              CH210678328270:1023:1:2581:
            """
            egrid, nr, nummer_zusatz, bfsnr, b = nummer.split(':')

            grundstuecke[nummer] = {
                'egrid': egrid,
                'art': art,
                'nummer': nr,
                'nummer_zusatz': nummer_zusatz,
                'bfsnr': bfsnr,
                'municipality_name': self.node_value(
                    node, '//municipalityName'
                ),
                # StockwerksEinheit
                'beschreibung': self.node_value(
                    node, '//Beschreibung'
                )
            }

        return grundstuecke

    def collect_personen(self, response_node):
        """Collect Person from response

        :param obj response_node: Result node GetParcelsByIdResponse
        """
        personen = {}

        for node in response_node.getElementsByTagNameNS('*', 'Person'):
            nummer = self.node_value(node, '//Nummer')

            person_info = (
                self.find(node, '//NatuerlichePerson') or
                self.find(node, '//SchweizerischeJuristischePerson') or
                self.find(node, '//OeffentlicheKoerperschaft') or
                self.find(node, '//AuslaendischeRechtsform')
            )
            if person_info:
                # Person
                person = {
                    'name': self.node_value(person_info, 'Name'),
                    'vornamen': self.node_value(person_info, 'Vornamen'),
                }

                adresse = self.find(person_info, '//Adresse')
                if not self.hide_owner_addresses and adresse:
                    person.update({
                        'strasse': self.node_value(adresse, 'Strasse'),
                        'hausnummer': self.node_value(adresse, 'Hausnummer'),
                        'plz': self.node_value(adresse, 'PLZ'),
                        'ort': self.node_value(adresse, 'Ort'),
                        'land': self.node_value(adresse, 'Land')
                    })

                personen[nummer] = person
            else:
                # Gemeinschaft
                gemeinschaft = self.find(node, '//Gemeinschaft')
                if gemeinschaft:
                    teilhaber = []
                    for mitglied in gemeinschaft.getElementsByTagNameNS(
                        '*', 'Mitglieder'
                    ):
                        teilhaber.append(self.node_value(mitglied, 'ref'))

                    personen[nummer] = {
                        'name': self.node_value(gemeinschaft, '//Name'),
                        'art': self.node_value(gemeinschaft, '//Art'),
                        'teilhaber': teilhaber
                    }
                else:
                    self.logger.error(
                        "Unknown Person type: %s" % node.childNodes
                    )

        return personen

    def collect_rechte(self, response_node, egrid):
        """Collect current Recht for EGRID from response

        :param obj response_node: Result node GetParcelsByIdResponse
        :param str egrid: EGRID
        """
        rechte = []

        for node in response_node.getElementsByTagNameNS('*', 'Recht'):
            if self.find(node, 'EigentumAnteil') is None:
                # skip if not EigentumAnteil
                continue

            belastetesGrundstueck = self.node_value(
                node, '//belastetesGrundstueck'
            )
            if belastetesGrundstueck.startswith(egrid):
                # filter by currently valid Recht (bisEGBTBID not present)
                anteil = self.find(node, '//InhaltEigentumAnteil')
                if anteil and not anteil.hasAttribute('bisEGBTBID'):
                    rechte.append({
                        'nummer': self.node_value(node, '//Nummer'),
                        'eigentumsform': self.node_value(
                            anteil, '//Eigentumsform'
                        ),
                        'anteil_zaehler': self.node_value(
                            anteil, '//AnteilZaehler'
                        ),
                        'anteil_nenner': self.node_value(
                            anteil, '//AnteilNenner'
                        ),
                        'berechtigte': self.node_value(node, '//Berechtigte')
                    })
                # else skip obsolete Recht

        return rechte

    def collect_eigentuemer(self, grundstueck_info, rechte, personen,
                            grundstuecke, recursive):
        """Collect nested Berechtigte.

        :param obj grundstueck_info: Grundstueck info for EGRID
        :param list[obj] rechte: List of Recht for EGRID
        :param obj personen: Lookup for Person info by Nummer
        :param obj grundstuecke: Lookup for Grundstueck info by Nummer
        :param bool recursive: Recursively get owner info of berechtigte
                               Grundstuecke if set
        """
        eigentumsform = None
        eigentum_art = None
        eigentuemer = []

        grundstuecksarten = set()

        for recht in rechte:
            eigentumsform = recht.get('eigentumsform')
            berechtigte_id = recht.get('berechtigte')

            person = personen.get(berechtigte_id)
            if person:
                if 'teilhaber' in person:
                    # Berechtigte is Gemeinschaft
                    # flatten mitglieder
                    mitglieder = self.flatten_mitglieder(person, personen)
                    # sort
                    mitglieder.sort(
                        key=lambda l: (
                            l.get('vornamen'), l.get('name'), l.get('strasse')
                        )
                    )

                    # collect unique addresses
                    last_adresse = None
                    berechtigte = []
                    for mitglied in mitglieder:
                        adresse = self.format_adresse(mitglied)
                        if adresse != last_adresse:
                            berechtigte.append(adresse)
                            last_adresse = adresse
                        # else skip duplicate adresse

                    eigentuemer.append({
                        'berechtigte': berechtigte
                    })
                else:
                    # Berechtigte is Person
                    eigentuemer.append({
                        'berechtigte': [self.format_adresse(person)]
                    })
            elif grundstuecke.get(berechtigte_id):
                # Berechtigte is Grundstueck
                grundstueck = grundstuecke.get(berechtigte_id)
                grundstuecksarten.add(grundstueck.get('art'))

                berechtigte = []
                if recursive:
                    # collect Berechtigte of Grundstueck
                    sub_owner_info = self.get_owner_info(
                        grundstueck.get('egrid')
                    )
                    if 'error' in sub_owner_info:
                        # mark as error
                        self.logger.error(sub_owner_info['error'])
                        berechtigte.append("ERROR")
                    else:
                        sub_grundstuecke = sub_owner_info.get('grundstuecke')
                        sub_personen = sub_owner_info.get('personen')
                        sub_rechte = sub_owner_info.get('rechte')
                        sub_eigentuemer = self.collect_eigentuemer(
                            grundstueck, sub_rechte, sub_personen,
                            sub_grundstuecke, False
                        )

                        if (sub_eigentuemer.get('eigentum_art') ==
                                'StockwerksEinheit'):
                            # Stockwerkeigentum
                            berechtigte.append(
                                self.lookup_eigentumsform('StockwerksEinheit')
                            )
                        elif (sub_eigentuemer.get('eigentum_art') ==
                                'GewoehnlichesMiteigentum'):
                            # Verselbständigtes Miteigentum
                            berechtigte.append(
                                self.lookup_eigentumsform(
                                    'GewoehnlichesMiteigentum'
                                )
                            )
                        elif (grundstueck.get('art') ==
                                'GewoehnlichesMiteigentum'):
                            # flatten Berechtigte of GewoehnlichesMiteigentum
                            sub_berechtigte = []
                            sub_grundstuecke = []
                            for b in sub_eigentuemer.get('eigentuemer'):
                                if b.get('grundstueck'):
                                    # sub Berechtigte is Grundstueck
                                    sub_grundstuecke.append(
                                        b.get('grundstueck')
                                    )
                                else:
                                    # sub Berechtigte is Person
                                    sub_berechtigte += b.get('berechtigte')

                            if sub_grundstuecke:
                                berechtigte.append(
                                    self.lookup_eigentumsform(
                                        'GewoehnlichesMiteigentum'
                                    )
                                )
                                berechtigte += sub_grundstuecke

                            berechtigte += sub_berechtigte
                        else:
                            # flatten Berechtigte of Grundstueck
                            for b in sub_eigentuemer.get('eigentuemer'):
                                berechtigte += b.get('berechtigte')

                # sort keys
                sort_nummer = int(grundstueck.get('nummer') or 0)
                sort_nummer_zusatz = int(
                    grundstueck.get('nummer_zusatz') or 0
                )

                sub_eigentum = {
                    'grundstueck': self.format_grundstueck(grundstueck),
                    'berechtigte': berechtigte,
                    'sort_nummer': sort_nummer,
                    'sort_nummer_zusatz': sort_nummer_zusatz
                }
                sub_eigentum['berechtigte'] = berechtigte

                if (
                    grundstueck.get('art') == 'StockwerksEinheit'
                    and 'beschreibung' in grundstueck
                ):
                    # add StockwerksEinheit Beschreibung
                    sub_eigentum['beschreibung'] = grundstueck.get(
                        'beschreibung'
                    )

                eigentuemer.append(sub_eigentum)
            else:
                self.logger.error(
                    "Could not find Berechtigte %s" % berechtigte_id
                )

        # sort eigentuemer by GB-Nr. and first Berechtigte
        eigentuemer.sort(
            key=lambda l: (
                l.get('sort_nummer'), l.get('sort_nummer_zusatz'),
                l.get('grundstueck'),
                (l.get('berechtigte') or [''])[0]
            )
        )

        # remove sort keys
        for e in eigentuemer:
            e.pop('sort_nummer', None)
            e.pop('sort_nummer_zusatz', None)

        if len(grundstuecksarten) == 1:
            # set eigentum_art if grundstueck Art is unique
            if 'StockwerksEinheit' in grundstuecksarten:
                eigentum_art = 'StockwerksEinheit'
            elif 'GewoehnlichesMiteigentum' in grundstuecksarten:
                eigentum_art = "GewoehnlichesMiteigentum"

        # result
        eigentum = {
            'grundstueck': self.format_grundstueck(grundstueck_info),
            'eigentumsform': eigentumsform,
            'eigentum_art': eigentum_art,
            'eigentuemer': eigentuemer
        }
        if (
            grundstueck_info.get('art') == 'StockwerksEinheit'
            and 'beschreibung' in grundstueck_info
        ):
            # add StockwerksEinheit Beschreibung
            eigentum['beschreibung'] = grundstueck_info.get('beschreibung')

        return eigentum

    def flatten_mitglieder(self, gemeinschaft, personen):
        """Recursively collect flattened list of Mitglieder of Gemeinschaft.

        :param obj gemeinschaft: Gemeinschaft info
        :param obj personen: Lookup for Person info by Nummer
        """
        mitglieder = []

        for teilhaber_id in gemeinschaft.get('teilhaber', []):
            mitglied = personen.get(teilhaber_id)
            if mitglied:
                if 'teilhaber' in mitglied:
                    # Gemeinschaft
                    mitglieder += self.flatten_mitglieder(mitglied, personen)
                else:
                    # Person
                    mitglieder.append(mitglied)
            else:
                self.logger.error("Could not find Mitglied %s" % teilhaber_id)

        return mitglieder

    def format_adresse(self, person):
        """Return fomatted address for a Person.

        :param obj person: Person info
        """
        name = (' ').join(
            filter(None, [person.get('vornamen'), person.get('name')])
        )
        strasse = (' ').join(
            filter(None, [person.get('strasse'), person.get('hausnummer')])
        )
        ort = (' ').join(filter(None, [person.get('plz'), person.get('ort')]))
        land = person.get('land')
        if land == 'Schweiz':
            # skip default country
            land = None

        return (', ').join(filter(None, [name, strasse, ort, land]))

    def format_grundstueck(self, grundstueck):
        """Return fomatted name for a Grundstueck.

        :param obj person: Grundstueck info
        """
        nummer = ('-').join(
            filter(None, [
                grundstueck.get('nummer'), grundstueck.get('nummer_zusatz')
            ])
        )
        return "GB-Nr. %s %s" % (nummer, grundstueck.get('municipality_name'))

    def lookup_eigentumsform(self, eigentumsform):
        """Lookup text for eigentumsform or -art

        :param str eigentumsform: Eigentumsform or -art
        """
        return self.EIGENTUMSFORM_LOOKUP.get(eigentumsform, eigentumsform)

    # XML parse helpers

    def find(self, parent, path):
        """Find first subnode of parent node matching path.

        XML namespaces are ignored.

        :param obj parent: Parent node
        :param str path: Path to subnode (use `//` for any sublevel)
        """
        match = parent
        any_level = False
        for part in path.split("/"):
            if part == '':
                # mark as any level
                any_level = True
                continue

            if any_level:
                # find child on any sublevel
                any_level = False
                for node in match.getElementsByTagNameNS('*', part):
                    match = node
                    break
                else:
                    # no match
                    return None
            else:
                # find child node
                for node in match.childNodes:
                    if node.nodeName.split(':')[-1] == part:
                        match = node
                        break
                else:
                    # no match
                    return None

        return match

    def node_value(self, parent, path):
        """Get value of first subnode of parent node matching path.

        XML namespaces are ignored.

        :param obj parent: Parent node
        :param str path: Path to subnode (use `//` for any sublevel)
        """
        value = None
        node = self.find(parent, path)
        if node and node.firstChild:
            value = node.firstChild.nodeValue
        return value
