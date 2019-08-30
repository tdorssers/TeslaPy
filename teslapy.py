""" This module provides access the Tesla Motors API and handles OAuth 2.0
password granting and bearer tokens. Tokens are saved to disk for reuse. It
requires a login and password to teslamotors.com and a client ID and secret.
"""

# Author: Tim Dorssers

import json
import time
import logging
import requests
from requests import HTTPError

requests.packages.urllib3.disable_warnings()

class Tesla(requests.Session):
    """ Implements a session manager to the Tesla API """

    def __init__(self, email, password, client_id, client_secret):
        super(Tesla, self).__init__()
        self.email = email
        self.password = password
        self.client_id = client_id
        self.client_secret = client_secret
        self.authorized = False
        self.endpoints = {}
        self.headers.update({'Content-Type': 'application/json'})
        self.verify = False
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
                response.reason = ', '.join('%s: %s' % (k, v)
                                            for k, v in response.json().items())
            except ValueError:
                response.reason = response.text
        response.raise_for_status()  # Raise HTTPError, if one occurred
        # Deserialize response
        return response.json()
        
    def fetch_token(self):
        """ Requests a new bearer token using password grant """
        if not self.authorized:
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
        """ Convenience method to perform API request for given endpoint name.
        Substitutes path variables in URI using given dict. Raises ValueError
        if endpoint name is not found. """
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
            ep = self.endpoints[name]
        except KeyError:
            raise ValueError('Unknown endpoint name ' + name)
        # Only JSON is supported
        if ep.get('CONTENT', 'JSON') != 'JSON':
            raise NotImplementedError('Endpoint %s not implemented' % name)
        # Fetch token if not authorized and API requires authorization
        if ep['AUTH'] and not self.authorized:
            self.fetch_token()
        # Perform request using given parameters
        return self.request(ep['TYPE'], ep['URI'].format(**path_vars), **kwargs)

    def vehicle_list(self):
        """ Returns a list of Vehicle objects """
        return [Vehicle(v, self) for v in self.api('VEHICLE_LIST')['response']]

class TimeoutError(Exception):
    """ Custom exception raised when a wake up task has timed out """
    pass

class Vehicle(dict):
    """ Vehicle class with dictionary access and API request support """

    def __init__(self, vehicle, tesla):
        super(Vehicle, self).__init__(vehicle)
        self.tesla = tesla
        self.codes = {}

    def __str__(self):
        """ Serialize dict to JSON formatted string with indents """
        return json.dumps(self, indent=4)

    def api(self, name, **kwargs):
        """ Endpoint request with vehicle_id path variable """
        return self.tesla.api(name, {'vehicle_id': self['id']}, **kwargs)

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
                self.update(self.api('VEHICLE_SUMMARY')['response'])
                # Raise exception when task has timed out
                if (start_time + timeout < time.time()):
                    raise TimeoutError('%s not woken within %s seconds' %
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
        uri = 'api/1/vehicles/%s/mobile_enabled' % self['id']
        return self.tesla.get(uri)['response']
