""" This module provides access the Tesla Motors Owner API. It uses Tesla's new
RFC compliant OAuth 2 Single Sign-On service and supports Time-based One-Time
Passwords. Access token is saved to disk for reuse. The API endpoints are loaded
from 'endpoints.json'.
"""

# Author: Tim Dorssers

import os
import json
import time
import base64
import hashlib
import logging
import pkgutil
try:
    from HTMLParser import HTMLParser
except ImportError:
    from html.parser import HTMLParser
import requests
from requests_oauthlib import OAuth2Session


requests.packages.urllib3.disable_warnings()

BASE_URL = 'https://owner-api.teslamotors.com/'
CLIENT_ID = 'e4a9949fcfa04068f59abb5a658f2bac0a3428e4652315490b659d5ab3f35a9e'
SSO_BASE_URL = 'https://auth.tesla.com/'
SSO_CLIENT_ID = 'ownerapi'


class Tesla(requests.Session):
    """ Implements a session manager for the Tesla Motors Owner API """

    def __init__(self, email, password, passcode_getter=None, proxy=None):
        super(Tesla, self).__init__()
        if not email:
            raise ValueError('Identity required')
        self.email = email
        self.password = password
        self.passcode_getter = passcode_getter
        self.token = {}
        self.expires_at = 0
        self.authorized = False
        self.endpoints = {}
        # Set Session properties
        self.headers.update({'Content-Type': 'application/json'})
        self.verify = False
        if proxy:
            self.trust_env = False
            self.proxies.update({'https': proxy})
        self._token_updater()  # Try to read token from cache

    def request(self, method, uri, data=None, **kwargs):
        """ Extends base class method to support bearer token insertion. Raises
        HTTPError when an error occurs. """
        # Auto refresh token and insert access token into headers
        if self.authorized:
            if 0 < self.expires_at < time.time():
                self.authorized = False
                self.fetch_token()
            self.headers.update({'Authorization':
                                 'Bearer ' + self.token['access_token']})
        # Construct URL, serialize data and send request
        url = BASE_URL + uri.strip('/')
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
        """ Sign in using Tesla's SSO service and request JWT bearer """
        if self.authorized:
            return
        if not self.password:
            raise ValueError('Password required')
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
        url = SSO_BASE_URL + 'oauth2/v3/authorize'
        auth_url, state = oauth.authorization_url(url,
                                                  code_challenge=code_challenge,
                                                  code_challenge_method='S256')
        # Retrieve SSO page and parse input objects on HTML form
        form = HTMLForm()
        form.feed(oauth.get(auth_url).text)
        # Send login credentials to get authorization response code
        form.data.update({'identity': self.email, 'credential': self.password})
        auth_resp = oauth.post(SSO_BASE_URL + 'oauth2/v3/authorize',
                               data=form.data, allow_redirects=False)
        auth_resp.raise_for_status()  # Raise HTTPError, if one occurred
        if auth_resp.status_code == 200:
            form.feed(auth_resp.text)
            if not form.data['credential']:
                raise ValueError('Invalid credential')
            # Check for MFA factors
            params = {'transaction_id': form.data['transaction_id']}
            url = SSO_BASE_URL + 'oauth2/v3/authorize/mfa/factors'
            response = oauth.get(url, params=params)
            response.raise_for_status()  # Raise HTTPError, if one occurred
            factors = response.json()['data']
            # Only one factor and only TOTP is supported
            if len(factors) == 1:
                if factors[0]['factorType'] != 'token:software':
                    raise NotImplementedError(factors[0]['factorType']
                                              + ' factor not supported')
                if not self.passcode_getter:
                    raise ValueError('passcode_getter method is not set')
                # Get passcode and verify
                data = {'transaction_id': form.data['transaction_id'],
                        'factor_id': factors[0]['id'],
                        'passcode': self.passcode_getter()}
                url = SSO_BASE_URL + 'oauth2/v3/authorize/mfa/verify'
                response = oauth.post(url, json=data)
                if ('error' in response.json() or
                        not response.json()['data']['valid']):
                    raise ValueError('Invalid passcode')
                # Get authorization response code
                data = {'transaction_id': form.data['transaction_id']}
                auth_resp = oauth.post(SSO_BASE_URL + 'oauth2/v3/authorize',
                                       data=data, allow_redirects=False)
            elif len(factors) > 1:
                raise NotImplementedError('Multiple MFA factors not supported')
        # Use authorization response code in redirected location to get token
        if auth_resp.status_code != 302:
            raise RuntimeError('Authorization error')
        oauth.fetch_token(SSO_BASE_URL + 'oauth2/v3/token',
                          authorization_response=auth_resp.headers['Location'],
                          include_client_id=True, code_verifier=code_verifier)
        # Perform RFC 7523 JSON web token exchange for Owner API access
        data = {'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                'client_id': CLIENT_ID}
        response = oauth.post(BASE_URL + 'oauth/token', data=data)
        response.raise_for_status()  # Raise HTTPError, if one occurred
        self.token = response.json()
        self.expires_at = self.token['created_at'] + self.token['expires_in']
        logging.debug('Got JWT bearer, expires at %s',
                      time.ctime(self.expires_at))
        self.authorized = True
        self._token_updater()  # Save new token

    def _token_updater(self):
        """ Handles token persistency """
        # Open cache file
        try:
            with open('cache.json') as infile:
                cache = json.load(infile)
        except (IOError, ValueError):
            cache = {}
        # Write token to cache file
        if self.authorized:
            cache[self.email] = self.token
            try:
                with open('cache.json', 'w') as outfile:
                    json.dump(cache, outfile)
            except IOError:
                logging.error('Cache not updated')
            else:
                logging.debug('Updated cache')
        # Read token from cache
        elif self.email in cache:
            self.token = cache[self.email]
            self.expires_at = (self.token['created_at']
                               + self.token['expires_in'])
            # Check if token is valid
            if 0 < self.expires_at < time.time():
                logging.debug('Cached token expired')
                self.fetch_token()
            else:
                self.authorized = True
                logging.debug('Cached token, expires at %s',
                              time.ctime(self.expires_at))

    def api(self, name, path_vars=None, **kwargs):
        """ Convenience method to perform API request for given endpoint name,
        with keyword arguments as parameters. Substitutes path variables in URI
        using path_vars. Raises ValueError if endpoint name is not found. """
        path_vars = path_vars or {}
        # Load API endpoints once
        if not self.endpoints:
            try:
                data = pkgutil.get_data(__name__, 'endpoints.json')
                self.endpoints = json.loads(data.decode())
                logging.debug('%d endpoints loaded', len(self.endpoints))
            except (IOError, ValueError):
                logging.error('No endpoints loaded')
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
        uri = endpoint['URI']
        try:
            uri = uri.format(**path_vars)
        except KeyError as e:
            raise ValueError('%s requires path variable %s' % (name, e))
        # Hide password in debug logging parameters
        log = {k: v if k != 'password' else '***' for k, v in kwargs.items()}
        if log:
            logging.debug('%s: %s', name, json.dumps(log))
        # Perform request using given keyword arguments as parameters
        return self.request(endpoint['TYPE'], uri, data=kwargs)

    def vehicle_list(self):
        """ Returns a list of Vehicle objects """
        return [Vehicle(v, self) for v in self.api('VEHICLE_LIST')['response']]


class HTMLForm(HTMLParser):
    """ Parse input tags on HTML form """

    def __init__(self):
        self.data = {}
        HTMLParser.__init__(self)

    def handle_starttag(self, tag, attrs):
        """ Make dictionary of name and value attributes of input tags """
        if tag == 'input':
            self.data[dict(attrs)['name']] = dict(attrs).get('value', '')


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

    def __init__(self, vehicle, tesla):
        super(Vehicle, self).__init__(vehicle)
        self.tesla = tesla

    def api(self, name, **kwargs):
        """ Endpoint request with vehicle_id path variable """
        return self.tesla.api(name, {'vehicle_id': self['id_s']}, **kwargs)

    def get_vehicle_summary(self):
        """ Determine the state of the vehicle's various sub-systems """
        self.update(self.api('VEHICLE_SUMMARY')['response'])
        return self

    def sync_wake_up(self, timeout=60, interval=2, backoff=1.15):
        """ Wakes up vehicle if needed and waits for it to come online """
        logging.info('%s is %s', self['display_name'], self['state'])
        if self['state'] != 'online':
            self.api('WAKE_UP')  # Send wake up command
            start_time = time.time()
            while self['state'] != 'online':
                logging.debug('Waiting for %d seconds', interval)
                time.sleep(int(interval))
                # Get vehicle status
                self.get_vehicle_summary()
                # Raise exception when task has timed out
                if start_time + timeout < time.time():
                    raise VehicleError('%s not woken up within %s seconds'
                                       % (self['display_name'], timeout))
                interval *= backoff
            logging.info('%s is %s', self['display_name'], self['state'])

    def option_code_list(self):
        """ Returns a list of known option code titles """
        # Load option codes once
        if Vehicle.codes is None:
            try:
                data = pkgutil.get_data(__name__, 'option_codes.json')
                Vehicle.codes = json.loads(data.decode())
                logging.debug('%d option codes loaded', len(Vehicle.codes))
            except (IOError, ValueError):
                Vehicle.codes = {}
                logging.error('No option codes loaded')
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

    def mobile_enabled(self):
        """ Checks if the Mobile Access setting is enabled in the car """
        # Construct URL and send request
        uri = 'api/1/vehicles/%s/mobile_enabled' % self['id_s']
        return self.tesla.get(uri)['response']

    def compose_image(self, view='STUD_3QTR', size=640):
        """ Returns a PNG formatted composed vehicle image. Valid views are:
        STUD_3QTR, STUD_SEAT, STUD_SIDE, STUD_REAR and STUD_WHEEL """
        # Derive model from VIN and other properties from option codes
        params = {'model': 'm' + self['vin'][3].lower(), 'bkba_opt': 1,
                  'view': view, 'size': size, 'options': self['option_codes']}
        # Retrieve image from compositor
        url = 'https://static-assets.tesla.com/v1/compositor/'
        response = requests.get(url, params=params, verify=False,
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
            raise ValueError('Password required')
        return self.command('REMOTE_START', password=self.tesla.password)

    def command(self, name, **kwargs):
        """ Wrapper method for vehicle command response error handling """
        response = self.api(name, **kwargs)['response']
        if not response['result']:
            raise VehicleError(response['reason'])
        return response['result']
