""" This module provides access the Tesla Motors Owner API. It uses Tesla's new
RFC compliant OAuth 2 Single Sign-On service and supports Time-based One-Time
Passwords. Tokens are saved to disk for reuse and refreshed automatically, only
needing an email (no password). The vehicle option codes are loaded from
'option_codes.json' and the API endpoints are loaded from 'endpoints.json'.
"""

# Author: Tim Dorssers

__version__ = '1.5.0'

import os
import re
import ast
import json
import time
import base64
import hashlib
import logging
import pkgutil
import tempfile
import webbrowser
try:
    from HTMLParser import HTMLParser
    from urlparse import urljoin
except ImportError:
    from html.parser import HTMLParser
    from urllib.parse import urljoin
import requests
from requests_oauthlib import OAuth2Session
from requests.exceptions import *
from requests.packages.urllib3.util.retry import Retry
from oauthlib.oauth2.rfc6749.errors import *
import websocket  # websocket-client v0.49.0 up to v0.58.0 is not supported

requests.packages.urllib3.disable_warnings()

BASE_URL = 'https://owner-api.teslamotors.com/'
CLIENT_ID = 'e4a9949fcfa04068f59abb5a658f2bac0a3428e4652315490b659d5ab3f35a9e'
SSO_BASE_URL = 'https://auth.tesla.com/'
SSO_CLIENT_ID = 'ownerapi'
STREAMING_BASE_URL = 'wss://streaming.vn.teslamotors.com/'


class PasswdFilter(logging.Filter):
    """ Logging filter to masquerade password """

    def filter(self, record):
        """ Modify record in-place """
        if isinstance(record.args, tuple):
            record.args = tuple(self._masquerade(arg) for arg in record.args)
        else:
            record.args = self._masquerade(record.args)
        return True  # Indicate record is to be logged

    @staticmethod
    def _masquerade(arg):
        """ Replace password by stars """
        if isinstance(arg, dict):
            for key in ('credential', 'password'):
                if key in arg:
                    arg = arg.copy()
                    arg[key] = '*' * len(arg[key])
        return arg


# Setup module logging
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
logger.addFilter(PasswdFilter())
logging.getLogger('requests_oauthlib.oauth2_session').addFilter(PasswdFilter())

# Py2/3 compatibility
try:
    input = raw_input
except NameError:
    pass


