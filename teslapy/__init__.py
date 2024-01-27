""" This module provides access the Tesla Motors Owner API. It uses Tesla's new
RFC compliant OAuth 2 Single Sign-On service. Tokens are saved to 'cache.json'
for reuse and refreshed automatically. The vehicle option codes are loaded from
'option_codes.json' and the API endpoints are loaded from 'endpoints.json'.
"""

# Author: Tim Dorssers

__version__ = '2.9.0'

import os
import ast
import json
import time
import base64
import hashlib
import logging
import pkgutil
import datetime
import webbrowser
import stat
try:
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin
from collections import defaultdict, namedtuple
import requests
from requests_oauthlib import OAuth2Session
from requests.exceptions import *
from requests.packages.urllib3.util.retry import Retry
from oauthlib.oauth2.rfc6749.errors import *
import websocket  # websocket-client v0.49.0 up to v0.58.0 is not supported

requests.packages.urllib3.disable_warnings()

BASE_URL = 'https://owner-api.teslamotors.com/'
SSO_BASE_URL = 'https://auth.tesla.com/'
SSO_CLIENT_ID = 'ownerapi'
STREAMING_BASE_URL = 'wss://streaming.vn.teslamotors.com/'
APP_USER_AGENT = 'TeslaApp/4.10.0'

# Setup module logging
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Py2/3 compatibility
try:
    input = raw_input
except NameError:
    pass


