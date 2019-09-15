""" This module provides access the Tesla Motors API and handles OAuth 2.0
password granting and bearer tokens. Tokens are saved to disk for reuse. It
requires a login and password to teslamotors.com and a client ID and secret.
"""

# Author: Tim Dorssers

import json
import time
import logging
import requests
from requests.exceptions import *

requests.packages.urllib3.disable_warnings()

class Tesla(requests.Session):
    """ Implements a session manager to the Tesla API """

    def __init__(self, email, password, client_id, client_secret, proxy=None):
        super(Tesla, self).__init__()
        self.email = email
        self.password = password
        self.client_id = client_id
        self.client_secret = client_secret
        self.authorized = False
        self.endpoints = {}
        # Set Session properties
        self.headers.update({'Content-Type': 'application/json'})
        self.verify = False
        if proxy:
            self.trust_env = False
            self.proxies.update({'https': proxy})
        self._token_updater()  # Read token from cache

    def request(self, method, uri, data=None, **kwargs):
        """ Extends base class method to support bearer token insertion. Raises
        HTTPError when an error occurs. """
        # Auto refresh token and insert access token into headers
        if self.authorized:
            if 0 < self.expires_at < time.time():
                self.refresh_token()
            self.headers.update({'Authorization': 'Bearer '
                                 + self.token['access_token']})
        # Construct URL, serialize data and send request
        url = 'https://owner-api.teslamotors.com/' + uri.strip('/')
        data = json.dumps(data).encode('utf-8') if data is not None else None
        response = super(Tesla, self).request(method, url, data=data, **kwargs)
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
        """ Requests a new bearer token using password grant """
        if not self.authorized:
            if not self.password:
                raise ValueError('Password required')
            data = {'grant_type': 'password',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'email': self.email, 'password': self.password}
            # Request new token
            response = self.api('AUTHENTICATE', data=data)
            if 'access_token' in response:
                self.token = response
                self.expires_at = (self.token['created_at']
                                   + self.token['expires_in'])
                logging.debug('Got new token, expires at '
                              + time.ctime(self.expires_at))
                self.authorized = True
            # Save new token or read cached token if applicable
            self._token_updater()

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
                logging.debug('Cached token, expires at '
                              + time.ctime(self.expires_at))

    def refresh_token(self):
        """ Requests a new token using a refresh token """
        if self.authorized:
            self.expires_at = 0
            data = {'grant_type': 'refresh_token',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'refresh_token': self.token['refresh_token']}
            # Request new token
            response = self.api('AUTHENTICATE', data=data)
            if 'access_token' in response:
                self.token = response
                self.expires_at = (self.token['created_at']
                                   + self.token['expires_in'])
                logging.debug('Refreshed token, expires '
                              + time.ctime(self.expires_at))
                self._token_updater()  # Update cache

    def api(self, name, path_vars={}, **kwargs):
        """ Convenience method to perform API request for given endpoint name,
        with keyword arguments as parameters. Substitutes path variables in URI
        using path_vars. Raises ValueError if endpoint name is not found. """
        # Load API endpoints once
        if not self.endpoints:
            try:
                with open('endpoints.json') as infile:
                    self.endpoints = json.load(infile)
                    logging.debug('%d endpoints loaded' % len(self.endpoints))
            except (IOError, ValueError):
                logging.error('No endpoints loaded')
        # Lookup endpoint name
        try:
            endpoint = self.endpoints[name]
        except KeyError:
            raise ValueError('Unknown endpoint name ' + name)
        # Only JSON is supported
        if endpoint.get('CONTENT', 'JSON') != 'JSON':
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
        # Perform request using given keyword arguments as parameters
        if kwargs:
            logging.debug('%s: %s' % (name, json.dumps(kwargs)))
        return self.request(endpoint['TYPE'], uri, data=kwargs)

    def vehicle_list(self):
        """ Returns a list of Vehicle objects """
        return [Vehicle(v, self) for v in self.api('VEHICLE_LIST')['response']]

class TimeoutError(Exception):
    """ Custom exception raised when a wake up task has timed out """
    pass

class JsonDict(dict):
    """ Dictionary for pretty printing """

    def __str__(self):
        """ Serialize dict to JSON formatted string with indents """
        return json.dumps(self, indent=4)