class Tesla(requests.Session):
    """ Implements a session manager for the Tesla Motors Owner API

    email: SSO identity.
    password: SSO credential.
    passcode_getter: (optional) Function that returns the TOTP passcode.
    factor_selector: (optional) Function with one argument, a list of factor
        dicts, that returns the selected dict or factor name.
    captcha_solver: (optional) Function with one argument, SVG image content,
        that returns the captcha characters.
    verify: (optional) Verify SSL certificate.
    proxy: (optional) URL of proxy server.
    retry: (optional) Number of connection retries or `Retry` instance.
    user_agent: (optional) The User-Agent string.
    cache_file: (optional) Path to cache file used by default loader and dumper.
    cache_loader: (optional) Function that returns the cache dict.
    cache_dumper: (optional) Function with one argument, the cache dict.
    """

    def __init__(self, email, password, passcode_getter=None,
                 factor_selector=None, captcha_solver=None, verify=True,
                 proxy=None, retry=0, user_agent=__name__ + '/' + __version__,
                 cache_file='cache.json', cache_loader=None, cache_dumper=None):
        super(Tesla, self).__init__()
        if not email:
            raise ValueError('`email` is not set')
        self.email = email
        self.password = password
        self.passcode_getter = passcode_getter or self._get_passcode
        self.factor_selector = factor_selector or self._select_factor
        self.captcha_solver = captcha_solver or self._solve_captcha
        self.cache_loader = cache_loader or self._cache_load
        self.cache_dumper = cache_dumper or self._cache_dump
        self.cache_file = cache_file
        self.token = {}
        self.expires_at = 0
        self.authorized = False
        self.endpoints = {}
        self.sso_token = {}
        self.sso_base = SSO_BASE_URL
        # Set Session properties
        self.mount('https://', requests.adapters.HTTPAdapter(max_retries=retry))
        self.headers.update({'Content-Type': 'application/json',
                             'User-Agent': user_agent})
        self.verify = verify
        if proxy:
            self.trust_env = False
            self.proxies.update({'https': proxy})
        self._token_updater()  # Try to read token from cache

    def request(self, method, url, **kwargs):
        """ Extends base class method to support bearer token insertion. Raises
        HTTPError when an error occurs.

        Return type: JsonDict
        """
        # Auto refresh token and insert access token into headers
        if self.authorized:
            if 0 < self.expires_at < time.time():
                self.refresh_token()
            self.headers.update({'Authorization':
                                 'Bearer ' + self.token['access_token']})
        # Construct URL and send request with optional serialized data
        url = BASE_URL + url.strip('/')
        kwargs.setdefault('timeout', 10)
        data = kwargs.pop('data', {})
        logger.debug('Requesting url %s using method %s', url, method)
        logger.debug('Supplying headers %s and data %s', self.headers, data)
        logger.debug('Passing through key word arguments %s', kwargs)
        response = super(Tesla, self).request(method, url, json=data, **kwargs)
        # Error message handling
        if 400 <= response.status_code < 600:
            try:
                lst = [str(v).strip('.') for v in response.json().values() if v]
                response.reason = '. '.join(lst)
            except ValueError:
                pass
        response.raise_for_status()  # Raise HTTPError, if one occurred
        # Deserialize response
        return response.json(object_hook=JsonDict)

    def fetch_token(self):
        """ Sign in using Tesla's SSO service to request a JWT bearer. Raises
        HTTPError, CustomOAuth2Error or ValueError. """
        if self.authorized:
            return
        if not self.password:
            raise ValueError('`password` is not set')
        # Generate code verifier and challenge for PKCE (RFC 7636)
        code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=')
        unencoded_digest = hashlib.sha256(code_verifier).digest()
        code_challenge = base64.urlsafe_b64encode(unencoded_digest).rstrip(b'=')
        # Prepare for OAuth 2 Authorization Code Grant flow
        oauth = OAuth2Session(client_id=SSO_CLIENT_ID,
                              scope=('openid', 'email', 'offline_access'),
                              redirect_uri=SSO_BASE_URL + 'void/callback')
        oauth.verify = self.verify
        oauth.trust_env = self.trust_env
        oauth.proxies = self.proxies
        oauth.headers['User-Agent'] = self.headers['User-Agent']
        url, _ = oauth.authorization_url(self.sso_base + 'oauth2/v3/authorize',
                                         code_challenge=code_challenge,
                                         code_challenge_method='S256',
                                         login_hint=self.email)
        # Retrieve SSO page (may be redirected to account's registered region)
        response = oauth.get(url)
        response.raise_for_status()  # Raise HTTPError, if one occurred
        if response.history:
            self.sso_base = urljoin(response.url, '/')
        # Parse input objects on HTML form
        form = HTMLForm(response.text)
        transaction_id = form['transaction_id']
        # Retrieve captcha image if required
        if 'captcha' in form:
            response = oauth.get(self.sso_base + 'captcha')
            response.raise_for_status()  # Raise HTTPError, if one occurred
            form['captcha'] = self.captcha_solver(response.content)
            if not form['captcha']:
                raise ValueError('Missing captcha response')
        # Submit login credentials to get authorization code through redirect
        form.update({'identity': self.email, 'credential': self.password})
        response = oauth.post(self.sso_base + 'oauth2/v3/authorize',
                              data=form, allow_redirects=False)
        if response.status_code != 302:
            form = HTMLForm(response.text)
            # Retrieve captcha image if required
            if 'captcha' in form:
                response = oauth.get(self.sso_base + 'captcha')
                response.raise_for_status()  # Raise HTTPError, if one occurred
                form['captcha'] = self.captcha_solver(response.content)
                if not form['captcha']:
                    raise ValueError('Missing captcha response')
                # Resubmit login credentials
                form.update({'identity': self.email, 'credential': self.password})
                response = oauth.post(self.sso_base + 'oauth2/v3/authorize',
                                      data=form, allow_redirects=False)
        if response.status_code != 302:
            # An error occurred if the login form is present
            msgs = ['Credentials rejected'] if HTMLForm(response.text) else []
            # Look for messages object literal
            m = re.search(r'var messages = ({.*});', response.text)
            if m:
                # Make list of error messages
                for msg in json.loads(m.group(1)).values():
                    msgs += [msg] if not isinstance(msg, list) else msg
            # Raise error if one occurred
            if msgs:
                raise ValueError('. '.join(msgs))
            response.raise_for_status()
            # Check for MFA factors to handle to get authorized
            response = self._check_mfa(oauth, transaction_id)
        response.raise_for_status()
        # Use authorization response code in redirected location to get token
        url = response.headers.get('Location')
        oauth.fetch_token(self.sso_base + 'oauth2/v3/token',
                          authorization_response=url, include_client_id=True,
                          code_verifier=code_verifier)
        self.sso_token = oauth.token
        self._fetch_jwt(oauth)  # Access protected resource

    def _check_mfa(self, oauth, transaction_id):
        """ Handle multi-factor authentication and return submitted response """
        # Check for MFA factors
        url = self.sso_base + 'oauth2/v3/authorize/mfa/factors'
        response = oauth.get(url, params={'transaction_id': transaction_id})
        response.raise_for_status()  # Raise HTTPError, if one occurred
        factors = response.json()['data']
        if not factors:
            raise ValueError('No registered factors')
        if len(factors) == 1:
            factor = factors[0]  # Auto select only factor
        elif len(factors) > 1:
            # Get selected factor
            factor = self.factor_selector(factors)
            if not factor:
                # Submit cancel and have fetch_token raise CustomOAuth2Error
                data = {'transaction_id': transaction_id, 'cancel': '1'}
                return oauth.post(self.sso_base + 'oauth2/v3/authorize',
                                  data=data, allow_redirects=False)
            if not isinstance(factor, dict):
                # Find factor by name
                try:
                    factor = next((f for f in factors if f['name'] == factor))
                except StopIteration:
                    raise ValueError('No such factor name ' + factor)
        # Only TOTP is supported
        if factor['factorType'] != 'token:software':
            msg = factor['factorType'] + ' factor is not implemented'
            raise NotImplementedError(msg)
        # Get passcode
        passcode = self.passcode_getter()
        if not passcode:
            # Submit cancel and have fetch_token raise CustomOAuth2Error
            data = {'transaction_id': transaction_id, 'cancel': '1'}
            return oauth.post(self.sso_base + 'oauth2/v3/authorize', data=data,
                              allow_redirects=False)
        # Verify passcode
        data = {'transaction_id': transaction_id, 'factor_id': factor['id'],
                'passcode': passcode}
        url = self.sso_base + 'oauth2/v3/authorize/mfa/verify'
        response = oauth.post(url, json=data)
        if 'error' in response.json():
            raise ValueError(response.json()['error']['message'])
        if not response.json()['data']['valid']:
            raise ValueError('Invalid passcode')
        # Submit and get authorization response code
        data = {'transaction_id': transaction_id}
        return oauth.post(self.sso_base + 'oauth2/v3/authorize', data=data,
                          allow_redirects=False)

    def _fetch_jwt(self, oauth):
        """ Perform RFC 7523 JSON web token exchange for Owner API access """
        data = {'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                'client_id': CLIENT_ID}
        response = oauth.post(BASE_URL + 'oauth/token', data=data)
        response.raise_for_status()  # Raise HTTPError, if one occurred
        self.token = response.json()
        self.expires_at = self.token['created_at'] + self.token['expires_in']
        logger.debug('Got JWT bearer, expires at %s',
                     time.ctime(self.expires_at))
        self.authorized = True
        self._token_updater()  # Save new token

    @staticmethod
    def _get_passcode():
        """ Default passcode_getter method """
        return input('Passcode: ')

    @staticmethod
    def _select_factor(factors):
        """ Default factor_selector method """
        for i, factor in enumerate(factors):
            print('{:2} {}'.format(i, factor['name']))
        return factors[int(input('Select factor: '))]

    @staticmethod
    def _solve_captcha(svg):
        """ Default captcha_solver method """
        # Use web browser to display SVG image
        with tempfile.NamedTemporaryFile(suffix='.svg', delete=False) as f:
            f.write(svg)
        logger.debug('Opening %s with default browser', f.name)
        webbrowser.open('file://' + f.name)
        return input('Captcha: ')

    def _cache_load(self):
        """ Default cache loader method """
        try:
            with open(self.cache_file) as infile:
                cache = json.load(infile)
        except (IOError, ValueError):
            cache = {}
        return cache

    def _cache_dump(self, cache):
        """ Default cache dumper method """
        try:
            with open(self.cache_file, 'w') as outfile:
                json.dump(cache, outfile)
        except IOError:
            logger.error('Cache not updated')
        else:
            logger.debug('Updated cache')

    def _token_updater(self):
        """ Handles token persistency """
        cache = self.cache_loader()
        if not isinstance(cache, dict):
            raise ValueError('`cache_loader` must return dict')
        # Write token to cache
        if self.authorized:
            cache[self.email] = {'url': self.sso_base, 'sso': self.sso_token,
                                 SSO_CLIENT_ID: self.token}
            self.cache_dumper(cache)
        # Read token from cache
        elif self.email in cache:
            self.sso_base = cache[self.email].get('url', SSO_BASE_URL)
            self.sso_token = cache[self.email].get('sso', {})
            self.token = cache[self.email].get(SSO_CLIENT_ID, {})
            if not self.token:
                return
            self.expires_at = (self.token['created_at']
                               + self.token['expires_in'])
            self.authorized = True
            # Log the token validity
            if 0 < self.expires_at < time.time():
                logger.debug('Cached JWT bearer expired')
            else:
                logger.debug('Cached JWT bearer, expires at %s',
                             time.ctime(self.expires_at))

    def refresh_token(self):
        """ Refreshes the SSO token and requests a new JWT bearer """
        if not self.sso_token:
            return
        # Prepare session for token refresh
        oauth = OAuth2Session(client_id=SSO_CLIENT_ID, token=self.sso_token,
                              scope=('openid', 'email', 'offline_access'))
        oauth.verify = self.verify
        oauth.trust_env = self.trust_env
        oauth.proxies = self.proxies
        # Refresh token request must include client_id
        oauth.refresh_token(self.sso_base + 'oauth2/v3/token',
                            client_id=SSO_CLIENT_ID)
        self.sso_token = oauth.token
        self._fetch_jwt(oauth)  # Access protected resource

    def api(self, name, path_vars=None, **kwargs):
        """ Convenience method to perform API request for given endpoint name,
        with keyword arguments as parameters. Substitutes path variables in URI
        using path_vars. Raises ValueError if endpoint name is not found.

        Return type: JsonDict
        """
        path_vars = path_vars or {}
        # Load API endpoints once
        if not self.endpoints:
            try:
                data = pkgutil.get_data(__name__, 'endpoints.json')
                self.endpoints = json.loads(data.decode())
                logger.debug('%d endpoints loaded', len(self.endpoints))
            except (IOError, ValueError):
                logger.error('No endpoints loaded')
        # Lookup endpoint name
        try:
            endpoint = self.endpoints[name]
        except KeyError:
            raise ValueError('Unknown endpoint name ' + name)
        # Only JSON is supported
        if endpoint.get('CONTENT', 'JSON') != 'JSON' or name == 'STATUS':
            raise NotImplementedError('Endpoint %s not implemented' % name)
        # Fetch token if not authorized and API requires authorization
        if endpoint['AUTH'] and not self.authorized:
            self.fetch_token()
        # Substitute path variables in URI
        try:
            uri = endpoint['URI'].format(**path_vars)
        except KeyError as e:
            raise ValueError('%s requires path variable %s' % (name, e))
        # Perform request using given keyword arguments as parameters
        if endpoint['TYPE'] == 'GET':
            return self.request('GET', uri, params=kwargs)
        return self.request(endpoint['TYPE'], uri, data=kwargs)

    def vehicle_list(self):
        """ Returns a list of `Vehicle` objects """
        return [Vehicle(v, self) for v in self.api('VEHICLE_LIST')['response']]

    def battery_list(self):
        """ Returns a list of `Battery` objects """
        return [Battery(p, self) for p in self.api('PRODUCT_LIST')['response']
                if p.get('resource_type') == 'battery']

    def solar_list(self):
        """ Returns a list of `SolarPanel` objects """
        return [SolarPanel(p, self) for p in self.api('PRODUCT_LIST')['response']
                if p.get('resource_type') == 'solar']


class HTMLForm(HTMLParser, dict):
    """ Parse input tags on HTML form """

    def __init__(self, html):
        HTMLParser.__init__(self)
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        """ Make dictionary of name and value attributes of input tags """
        if tag == 'input':
            self[dict(attrs)['name']] = dict(attrs).get('value', '')


class VehicleError(Exception):
    """ Vehicle exception class """
    pass


class JsonDict(dict):
    """ Pretty printing dictionary """

    def __str__(self):
        """ Serialize dict to JSON formatted string with indents """
        return json.dumps(self, indent=4)


class Vehicle(JsonDict):
    """ Vehicle class with dictionary access and API request support """

    codes = None  # Vehicle option codes class variable
    COLS = ['speed', 'odometer', 'soc', 'elevation', 'est_heading', 'est_lat',
            'est_lng', 'power', 'shift_state', 'range', 'est_range', 'heading']

    def __init__(self, vehicle, tesla):
        super(Vehicle, self).__init__(vehicle)
        self.tesla = tesla
        self.callback = None

    def _subscribe(self, wsapp):
        """ Authenticate and select streaming telemetry columns """
        msg = {'msg_type': 'data:subscribe_oauth',
               'token': self.tesla.token['access_token'],
               'value': ','.join(self.COLS), 'tag': str(self['vehicle_id'])}
        wsapp.send(json.dumps(msg))

    def _parse_msg(self, wsapp, message):
        """ Parse messages """
        msg = json.loads(message)
        if msg['msg_type'] == 'control:hello':
            logger.debug('connected')
        elif msg['msg_type'] == 'data:update':
            # Parse comma separated data record
            data = dict(zip(['timestamp'] + self.COLS, msg['value'].split(',')))
            for key, value in data.items():
                try:
                    data[key] = ast.literal_eval(value) if value else None
                except ValueError:
                    pass
            logger.debug('Update %s', json.dumps(data))
            if self.callback:
                self.callback(data)
            # Update polled data with streaming telemetry data
            drive_state = self.setdefault('drive_state', JsonDict())
            vehicle_state = self.setdefault('vehicle_state', JsonDict())
            charge_state = self.setdefault('charge_state', JsonDict())
            drive_state['timestamp'] = data['timestamp']
            drive_state['speed'] = data['speed']
            vehicle_state['odometer'] = data['odometer']
            charge_state['battery_level'] = data['soc']
            drive_state['heading'] = data['est_heading']
            drive_state['latitude'] = data['est_lat']
            drive_state['longitude'] = data['est_lng']
            drive_state['power'] = data['power']
            drive_state['shift_state'] = data['shift_state']
            charge_state['ideal_battery_range'] = data['range']
            charge_state['est_battery_range'] = data['est_range']
            drive_state['heading'] = data['heading']
        elif msg['msg_type'] == 'data:error':
            logger.error(msg['value'])
            wsapp.close()

    @staticmethod
    def _ws_error(wsapp, err):
        """ Log exceptions """
        logger.error(err)

    def stream(self, callback=None, retry=0, indefinitely=False, **kwargs):
        """ Let vehicle push on-change data, with 10 second idle timeout.

        callback: (optional) Function with one argument, a dict of pushed data.
        retry: (optional) Number of connection retries.
        indefinitely: (optional) Retry indefinitely.
        **kwargs: Optional arguments that `run_forever` takes.
        """
        self.callback = callback
        websocket.enableTrace(logger.isEnabledFor(logging.DEBUG),
                              handler=logging.NullHandler())
        wsapp = websocket.WebSocketApp(STREAMING_BASE_URL + 'streaming/',
                                       on_open=self._subscribe,
                                       on_message=self._parse_msg,
                                       on_error=self._ws_error)
        kwargs.setdefault('ping_interval', 10)
        while True:
            wsapp.run_forever(**kwargs)
            if indefinitely:
                continue
            if not retry:
                break
            logger.debug('%d retries left', retry)
            retry -= 1

    def api(self, name, **kwargs):
        """ Endpoint request with vehicle_id path variable """
        return self.tesla.api(name, {'vehicle_id': self['id_s']}, **kwargs)

    def get_vehicle_summary(self):
        """ Determine the state of the vehicle's various sub-systems """
        self.update(self.api('VEHICLE_SUMMARY')['response'])
        return self

    def sync_wake_up(self, timeout=60, interval=2, backoff=1.15):
        """ Wakes up vehicle if needed and waits for it to come online """
        logger.info('%s is %s', self['display_name'], self['state'])
        if self['state'] != 'online':
            self.api('WAKE_UP')  # Send wake up command
            start_time = time.time()
            while self['state'] != 'online':
                logger.debug('Waiting for %d seconds', interval)
                time.sleep(int(interval))
                # Get vehicle status
                self.get_vehicle_summary()
                # Raise exception when task has timed out
                if start_time + timeout < time.time():
                    raise VehicleError('%s not woken up within %s seconds'
                                       % (self['display_name'], timeout))
                interval *= backoff
            logger.info('%s is %s', self['display_name'], self['state'])

    def option_code_list(self):
        """ Returns a list of known option code titles """
        # Load option codes once
        if Vehicle.codes is None:
            try:
                data = pkgutil.get_data(__name__, 'option_codes.json')
                Vehicle.codes = json.loads(data.decode())
                logger.debug('%d option codes loaded', len(Vehicle.codes))
            except (IOError, ValueError):
                Vehicle.codes = {}
                logger.error('No option codes loaded')
        # Make list of known option code titles
        return [self.codes[c] for c in self['option_codes'].split(',')
                if self.codes.get(c) is not None]

    def get_vehicle_data(self):
        """ A rollup of all the data request endpoints plus vehicle config """
        self.update(self.api('VEHICLE_DATA')['response'])
        return self

    def get_nearby_charging_sites(self):
        """ Lists nearby Tesla-operated charging stations """
        return self.api('NEARBY_CHARGING_SITES')['response']

    def get_service_scheduling_data(self):
        """ Retrieves next service appointment for this vehicle """
        response = self.api('SERVICE_SELF_SCHEDULING_ELIGIBILITY')['response']
        return next((enabled for enabled in response['enabled_vins']
                     if enabled['vin'] == self['vin']), {})

    def mobile_enabled(self):
        """ Checks if the Mobile Access setting is enabled in the car """
        # Construct URL and send request
        uri = 'api/1/vehicles/%s/mobile_enabled' % self['id_s']
        return self.tesla.get(uri)['response']

    def compose_image(self, view='STUD_3QTR', size=640, options=None):
        """ Returns a PNG formatted composed vehicle image. Valid views are:
        STUD_3QTR, STUD_SEAT, STUD_SIDE, STUD_REAR and STUD_WHEEL """
        if options is None:
            msg = 'compose_image requires options for the image to be accurate'
            logger.warning(msg)
        # Derive model from VIN and other properties from (given) option codes
        params = {'model': 'm' + self['vin'][3].lower(),
                  'bkba_opt': 1, 'view': view, 'size': size,
                  'options': options or self['option_codes']}
        # Retrieve image from compositor
        url = 'https://static-assets.tesla.com/v1/compositor/'
        response = requests.get(url, params=params, verify=self.tesla.verify,
                                proxies=self.tesla.proxies)
        response.raise_for_status()  # Raise HTTPError, if one occurred
        return response.content

    def dist_units(self, miles, speed=False):
        """ Format and convert distance or speed to GUI setting units """
        if miles is None:
            return None
        if 'gui_settings' not in self:
            self.get_vehicle_data()
        # Lookup GUI settings of the vehicle
        if 'km' in self['gui_settings']['gui_distance_units']:
            return '%.1f %s' % (miles * 1.609344, 'km/h' if speed else 'km')
        return '%.1f %s' % (miles, 'mph' if speed else 'mi')

    def temp_units(self, celcius):
        """ Format and convert temperature to GUI setting units """
        if celcius is None:
            return None
        if 'gui_settings' not in self:
            self.get_vehicle_data()
        # Lookup GUI settings of the vehicle
        if 'F' in self['gui_settings']['gui_temperature_units']:
            return '%.1f F' % (celcius * 1.8 + 32)
        return '%.1f C' % celcius

    def decode_vin(self):
        """ Returns decoded VIN as dict """
        make = 'Model ' + self['vin'][3]
        body = {'A': 'Hatchback 5 Dr / LHD', 'B': 'Hatchback 5 Dr / RHD',
                'C': 'MPV / 5 Dr / LHD', 'D': 'MPV / 5 Dr / RHD',
                'E': 'Sedan 4 Dr / LHD', 'F': 'Sedan 4 Dr / RHD',
                'G': 'MPV / 5 Dr / LHD'}.get(self['vin'][4], 'Unknown')
        batt = {'E': 'Electric', 'H': 'High Capacity', 'S': 'Standard Capacity',
                'V': 'Ultra Capacity'}.get(self['vin'][6], 'Unknown')
        drive = {'1': 'Single Motor', '2': 'Dual Motor',
                 '3': 'Performance Single Motor', 'C': 'Base, Tier 2',
                 '4': 'Performance Dual Motor', 'P': 'Performance, Tier 7',
                 'A': 'Single Motor', 'B': 'Dual Motor',
                 'F': 'Performance Dual Motor', 'G': 'Base, Tier 4',
                 'N': 'Base, Tier 7'}.get(self['vin'][7], 'Unknown')
        year = 2009 + '9ABCDEFGHJKLMNPRSTVWXY12345678'.index(self['vin'][9])
        plant = {'C': 'Shanghai, China', 'F': 'Fremont, CA, USA',
                 'P': 'Palo Alto, CA, USA'}.get(self['vin'][10], 'Unknown')
        return JsonDict(manufacturer='Tesla Motors, Inc.',
                        make=make, body_type=body, battery_type=batt,
                        drive_unit=drive, year=str(year), plant_code=plant)

    def remote_start_drive(self):
        """ Enables keyless driving for two minutes """
        if not self.tesla.password:
            raise ValueError('`password` is not set')
        return self.command('REMOTE_START', password=self.tesla.password)

    def command(self, name, **kwargs):
        """ Wrapper method for vehicle command response error handling """
        response = self.api(name, **kwargs)['response']
        if not response['result']:
            raise VehicleError(response['reason'])
        return response['result']


class ProductError(Exception):
    """ Product exception class """
    pass


class Product(JsonDict):
    """ Base product class with dictionary access and API request support """

    def __init__(self, product, tesla):
        super(Product, self).__init__(product)
        self.tesla = tesla

    def api(self, name, **kwargs):
        """ Endpoint request with battery_id or site_id path variable """
        pathvars = {'battery_id': self['id'], 'site_id': self['energy_site_id']}
        return self.tesla.api(name, pathvars, **kwargs)

    def get_calendar_history_data(
            self, kind='savings', period='day', start_date=None,
            end_date=time.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            installation_timezone=None, timezone=None, tariff=None):
        """ Retrieve live status of product
        kind: A telemetry type of 'backup', 'energy', 'power',
              'self_consumption', 'time_of_use_energy',
              'time_of_use_self_consumption' and 'savings'
        period: 'day', 'month', 'year', or 'lifetime'
        end_date: The final day in the data requested in the json format
                  '2021-02-28T07:59:59.999Z'
        time_zone: Timezone in the json timezone format. eg. Europe/Brussels
        start_date: The state date in the data requested in the json format
                    '2021-02-27T07:59:59.999Z'
        installation_timezone: Timezone of installation location for 'savings'
        tariff: Unclear format use in 'savings' only
        """
        return self.api('CALENDAR_HISTORY_DATA', kind=kind, period=period,
                        start_date=start_date, end_date=end_date,
                        timezone=timezone,
                        installation_timezone=installation_timezone,
                        tariff=tariff)['response']

    def get_history_data(
            self, kind='savings', period='day', start_date=None,
            end_date=time.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            installation_timezone=None, timezone=None, tariff=None):
        """ Retrieve live status of product
        kind: A telemetry type of 'backup', 'energy', 'power',
              'self_consumption', 'time_of_use_energy', and
              'time_of_use_self_consumption'
        period: 'day', 'month', 'year', or 'lifetime'
        end_date: The final day in the data requested in the json format
                  '2021-02-28T07:59:59.999Z'
        time_zone: Timezone in the json timezone format. eg. Europe/Brussels
        start_date: The state date in the data requested in the json format
                    '2021-02-27T07:59:59.999Z'
        installation_timezone: Timezone of installation location for 'savings'
        tariff: Unclear format use in 'savings' only
        """
        return self.api('HISTORY_DATA', kind=kind, period=period,
                        start_date=start_date, end_date=end_date,
                        timezone=timezone,
                        installation_timezone=installation_timezone,
                        tariff=tariff)['response']

    def command(self, name, **kwargs):
        """ Wrapper method for product command response error handling """
        response = self.api(name, **kwargs)['response']
        if response['code'] == 201:
            return response.get('message')
        raise ProductError(response.get('message'))


class Battery(Product):
    """ Powerwall class """

    def get_battery_data(self):
        """ Retrieve detailed state and configuration of the battery """
        self.update(self.api('BATTERY_DATA')['response'])
        return self

    def set_operation(self, mode):
        """ Set battery operation to self_consumption, backup or autonomous """
        return self.command('BATTERY_OPERATION_MODE', default_real_mode=mode)

    def set_backup_reserve_percent(self, percent):
        """ Set the minimum backup reserve percent for that battery """
        return self.command('BACKUP_RESERVE',
                            backup_reserve_percent=int(percent))


class SolarPanel(Product):
    """ Solar panel class """

    def get_site_data(self):
        """ Retrieve current site generation data """
        self.update(self.api('SITE_DATA')['response'])
        return self