class Tesla(OAuth2Session):
    """ Implements a session manager for the Tesla Motors Owner API

    email: SSO identity.
    verify: (optional) Verify SSL certificate.
    proxy: (optional) URL of proxy server.
    retry: (optional) Number of connection retries or `Retry` instance.
    timeout: (optional) Connect/read timeout.
    user_agent: (optional) The User-Agent string.
    authenticator: (optional) Function with one argument, the authorization URL,
                   that returns the redirected URL.
    cache_file: (optional) Path to cache file used by default loader and dumper.
    cache_loader: (optional) Function that returns the cache dict.
    cache_dumper: (optional) Function with one argument, the cache dict.
    sso_base_url: (optional) URL of SSO service, set to `https://auth.tesla.cn/`
                  if your email is registered in another region.
    code_verifier (optional): PKCE code verifier string.
    app_user_agent (optional): X-Tesla-User-Agent string.

    Extra keyword arguments to pass to OAuth2Session constructor using `kwargs`:
    state (optional): A state string for CSRF protection.
    """

    def __init__(self, email, verify=True, proxy=None, retry=0, timeout=10,
                 user_agent=__name__ + '/' + __version__, authenticator=None,
                 cache_file='cache.json', cache_loader=None, cache_dumper=None,
                 sso_base_url=None, code_verifier=None,
                 app_user_agent=APP_USER_AGENT, **kwargs):
        super(Tesla, self).__init__(client_id=SSO_CLIENT_ID, **kwargs)
        if not email:
            raise ValueError('`email` is not set')
        self.email = email
        self.authenticator = authenticator or self._authenticate
        self.cache_loader = cache_loader or self._cache_load
        self.cache_dumper = cache_dumper or self._cache_dump
        self.cache_file = cache_file
        self.timeout = timeout
        self.endpoints = {}
        self.sso_base_url = sso_base_url or SSO_BASE_URL
        self._auto_refresh_url = None
        self.code_verifier = code_verifier
        # Set OAuth2Session properties
        self.scope = ('openid', 'email', 'offline_access')
        self.redirect_uri = SSO_BASE_URL + 'void/callback'
        self.auto_refresh_url = 'oauth2/v3/token'
        self.auto_refresh_kwargs = {'client_id': SSO_CLIENT_ID}
        self.token_updater = self._token_updater
        self.mount('https://', requests.adapters.HTTPAdapter(max_retries=retry))
        self.headers.update({'Content-Type': 'application/json',
                             'X-Tesla-User-Agent': app_user_agent,
                             'User-Agent': user_agent})
        self.verify = verify
        if proxy:
            self.trust_env = False
            self.proxies.update({'https': proxy})
        self._token_updater()  # Try to read token from cache
        logger.debug('Using SSO service URL %s', self.sso_base_url)

    @property
    def expires_at(self):
        """ Returns unix time when token needs refreshing """
        return self.token.get('expires_at')

    @property
    def auto_refresh_url(self):
        """ Returns refresh token endpoint URL for auto-renewal access token """
        url = urljoin(self.sso_base_url, self._auto_refresh_url)
        return url if self._auto_refresh_url else None

    @auto_refresh_url.setter
    def auto_refresh_url(self, url):
        """ Sets refresh token endpoint URL for auto-renewal of access token """
        self._auto_refresh_url = url

    def request(self, method, url, serialize=True, **kwargs):
        """ Overriddes base method to support relative URLs, serialization and
        error message handling. Raises HTTPError when an error occurs.

        method: HTTP method to use.
        url: URL to send.
        serialize (optional): (de)serialize request/response body.

        Extra keyword arguments to pass to base method using `kwargs`:
        withhold_token (optional): perform unauthenticated request.
        params (optional): URL parameters to append to the URL.
        data (optional): the body to attach to the request.
        json (optional): json for the body to attach to the request.

        Return type: JsonDict or String or requests.Response
        """
        if url.startswith(self.sso_base_url):
            return super(Tesla, self).request(method, url, **kwargs)
        # Construct URL and send request with optional serialized data
        url = urljoin(BASE_URL, url)
        kwargs.setdefault('timeout', self.timeout)
        if serialize and 'data' in kwargs:
            kwargs['json'] = kwargs.pop('data')
        response = super(Tesla, self).request(method, url, **kwargs)
        # Error message handling
        if serialize and 400 <= response.status_code < 600:
            try:
                lst = [str(v).strip('.') for v in response.json().values() if v]
                response.reason = '. '.join(lst)
            except ValueError:
                pass
        response.raise_for_status()  # Raise HTTPError, if one occurred
        # Deserialize response
        if serialize:
            return response.json(object_hook=JsonDict)
        return response.text

    @staticmethod
    def new_code_verifier():
        """ Generate code verifier for PKCE as per RFC 7636 section 4.1 """
        result = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=')
        logger.debug('Generated new code verifier %s.',
                     result.decode() if isinstance(result, bytes) else result)
        return result

    def authorization_url(self, url='oauth2/v3/authorize',
                          code_verifier=None, **kwargs):
        """ Overriddes base method to form an authorization URL with PKCE
        extension for Tesla's SSO service.

        url (optional): Authorization endpoint url.
        code_verifier (optional): PKCE code verifier string.

        Extra keyword arguments to pass to base method using `kwargs`:
        state (optional): A state string for CSRF protection.

        Return type: String or None
        """
        if self.authorized:
            return None
        # Generate code verifier and challenge for PKCE (RFC 7636)
        self.code_verifier = code_verifier or self.new_code_verifier()
        unencoded_digest = hashlib.sha256(self.code_verifier).digest()
        code_challenge = base64.urlsafe_b64encode(unencoded_digest).rstrip(b'=')
        # Prepare for OAuth 2 Authorization Code Grant flow
        url = urljoin(self.sso_base_url, url)
        kwargs['code_challenge'] = code_challenge
        kwargs['code_challenge_method'] = 'S256'
        without_hint, state = super(Tesla, self).authorization_url(url,
                                                                   **kwargs)
        # Detect account's registered region
        kwargs['login_hint'] = self.email
        kwargs['state'] = state
        with_hint = super(Tesla, self).authorization_url(url, **kwargs)[0]
        response = self.get(with_hint, allow_redirects=False)
        if response.is_redirect:
            with_hint = response.headers['Location']
            self.sso_base_url = urljoin(with_hint, '/')
            logger.debug('New SSO service URL %s', self.sso_base_url)
        return with_hint if response.ok else without_hint

    def fetch_token(self, token_url='oauth2/v3/token', **kwargs):
        """ Overriddes base method to sign into Tesla's SSO service using
        Authorization Code grant with PKCE extension. Raises CustomOAuth2Error.

        token_url (optional): Token endpoint URL.

        Extra keyword arguments to pass to base method using `kwargs`:
        authorization_response (optional): Authorization response URL.
        code_verifier (optional): Code verifier cryptographic random string.

        Return type: dict
        """
        if self.authorized:
            return self.token
        if kwargs.get('authorization_response') is None:
            # Open SSO page for user authorization through redirection
            url = self.authorization_url()
            kwargs['authorization_response'] = self.authenticator(url)
        # Use authorization code in redirected location to get token
        token_url = urljoin(self.sso_base_url, token_url)
        kwargs['include_client_id'] = True
        kwargs.setdefault('verify', self.verify)
        kwargs.setdefault('code_verifier', self.code_verifier)
        super(Tesla, self).fetch_token(token_url, **kwargs)
        self._token_updater()  # Save new token
        return self.token

    def refresh_token(self, token_url='oauth2/v3/token', **kwargs):
        """ Overriddes base method to refresh Tesla's SSO token. Raises
        ValueError and ServerError.

        token_url (optional): The token endpoint.

        Extra keyword arguments to pass to base method using `kwargs`:
        refresh_token (optional): The refresh_token to use.

        Return type: dict
        """
        if not self.authorized and not kwargs.get('refresh_token'):
            raise ValueError('`refresh_token` is not set')
        token_url = urljoin(self.sso_base_url, token_url)
        kwargs.setdefault('verify', self.verify)
        super(Tesla, self).refresh_token(token_url, **kwargs)
        self._token_updater()  # Save new token
        return self.token

    def close(self):
        """ Overriddes base method to remove all adapters on close """
        super(Tesla, self).close()
        self.adapters.clear()

    def logout(self, sign_out=False):
        """ Removes token from cache, returns logout URL, and optionally logs
        out of default browser.

        sign_out (optional): sign out using system's default web browser.

        Return type: String or None
        """
        if not self.authorized:
            return None
        url = self.sso_base_url + 'oauth2/v3/logout?client_id=' + SSO_CLIENT_ID
        # Built-in sign out method
        if sign_out:
            if webbrowser.open(url):
                logger.debug('Opened %s with default browser', url)
            else:
                print('Open this URL to sign out: ' + url)
        # Empty token dict, update cache and remove access_token
        self.token = {}
        self._token_updater()
        del self.access_token
        return url

    @staticmethod
    def _authenticate(url):
        """ Default authenticator method """
        print('Use browser to login. Page Not Found will be shown at success.')
        if webbrowser.open(url):
            logger.debug('Opened %s with default browser', url)
        else:
            print('Open this URL to authenticate: ' + url)
        return input('Enter URL after authentication: ')

    def _cache_load(self):
        """ Default cache loader method """
        try:
            with open(self.cache_file, encoding='utf-8') as infile:
                cache = json.load(infile)
        except (IOError, ValueError):
            logger.warning('Cannot load cache: %s',
                           self.cache_file, exc_info=True)
            cache = {}
        return cache

    def _cache_dump(self, cache):
        """ Default cache dumper method """
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as outfile:
                json.dump(cache, outfile)
            os.chmod(self.cache_file, (stat.S_IWUSR | stat.S_IRUSR | 
                                       stat.S_IRGRP))
        except IOError:
            logger.error('Cache not updated')
        else:
            logger.debug('Updated cache')

    def _token_updater(self, token=None):
        """ Handles token persistency. Raises ValueError. """
        if token:
            return  # Don't update token twice when auto refreshing
        cache = self.cache_loader()
        if not isinstance(cache, dict):
            raise ValueError('`cache_loader` must return dict')
        # Write token to cache
        if self.authorized:
            cache[self.email] = {'url': self.sso_base_url, 'sso': self.token}
            self.cache_dumper(cache)
        # Read token from cache
        elif self.email in cache:
            self.sso_base_url = cache[self.email].get('url', self.sso_base_url)
            self.token = cache[self.email].get('sso', {})
            if not self.token:
                return
            # Log the token validity
            if 0 < self.expires_at < time.time():
                logger.debug('Cached SSO token expired')
            else:
                logger.debug('Cached SSO token expires at %s',
                             time.ctime(self.expires_at))

    def api(self, name, path_vars=None, **kwargs):
        """ Convenience method to perform API request for given endpoint name,
        with keyword arguments as parameters. Substitutes path variables in URI
        using path_vars. Raises ValueError.

        Return type: JsonDict or String
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
        # Fetch token if not authorized and API requires authorization
        if endpoint['AUTH'] and not self.authorized:
            self.fetch_token()
        # Substitute path variables in URI
        try:
            uri = endpoint['URI'].format(**path_vars)
        except KeyError as e:
            raise ValueError('%s requires path variable %s' % (name, e))
        # Perform request using given keyword arguments as parameters
        arg_name = 'params' if endpoint['TYPE'] == 'GET' else 'json'
        serialize = endpoint.get('CONTENT') != 'HTML' and name != 'STATUS'
        return self.request(endpoint['TYPE'], uri, serialize,
                            withhold_token=not endpoint['AUTH'],
                            **{arg_name: kwargs})

    def vehicle_list(self):
        """ Returns a list of `Vehicle` objects """
        return [Vehicle(p, self) for p in self.api('PRODUCT_LIST')['response']
                if 'vehicle_id' in p]

    def battery_list(self):
        """ Returns a list of `Battery` objects """
        return [Battery(p, self) for p in self.api('PRODUCT_LIST')['response']
                if p.get('resource_type') == 'battery']

    def solar_list(self):
        """ Returns a list of `SolarPanel` objects """
        return [SolarPanel(p, self) for p in self.api('PRODUCT_LIST')['response']
                if p.get('resource_type') == 'solar']


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
        self.timestamp = time.time()

    def _subscribe(self, wsapp):
        """ Authenticate and select streaming telemetry columns """
        msg = {'msg_type': 'data:subscribe_oauth', 'value': ','.join(self.COLS),
               'token': self.tesla.access_token, 'tag': str(self['vehicle_id'])}
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
                except (SyntaxError, ValueError):
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
        self.timestamp = time.time()
        return self

    def available(self, max_age=60):
        """ Determine vehicle availability based on the cached data or the
        refreshed status when aged out. """
        if self.timestamp + max_age < time.time():
            self.get_vehicle_summary()
        return self['state'] == 'online'

    def sync_wake_up(self, timeout=60, interval=2, backoff=1.15):
        """ Wakes up vehicle if needed and waits for it to come online. Raises
        VehicleError if not woken up within timeout. """
        logger.info('%s is %s', self['display_name'], self['state'])
        if not self.available():
            self.api('WAKE_UP')  # Send wake up command
            start_time = time.time()
            while True:
                logger.debug('Waiting for %d seconds', interval)
                time.sleep(int(interval))
                if self.available(0):
                    break
                # Raise exception when task has timed out
                if start_time + timeout - interval < time.time():
                    raise VehicleError('%s not woken up within %s seconds'
                                       % (self['display_name'], timeout))
                interval *= backoff
            logger.info('%s is %s', self['display_name'], self['state'])

    @classmethod
    def decode_option(cls, code):
        """ Returns option code title or None if unknown """
        # Load option codes once
        if cls.codes is None:
            try:
                data = pkgutil.get_data(__name__, 'option_codes.json')
                cls.codes = json.loads(data.decode())
                logger.debug('%d option codes loaded', len(Vehicle.codes))
            except (IOError, ValueError):
                cls.codes = {}
                logger.error('No option codes loaded')
        # Lookup option code title
        return cls.codes.get(code)

    def option_code_list(self):
        """ Returns a list of known vehicle option code titles """
        codes = self['option_codes'] if self['option_codes'] else ''
        return list(filter(None, [self.decode_option(code)
                                  for code in codes.split(',')]))

    def get_vehicle_data(self, endpoints='location_data;charge_state;'
                                         'climate_state;vehicle_state;'
                                         'gui_settings;vehicle_config'):
        """ Allow specifying individual endpoints to query. Defaults to all
        endpoints. Raises HTTPError when vehicle is not online.

        endpoints: string containing each endpoint to query, separate with ;"""
        self.update(self.api('VEHICLE_DATA', endpoints=endpoints)['response'])
        self.timestamp = time.time()
        return self

    def get_vehicle_location_data(self, max_age=300):
        """ Get basic and location_data. Wakes vehicle if location data is not
        already present, or older than max_age seconds. Raises  HTTPError when
        vehicle is not online.

        max_age: how long in seconds before refreshing location data. Defaults
                 to 300 (5 minutes). """
        last_update = self.get('drive_state', {}).get('gps_as_of')
        # Check for cached data more recent than max_age
        if last_update is None or last_update < (time.time() - max_age):
            self.sync_wake_up()
            self.update(self.api('VEHICLE_DATA',
                                 endpoints='location_data')['response'])
            self.timestamp = time.time()
        self.timestamp = time.time()
        return self

    def get_nearby_charging_sites(self):
        """ Lists nearby Tesla-operated charging stations. Raises HTTPError when
        vehicle is in service or not online. """
        return self.api('NEARBY_CHARGING_SITES')['response']

    def get_service_scheduling_data(self):
        """ Retrieves next service appointment for this vehicle """
        response = self.api('GET_UPCOMING_SERVICE_VISIT_DATA')['response']
        return next((enabled for enabled in response['enabled_vins']
                     if enabled['vin'] == self['vin']), {})

    def get_charge_history(self):
        """ Lists vehicle charging history data points """
        return self.api('VEHICLE_CHARGE_HISTORY')['response']

    def get_charge_history_v2(self):
        """ Lists vehicle charging history data points """
        url = 'https://ownership.tesla.com/mobile-app/charging/history'
        return self.tesla.get(url, params={
            'vin': self['vin'], 'deviceLanguage': 'en', 'deviceCountry': 'US',
            'operationName': 'getChargingHistoryV2'})['data']

    def mobile_enabled(self):
        """ Checks if the Mobile Access setting is enabled in the car. Raises
        HTTPError when vehicle is in service or not online. """
        # Construct URL and send request
        uri = 'api/1/vehicles/%s/mobile_enabled' % self['id_s']
        return self.tesla.get(uri)['response']

    def compose_image(self, view='STUD_3QTR', size=640, options=None):
        """ Returns a PNG formatted composed vehicle image. Valid views are:
        STUD_3QTR, STUD_SEAT, STUD_SIDE, STUD_REAR and STUD_WHEEL """
        if options is None and self['option_codes'] is None:
            raise ValueError('`compose_image` requires `options` to be set')
        # Derive model from VIN and other properties from (given) option codes
        params = {'model': 'm' + self['vin'][3].lower(),
                  'bkba_opt': 1, 'view': view, 'size': size,
                  'options': options or self['option_codes']}
        # Retrieve image from compositor
        url = 'https://static-assets.tesla.com/v1/compositor/'
        response = requests.get(url, params=params, verify=self.tesla.verify,
                                proxies=self.tesla.proxies, timeout=30)
        response.raise_for_status()  # Raise HTTPError, if one occurred
        return response.content

    def __missing__(self, key):
        """ Get cached data when accessed. Raises KeyError on invalid key. """
        if key not in self.get_vehicle_data():
            raise KeyError(key)
        return self[key]

    def dist_units(self, miles, speed=False):
        """ Format and convert distance or speed to GUI setting units """
        if miles is None:
            return None
        # Lookup GUI settings of the vehicle
        if 'km' in self['gui_settings']['gui_distance_units']:
            return '%.1f %s' % (miles * 1.609344, 'km/h' if speed else 'km')
        return '%.1f %s' % (miles, 'mph' if speed else 'mi')

    def temp_units(self, celcius):
        """ Format and convert temperature to GUI setting units """
        if celcius is None:
            return None
        # Lookup GUI settings of the vehicle
        if 'F' in self['gui_settings']['gui_temperature_units']:
            return '%.1f F' % (celcius * 1.8 + 32)
        return '%.1f C' % celcius

    def gui_time(self, timestamp_ms=0):
        """ Returns timestamp or current time formatted to GUI setting """
        tm = time.localtime(timestamp_ms / 1000 or None)
        # Lookup GUI settings of the vehicle
        if self['gui_settings']['gui_24_hour_time']:
            return time.strftime('%H:%M:%S', tm)
        return time.strftime('%I:%M:%S %p', tm)

    def last_seen(self):
        """ Returns vehicle last seen natural time. """
        units = ((60, 'a second'), (60, 'a minute'), (24, 'an hour'),
                 (7, 'a day'), (4.35, 'a week'), (12, 'a month'), (0, 'a year'))
        diff = time.time() - self['charge_state']['timestamp'] / 1000
        if diff >= 1:
            for length, unit in units:
                if diff < length or not length:
                    if diff > 1.5:
                        unit = '%d %ss' % (round(diff), unit.split()[1])
                    return unit + ' ago'
                diff /= length
        return 'just now'

    def decode_vin(self):
        """ Returns decoded VIN as dict """
        make = 'Tesla Model ' + self['vin'][3]
        body = {
            'A': 'Hatch back 5 Dr / LHD', 'B': 'Hatch back 5 Dr / RHD',
            'C': 'Class E MPV / 5 Dr / LHD', 'E': 'Sedan 4 Dr / LHD',
            'D': 'Class E MPV / 5 Dr / RHD', 'F': 'Sedan 4 Dr / RHD',
            'G': 'Class D MPV / 5 Dr / LHD', 'H': 'Class D MPV / 5 Dr / RHD'
        }.get(self['vin'][4], 'Unknown')
        belt = {
            '1': 'Type 2 manual seatbelts (FR, SR*3) with front airbags, '
                 'PODS, side inflatable restraints, knee airbags (FR)',
            '3': 'Type 2 manual seatbelts (FR, SR*2) with front airbags, '
                 'side inflatable restraints, knee airbags (FR)',
            '4': 'Type 2 manual seatbelts (FR, SR*2) with front airbags, '
                 'side inflatable restraints, knee airbags (FR)',
            '5': 'Type 2 manual seatbelts (FR, SR*2) with front airbags, '
                 'side inflatable restraints',
            '6': 'Type 2 manual seatbelts (FR, SR*3) with front airbags, '
                 'side inflatable restraints',
            '7': 'Type 2 manual seatbelts (FR, SR*3) with front airbags, '
                 'side inflatable restraints & active hood',
            '8': 'Type 2 manual seatbelts (FR, SR*2) with front airbags, '
                 'side inflatable restraints & active hood',
            'A': 'Type 2 manual seatbelts (FR, SR*3, TR*2) with front '
                 'airbags, PODS, side inflatable restraints, knee airbags (FR)',
            'B': 'Type 2 manual seatbelts (FR, SR*2, TR*2) with front '
                 'airbags, PODS, side inflatable restraints, knee airbags (FR)',
            'C': 'Type 2 manual seatbelts (FR, SR*2, TR*2) with front '
                 'airbags, PODS, side inflatable restraints, knee airbags (FR)',
            'D': 'Type 2 Manual Seatbelts (FR, SR*3) with front airbag, '
                 'PODS, side inflatable restraints, knee airbags (FR)'
        }.get(self['vin'][5], 'Unknown')
        batt = {
            'E': 'Electric (NMC)', 'F': 'Li-Phosphate (LFP)',
            'H': 'High Capacity (NMC)', 'S': 'Standard (NMC)',
            'V': 'Ultra Capacity (NMC)'
        }.get(self['vin'][6], 'Unknown')
        drive = {'1': 'Single Motor - Standard', '2': 'Dual Motor - Standard',
                 '3': 'Single Motor - Performance', '5': 'P2 Dual Motor',
                 '4': 'Dual Motor - Performance', '6': 'P2 Tri Motor',
                 'A': 'Single Motor', 'B': 'Dual Motor - Standard',
                 'C': 'Dual Motor - Performance', 'D': 'Single Motor',
                 'E': 'Dual Motor - Standard', 'F': 'Dual Motor - Performance',
                 'P': 'Performance, Tier 7', 'G': 'Base, Tier 4',
                 'N': 'Base, Tier 7'}.get(self['vin'][7], 'Unknown')
        year = 2009 + '9ABCDEFGHJKLMNPRSTVWXY12345678'.index(self['vin'][9])
        plant = {'1': 'Menlo Park, CA, USA', '3': 'Hethel, UK',
                 'B': 'Berlin, Germany', 'C': 'Shanghai, China',
                 'F': 'Fremont, CA, USA', 'P': 'Palo Alto, CA, USA',
                 'R': 'Research'}.get(self['vin'][10], 'Unknown')
        return JsonDict(manufacturer='Tesla Motors, Inc.', make=make,
                        body_type=body, belt_system=belt, battery_type=batt,
                        drive_unit=drive, year=str(year), plant_code=plant)

    def command(self, name, **kwargs):
        """ Wrapper method for vehicle command response error handling. Raises
        VehicleError or HTTPError. """
        response = self.api(name, **kwargs).get('response')
        if not response or 'result' not in response:
            raise VehicleError(name + " doesn't seem to be a command")
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
        """ Endpoint request with site_id path variable """
        path_vars = {'site_id': self['energy_site_id']}
        return self.tesla.api(name, path_vars, **kwargs)

    def get_site_info(self):
        """ Retrieve current site/battery information """
        self.update(self.api('SITE_CONFIG')['response'])
        return self

    def get_site_data(self):
        """ Retrieve current site/battery live status """
        self.update(self.api('SITE_DATA')['response'])
        return self

    def get_calendar_history_data(
            self, kind='energy', period='day', start_date=None,
            end_date=time.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            installation_timezone=None, timezone=None, tariff=None):
        """ Retrieve live status of product
        kind: A telemetry type of 'backup', 'energy', 'power',
              'self_consumption', 'time_of_use_energy',
              'time_of_use_self_consumption', 'savings' and 'soe'
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
                        installation_timezone=installation_timezone,
                        timezone=timezone, tariff=tariff)['response']

    def get_history_data(
            self, kind='energy', period='day', start_date=None,
            end_date=time.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            installation_timezone=None, timezone=None):
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
        """
        return self.api('HISTORY_DATA', kind=kind, period=period,
                        start_date=start_date, end_date=end_date,
                        installation_timezone=installation_timezone,
                        timezone=timezone)['response']

    def command(self, name, **kwargs):
        """ Wrapper method for product command response error handling """
        response = self.api(name, **kwargs)['response']
        if response['code'] == 201:
            return response.get('message')
        raise ProductError(response.get('message'))


class BatteryTariffPeriodCost(
        namedtuple('BatteryTariffPeriodCost', ['buy', 'sell', 'name'])):
    """ Represents the costs of a tariff period
    buy: A float containing the import price
    sell: A float containing the export price
    name: The name for the period, must be 'ON_PEAK', 'PARTIAL_PEAK',
          'OFF_PEAK', or 'SUPER_OFF_PEAK'
    """
    __slots__ = ()


class BatteryTariffPeriod(
        namedtuple('BatteryTariffPeriod', ['cost', 'start', 'end'])):
    """ Represents a time period of a tariff
    cost: A BatteryTariffPeriodCost object representing the cost for this
    time period
    start: A datetime.time object representing the start time of the period
    end: A datetime.time object representing the end time of the period
    """
    __slots__ = ()


class Battery(Product):
    """ Powerwall class """

    def set_operation(self, mode):
        """ Set battery operation to self_consumption, backup or autonomous """
        return self.command('OPERATION_MODE', default_real_mode=mode)

    def set_backup_reserve_percent(self, percent):
        """ Set the minimum backup reserve percent for that battery """
        return self.command('BACKUP_RESERVE',
                            backup_reserve_percent=int(percent))

    def set_import_export(
            self, allow_grid_charging=None, allow_battery_export=None):
        """ Sets the battery grid import and export settings
        allow_grid_charging: Optional bool argument indicating if charging from
        the grid is allowed.
        allow_battery_export: Optional bool argument indicating if export to the
        grid is allowed.
        """
        params = {}
        if allow_grid_charging is not None:
            val = not allow_grid_charging
            params['disallow_charge_from_grid_with_solar_installed'] = val
        if allow_battery_export is not None:
            val = 'battery_ok' if allow_battery_export else 'pv_only'
            params['customer_preferred_export_rule'] = val
        # This endpoint returns an empty responce instead of a result code, so
        # api() is called instead of using command()
        self.api('ENERGY_SITE_IMPORT_EXPORT_CONFIG', **params)

    def get_tariff(self):
        """ Get the tariff rate data """
        return self.api('SITE_TARIFF')['response']

    def set_tariff(self, tariff_data):
        """ Set the tariff rate data. The data can be created manually, or
        generated by create_tariff """
        return self.command('TIME_OF_USE_SETTINGS',
                            tou_settings={"tariff_content": tariff_data})

    @staticmethod
    def create_tariff(default_price, periods, provider, plan):
        """ Creates a correctly formatted dictionary of tariff data
        default_price: A BatteryTariffPeriodCost object representing the price
        of the background time period
        periods: A list of BatteryTariffPeriod objects representing times with
        higher prices than the background time period
        provider: The name of the energy provider
        plan: The name of the plan
        """
        midnight_start_time = datetime.time(hour=0)
        midnight_end_time = datetime.time(hour=23, minute=59, second=59)
        background_time = [[midnight_start_time, midnight_end_time]]

        # Subtract each of the time periods from the background time
        costs = defaultdict(list)
        for period in periods:
            slot_found = False
            # go through items in the background time searching for a slot that
            # completely encompas the period we're trying to add
            for (index, bg_period) in enumerate(background_time[:]):
                if bg_period[0] <= period.start and period.end <= bg_period[1]:
                    slot_found = True
                    # If the period matches the start/end times, then we just
                    # need to adjust the existing background time slot.
                    # Otherwise we need to split it.
                    if bg_period[0] == period.start:
                        background_time[index][0] = period.end
                    elif bg_period[1] == period.end:
                        background_time[index][1] = period.start
                    else:
                        background_time.append([period.end, bg_period[1]])
                        background_time[index][1] = period.start
            if not slot_found:
                return None
            # Update the list of prices
            costs[period.cost].append(period)

            # The loop above can leave background time slots with zero duration.
            # It's difficult to filter them out above as the list indexes can
            # get out of sync as we end up modifying the array being iterated
            # over. As a result it's easier to filter out invalid background
            # slots now.
            background_time = list(filter(lambda t: t[0] != t[1],
                                          background_time))

        # add the background time slots to the costs array
        costs[default_price] = [BatteryTariffPeriod(default_price, x[0], x[1])
                                for x in background_time]

        tou_periods = {}
        buy_price_info = {}
        sell_price_info = {}
        for cost in sorted(costs, reverse=True):
            name = cost.name
            buy_price_info[name] = cost.buy
            sell_price_info[name] = cost.sell
            periods_for_cost = []
            for period in costs[cost]:
                # Map the second before midnight back to midnight, after
                # the time comparisons. This is required to get the json
                # in the right format
                if period.end == midnight_end_time:
                    period = period._replace(end=midnight_start_time)
                periods_for_cost.append({
                    "fromDayOfWeek": 0, "fromHour": period.start.hour,
                    "fromMinute": period.start.minute, "toDayOfWeek": 6,
                    "toHour": period.end.hour,
                    "toMinute": period.end.minute})
            tou_periods[name] = periods_for_cost

        # Build the final dict
        demand_changes = {"ALL": {"ALL": 0}, "Summer": {}, "Winter": {}}
        daily_charges = [{"name":   "Charge", "amount": 0}]
        seasons = {"Summer": {"fromMonth": 1, "fromDay": 1, "toDay": 31,
                              "toMonth": 12, "tou_periods": tou_periods},
                   "Winter": {"tou_periods": {}}}
        return JsonDict(
            daily_charges=daily_charges, demand_charges=demand_changes,
            name=plan, utility=provider, seasons=seasons,
            energy_charges={"ALL": {"ALL": 0}, "Summer": buy_price_info,
                            "Winter": {}},
            sell_tariff={"daily_charges": daily_charges,
                         "demand_charges": demand_changes, "name": plan,
                         "utility": provider, "seasons": seasons,
                         "energy_charges": {"ALL": {"ALL": 0},
                                            "Summer": sell_price_info,
                                            "Winter": {}}})


class SolarPanel(Product):
    """ Solar panel class """
    pass