class Vehicle(JsonDict):
    """ Vehicle class with dictionary access and API request support """

    def __init__(self, vehicle, tesla):
        super(Vehicle, self).__init__(vehicle)
        self.tesla = tesla
        self.codes = {}

    def api(self, name, **kwargs):
        """ Endpoint request with vehicle_id path variable """
        return self.tesla.api(name, {'vehicle_id': self['id_s']}, **kwargs)

    def get_vehicle_summary(self):
        """ Determine the state of the vehicle's various sub-systems """
        self.update(self.api('VEHICLE_SUMMARY')['response'])
        return self

    def sync_wake_up(self, timeout=60, interval=2, backoff=1.15):
        """ Wakes up vehicle if needed and waits for it to come online """
        logging.info('%s is %s' % (self['display_name'], self['state']))
        if self['state'] != 'online':
            self.api('WAKE_UP')  # Send wake up command
            start_time = time.time()
            while self['state'] != 'online':
                logging.debug('Waiting for %d seconds' % interval)
                time.sleep(int(interval))
                # Get vehicle status
                self.get_vehicle_summary()
                # Raise exception when task has timed out
                if (start_time + timeout < time.time()):
                    raise TimeoutError('%s not woken up within %s seconds' %
                                       (self['display_name'], timeout))
                interval *= backoff
            logging.info('%s is %s' % (self['display_name'], self['state']))

    def option_code_list(self):
        """ Returns a list of known option code titles """
        # Load option codes once
        if not self.codes:
            try:
                with open('option_codes.json') as infile:
                    self.codes = json.load(infile)
                    logging.debug('%d option codes loaded' % len(self.codes))
            except (IOError, ValueError):
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
        if not 'gui_settings' in self:
            self.get_vehicle_data()
        # Lookup GUI settings of the vehicle
        if 'km' in self['gui_settings']['gui_distance_units']:
            return '%.1f %s' % (miles * 1.609344, 'km/h' if speed else 'km')
        else:
            return '%.1f %s' % (miles, 'mph' if speed else 'mi')

    def temp_units(self, celcius):
        """ Format and convert temperature to GUI setting units """
        if not 'gui_settings' in self:
            self.get_vehicle_data()
        # Lookup GUI settings of the vehicle
        if 'F' in self['gui_settings']['gui_temperature_units']:
            return '%.1f F' % (celcius * 1.8 + 32)
        else:
            return '%.1f C' % celcius

    def decode_vin(self):
        """ Returns decoded VIN as dict """
        make = 'Model ' + self['vin'][3]
        body = {'A': 'Hatchback 5 Dr / LHD', 'B': 'Hatchback 5 Dr / RHD',
                'C': 'MPV / 5 Dr / LHD', 'D': 'MPV / 5 Dr / RHD',
                'E': 'Sedan 4 Dr / LHD',
                'F': 'Sedan 4 Dr / RHD'}.get(self['vin'][4], 'Unknown')
        batt = {'E': 'Electric', 'H': 'High Capacity', 'S': 'Standard Capacity',
                'V': 'Ultra Capacity'}.get(self['vin'][6], 'Unknown')
        drive = {'1': 'Single Motor', '2': 'Dual Motor',
                 '3': 'Performance Single Motor', 'C': 'Base, Tier 2',
                 '4': 'Performance Dual Motor', 'P': 'Performance, Tier 7',
                 'A': 'Single Motor', 'B': 'Dual Motor', 'G': 'Base, Tier 4',
                 'N': 'Base, Tier 7'}.get(self['vin'][7], 'Unknown')
        year = 2009 + '9ABCDEFGHJKLMNPRSTVWXY12345678'.index(self['vin'][9])
        plant = {'F': 'Fremont, CA, USA',
                 'P': 'Palo Alto, CA, USA'}.get(self['vin'][10], 'Unknown')
        return JsonDict(manufacturer='Tesla Motors, Inc.',
                        make=make, body_type=body, battery_type=batt,
                        drive_unit=drive, year=str(year), plant_code=plant)

    def remote_start_drive(self):
        """ Enables keyless driving for two minutes """
        if not self.tesla.password:
            raise ValueError('Password required')
        return self.api('REMOTE_START', password=self.tesla.password)
