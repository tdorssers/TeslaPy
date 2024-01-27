# TeslaPy

A Python implementation based on [unofficial documentation](https://tesla-api.timdorr.com/) of the client side interface to the Tesla Motors Owner API, which provides functionality to monitor and control Tesla products remotely.

The Owner API will [stop working](https://developer.tesla.com/docs/fleet-api#2023-11-17-vehicle-commands-endpoint-deprecation-timeline-action-required) as vehicles begin requiring end-to-end command authentication using the Tesla Vehicle Command Protocol. Pre-2021 Model S and X vehicles do not support this new protocol and remain controllable using TeslaPy.

[![Version](https://img.shields.io/pypi/v/TeslaPy)](https://pypi.org/project/TeslaPy)
[![Downloads](https://static.pepy.tech/badge/TeslaPy/month)](https://pepy.tech/project/TeslaPy)

## Overview

This module depends on Python [requests](https://pypi.org/project/requests/), [requests_oauthlib](https://pypi.org/project/requests-oauthlib/) and [websocket-client](https://pypi.org/project/websocket-client/). It requires Python 3.10+ when using urllib3 2.0, which comes with requests 2.30.0+, or you can pin urllib3 to 1.26.x by installing `urllib3<2`.

The `Tesla` class extends `requests_oauthlib.OAuth2Session` which extends `requests.Session` and therefore inherits methods like `get()` and `post()` that can be used to perform API calls. Module characteristics:

* It implements Tesla's new [OAuth 2](https://oauth.net/2/) Single Sign-On service.
* Acquired tokens are stored in current working directory in *cache.json* file for persistence by default.
* The cache stores tokens of each authorized identity (email).
* Authentication is only needed when a new token is requested (usually once).
* The token is automatically refreshed when expired without the need to reauthenticate.
* An email registered in another region (e.g. auth.tesla.cn) is also supported.
* Streaming API support using a [WebSocket](https://datatracker.ietf.org/doc/html/rfc6455).
* Pluggable cache and authenticator methods.

TeslaPy 2.0.0+ no longer implements headless authentication. The constructor differs and takes these arguments:

| Argument | Description |
| --- | --- |
| `email` | SSO identity |
| `verify` | (optional) verify SSL certificate |
| `proxy` | (optional) URL of proxy server |
| `retry` | (optional) number of connection retries or `Retry` instance |
| `timeout` | (optional) Connect/read timeout |
| `user_agent` | (optional) the User-Agent string |
| `authenticator` | (optional) Function with one argument, the authorization URL, that returns the redirected URL |
| `cache_file` | (optional) path to cache file used by default loader and dumper |
| `cache_loader` | (optional) function that returns the cache dict |
| `cache_dumper` | (optional) function with one argument, the cache dict |
| `sso_base_url` | (optional) URL of SSO service, set to `https://auth.tesla.cn/` if your email is registered in another region |
| `state` | (optional) state string for CSRF protection |
| `code_verifier` | (optional) PKCE code verifier string |
| `app_user_agent` | (optional) X-Tesla-User-Agent string |

TeslaPy 2.1.0+ no longer implements [RFC 7523](https://tools.ietf.org/html/rfc7523) and uses the SSO token for all API requests.

The class will open Tesla's SSO page in the system's default web browser to authenticate. After successful authentication, a *Page not found* will be displayed and the URL should start with `https://auth.tesla.com/void/callback`, which is the redirected URL. The class will use `stdio` to get the full redirected URL from the web browser by default. You need to copy and paste the full URL from the web browser to the console to continue aquirering API tokens. You can use a pluggable authenticator method to automate this, for example using [pywebview](https://pypi.org/project/pywebview/) or [selenium](https://pypi.org/project/selenium/). It is also possible to use an SSO refresh token obtained by a 3rd party authentication app.

The convenience method `api()` uses named endpoints listed in *endpoints.json* to perform calls, so the module does not require changes if the API is updated. `api()` substitutes path variables in the URI and calls `fetch_token()` when needed. Any error message returned by the API is raised as an `HTTPError` exception. Additionally, the class implements the following methods:

| Call | Description |
| --- | --- |
| `request()` | performs API call using relative or absolute URL, serialization and error message handling |
| `new_code_verifier()` | generates code verifier for [PKCE](https://oauth.net/2/pkce/) |
| `authorization_url()` | forms authorization URL with [PKCE](https://oauth.net/2/pkce/) extension and tries to detect the accounts registered region |
| `fetch_token()` | requests an SSO token using Authorization Code grant with [PKCE](https://oauth.net/2/pkce/) extension |
| `refresh_token()` | requests an SSO token using [Refresh Token](https://oauth.net/2/grant-types/refresh-token/) grant |
| `close()` | remove all requests adapter instances |
| `logout()` | removes token from cache, returns logout URL and optionally signs out using system's default web browser |
| `vehicle_list()` | returns a list of Vehicle objects |
| `battery_list()` | returns a list of Battery objects |
| `solar_list()` | returns a list of SolarPanel objects |

The `Vehicle` class extends `dict` and stores vehicle data returned by the Owner API, which is a pull API. The `get_vehicle_summary()` and `get_vehicle_data()` calls update the `Vehicle` instance, merging data. The streaming API pushes vehicle data on-change after subscription. The `stream()` method takes an optional argument, a callback function that is called with one argument, a dict holding the changed data. The `Vehicle` object is always updated with the pushed data. If there are no changes within 10 seconds, the vehicle stops streaming data. The `stream()` method has two more optional arguments to control restarting. Additionally, the class implements the following methods:

| Call | Online | Description |
| --- | --- | --- |
| `api()` | Yes | performs an API call to named endpoint requiring vehicle_id with optional arguments |
| `get_vehicle_summary()` | No | gets the state of the vehicle (online, asleep, offline) |
| `available()` | No | checks if the vehicle is online based on cached data or refreshed status when aged out |
| `sync_wake_up()` | No | wakes up and waits for the vehicle to come online |
| `decode_option()` | No | lookup option code description (read from *option_codes.json*) |
| `option_code_list()` <sup>1</sup> | No | lists known descriptions of the vehicle option codes |
| `get_vehicle_data()` | Yes | get vehicle data for selected endpoints, defaults to all endpoints|
| `get_vehicle_location_data()` | Yes | gets the basic and location data for the vehicle|
| `get_nearby_charging_sites()` | Yes | lists nearby Tesla-operated charging stations |
| `get_service_scheduling_data()` | No | retrieves next service appointment for this vehicle |
| `get_charge_history()` <sup>2</sup> | No | lists vehicle charging history data points |
| `mobile_enabled()` | Yes | checks if the Mobile Access setting is enabled in the car |
| `compose_image()` <sup>3</sup> | No | composes a vehicle image based on vehicle option codes |
| `dist_units()` | No | converts distance or speed units to GUI setting of the vehicle |
| `temp_units()` | No | converts temperature units to GUI setting of the vehicle |
| `gui_time()` | No | returns timestamp or current time formatted to GUI setting |
| `last_seen()` | No | returns vehicle last seen natural time |
| `decode_vin()` | No | decodes the vehicle identification number to a dict |
| `command()` | Yes | wrapper around `api()` for vehicle command response error handling |

<sup>1</sup> Option codes appear to be deprecated.

<sup>2</sup> Car software version 2021.44.25 or higher required, Data Sharing must be enabled and you must be the primary vehicle owner.

<sup>3</sup> Pass vehicle option codes to this method now options codes are deprecated.

Only methods with *No* in the *Online* column are available when the vehicle is asleep or offline. These methods will not prevent your vehicle from sleeping. Other methods and API calls require the vehicle to be brought online by using `sync_wake_up()` and can prevent your vehicle from sleeping if called within too short a period.

The `Product` class extends `dict` and is initialized with product data of Powerwalls and solar panels returned by the API. Additionally, the class implements the following methods:

| Call | Description |
| --- | --- |
| `api()` | performs an API call to named endpoint requiring battery_id or site_id with optional arguments |
| `get_history_data()` | Retrieve live status of product |
| `get_calendar_history_data()` | Retrieve live status of product |
| `command()` | wrapper around `api()` for battery command response error handling |

The `Battery` class extends `Product` and stores Powerwall data returned by the API, updated by `get_battery_data()`. Additionally, the class implements the following methods:

| Call | Description |
| --- | --- |
| `get_battery_data()` | Retrieve detailed state and configuration of the battery |
| `set_operation()` | Set battery operation to self_consumption, backup or autonomous |
| `set_backup_reserve_percent()` | Set the minimum backup reserve percent for that battery |
| `set_import_export()` | Sets the battery grid import and export settings |
| `get_tariff()` | Get the tariff rate data |
| `set_tariff()` | Set the tariff rate data. The data can be created manually, or generated by create_tariff |
| `create_tariff()` | Creates a correctly formatted dictionary of tariff data |

The `SolarPanel` class extends `Product` and stores solar panel data returned by the API, updated by `get_site_data()`. Additionally, the class implements the following methods:

| Call | Description |
| --- | --- |
| `get_site_data()` | Retrieve current site generation data |

## Usage

Basic usage of the module:

```python
import teslapy
with teslapy.Tesla('elon@tesla.com') as tesla:
    vehicles = tesla.vehicle_list()
    vehicles[0].sync_wake_up()
    vehicles[0].command('ACTUATE_TRUNK', which_trunk='front')
    vehicles[0].get_vehicle_data()
    print(vehicles[0]['vehicle_state']['car_version'])
```

TeslaPy 2.4.0 and 2.5.0 automatically calls `get_vehicle_data()` and TeslaPy 2.6.0+ automatically calls `get_latest_vehicle_data()` when a key is not found. This example works for TeslaPy 2.6.0+:

```python
import teslapy
with teslapy.Tesla('elon@tesla.com') as tesla:
    vehicles = tesla.vehicle_list()
    print(vehicles[0]['display_name'] + ' last seen ' + vehicles[0].last_seen() +
          ' at ' + str(vehicles[0]['charge_state']['battery_level']) + '% SoC')
```

Example output:

`Tim's Tesla last seen 6 hours ago at 87% SoC`

### Authentication

The `Tesla` class implements a pluggable authentication method. If you want to implement your own method to handle the SSO page and retrieve the redirected URL after authentication, you can pass a function as an argument to the constructor, that takes the authentication URL as an argument and returns the redirected URL. The `authenticator` argument is accessible as an attribute as well.

#### pywebview

Example using a webview component that displays the SSO page in its own native GUI window.

```python
import teslapy
import webview

def custom_auth(url):
    result = ['']
    window = webview.create_window('Login', url)
    def on_loaded():
        result[0] = window.get_current_url()
        if 'void/callback' in result[0].split('?')[0]:
            window.destroy()
    window.loaded += on_loaded
    webview.start()
    return result[0]

with teslapy.Tesla('elon@tesla.com', authenticator=custom_auth) as tesla:
    tesla.fetch_token()
```

#### selenium

Example using selenium to automate web browser interaction. The SSO page returns a 403 when `navigator.webdriver` is set and currently only Chrome, Opera and Edge Chromium can prevent this.

```python
import teslapy
from selenium import webdriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

def custom_auth(url):
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    with webdriver.Chrome(chrome_options=options) as browser:
        browser.get(url)
        WebDriverWait(browser, 300).until(EC.url_contains('void/callback'))
        return browser.current_url

with teslapy.Tesla('elon@tesla.com', authenticator=custom_auth) as tesla:
    tesla.fetch_token()
```

#### Alternative

TeslaPy 2.2.0 introduced the `authorization_url()` method to get the SSO page URL and the option to supply the redirected URL as keyword argument `authorization_response` to `fetch_token()` after authentication.

```python
import teslapy
tesla = teslapy.Tesla('elon@tesla.com')
if not tesla.authorized:
    print('Use browser to login. Page Not Found will be shown at success.')
    print('Open this URL: ' + tesla.authorization_url())
    tesla.fetch_token(authorization_response=input('Enter URL after authentication: '))
vehicles = tesla.vehicle_list()
print(vehicles[0])
tesla.close()
```

#### Alternative staged

Support for staged authorization has been added to TeslaPy 2.5.0. The keyword arguments `state` and `code_verifier` are accepted by the `Tesla` class constructor, the `authorization_url()` method and the `fetch_token()` method.

```python
import teslapy
# First stage
tesla = teslapy.Tesla('elon@tesla.com')
if not tesla.authorized:
    state = tesla.new_state()
    code_verifier = tesla.new_code_verifier()
    print('Use browser to login. Page Not Found will be shown at success.')
    print('Open: ' + tesla.authorization_url(state=state, code_verifier=code_verifier))
tesla.close()
# Second stage
tesla = teslapy.Tesla('elon@tesla.com', state=state, code_verifier=code_verifier)
if not tesla.authorized:
    tesla.fetch_token(authorization_response=input('Enter URL after authentication: '))
vehicles = tesla.vehicle_list()
print(vehicles[0])
tesla.close()
```

#### 3rd party authentication apps

TeslaPy 2.4.0+ supports usage of a refresh token obtained by 3rd party [authentication apps](https://teslascope.com/help/generating-tokens). The refresh token is used to obtain an access token and both are cached for persistence, so you only need to supply the refresh token only once.

```python
import teslapy
with teslapy.Tesla('elon@tesla.com') as tesla:
    if not tesla.authorized:
        tesla.refresh_token(refresh_token=input('Enter SSO refresh token: '))
    vehicles = tesla.vehicle_list()
    print(vehicles[0])
```

#### Logout

To use your systems's default web browser to sign out of the SSO page and clear the token from cache:

```python
tesla.logout(sign_out=True)
```

If using pywebview, you can clear the token from cache and get the logout URL to display a sign out window:

```python
window = webview.create_window('Logout', tesla.logout())
window.start()
```

Selenium does not store cookies, just clear the token from cache:

```python
tesla.logout()
```

### Cache

The `Tesla` class implements a pluggable cache method. If you don't want to use the default disk caching, you can pass a function to load and return the cache dict, and a function that takes a dict as an argument to dump the cache dict, as arguments to the constructor. The `cache_loader` and `cache_dumper` arguments are accessible as attributes as well.

```python
import json
import sqlite3
import teslapy

def db_load():
    con = sqlite3.connect('cache.db')
    cur = con.cursor()
    cache = {}
    try:
        for row in cur.execute('select * from teslapy'):
            cache[row[0]] = json.loads(row[1])
    except sqlite3.OperationalError:
        pass
    con.close()
    return cache

def db_dump(cache):
    con = sqlite3.connect('cache.db')
    con.execute('create table if not exists teslapy (email text primary key, data json)')
    for email, data in cache.items():
        con.execute('replace into teslapy values (?, ?)', [email, json.dumps(data)])
    con.commit()
    con.close()

with teslapy.Tesla('elon@tesla.com', cache_loader=db_load, cache_dumper=db_dump) as tesla:
    tesla.fetch_token()
```

### Absolute URL

The Safety Scores are obtained though another API. TeslaPy 2.1.0 introduced absolute URL support for accessing non-Owner API endpoints.

```python
from teslapy import Tesla

with Tesla('elon@tesla.com') as tesla:
    vehicles = tesla.vehicle_list()
    url = 'https://akamai-apigateway-vfx.tesla.com/safety-rating/daily-metrics'
    print(tesla.get(url, params={'vin': vehicles[0]['vin'], 'deviceLanguage': 'en',
                                 'deviceCountry': 'US', 'timezone': 'UTC'}))
```

### Robustness

TeslaPy uses an adjustable connect and read timeout of 10 seconds by default. Refer to the [timeouts](https://requests.readthedocs.io/en/master/user/advanced/#timeouts) section for more details. TeslaPy does not retry failed or timed out connections by default, which can be enabled with the `retry` parameter.

```python
tesla = teslapy.Tesla('elon@tesla.com', retry=2, timeout=15)
```

A robust program accounting for network failures has a retry strategy, that includes the total number of retry attempts to make, the HTTP response codes to retry on and optionally a backoff factor. Refer to the [retry](https://urllib3.readthedocs.io/en/latest/reference/urllib3.util.html#module-urllib3.util.retry) module for more details.

Be aware that Tesla may temporarily block your account if you are hammering the servers too much.

```python
import teslapy
retry = teslapy.Retry(total=2, status_forcelist=(500, 502, 503, 504))
with teslapy.Tesla('elon@tesla.com', retry=retry) as tesla:
    vehicles = tesla.vehicle_list()
    print(vehicles[0])
vehicles[0].command('FLASH_LIGHTS')  # Raises exception
```

The line after the context manager will raise an exception when using TeslaPy 2.5.0+ because it explicitly closes the [requests](https://pypi.org/project/requests/) connection handler when the context manager exits. Earlier versions would not raise an exception and retries would not work.

Take a look at [cli.py](https://github.com/tdorssers/TeslaPy/blob/master/cli.py), [menu.py](https://github.com/tdorssers/TeslaPy/blob/master/menu.py) or [gui.py](https://github.com/tdorssers/TeslaPy/blob/master/gui.py) for more code examples.

## Commands

These are the major commands:

| Endpoint | Parameters | Value |
| --- | --- | --- |
| UNLOCK | | |
| LOCK | | |
| HONK_HORN | | |
| FLASH_LIGHTS | | |
| CLIMATE_ON | | |
| CLIMATE_OFF | | |
| MAX_DEFROST | `on` | `true` or `false` |
| CHANGE_CLIMATE_TEMPERATURE_SETTING | `driver_temp`, `passenger_temp` | temperature in celcius |
| SET_CLIMATE_KEEPER_MODE | `climate_keeper_mode` | 0=off, 1=on, 2=dog, 3=camp |
| HVAC_BIOWEAPON_MODE | `on` | `true` or `false` |
| SCHEDULED_DEPARTURE <sup>1</sup> | `enable`, `departure_time`, `preconditioning_enabled`, `preconditioning_weekdays_only`, `off_peak_charging_enabled`, `off_peak_charging_weekdays_only`, `end_off_peak_time` | `true` or `false`, minutes past midnight |
| SCHEDULED_CHARGING <sup>1</sup> | `enable`, `time` | `true` or `false`, minutes past midnight |
| CHARGING_AMPS <sup>1</sup> | `charging_amps` | between 0-32 |
| SET_CABIN_OVERHEAT_PROTECTION | `on`, `fan_only` | `true` or `false` |
| CHANGE_CHARGE_LIMIT | `percent` | percentage |
| SET_VEHICLE_NAME | `vehicle_name` | name |
| CHANGE_SUNROOF_STATE | `state` | `vent` or `close` |
| WINDOW_CONTROL <sup>2</sup> | `command`, `lat`, `lon` | `vent` or `close`, `0`, `0` |
| ACTUATE_TRUNK | `which_trunk` | `rear` or `front` |
| REMOTE_START | | |
| TRIGGER_HOMELINK | `lat`, `lon` | current lattitude and logitude |
| CHARGE_PORT_DOOR_OPEN | | |
| CHARGE_PORT_DOOR_CLOSE | | |
| START_CHARGE | | |
| STOP_CHARGE | | |
| SET_COP_TEMP | `temp` | temperature in celcius |
| MEDIA_TOGGLE_PLAYBACK | | |
| MEDIA_NEXT_TRACK | | |
| MEDIA_PREVIOUS_TRACK | | |
| MEDIA_NEXT_FAVORITE | | |
| MEDIA_PREVIOUS_FAVORITE | | |
| MEDIA_VOLUME_UP | | |
| MEDIA_VOLUME_DOWN | | |
| SET_VALET_MODE | `on`, `password` | `true` or `false`, 4 digit PIN |
| RESET_VALET_PIN | | |
| SPEED_LIMIT_ACTIVATE | `pin` | 4 digit PIN |
| SPEED_LIMIT_DEACTIVATE | `pin` | 4 digit PIN |
| SPEED_LIMIT_SET_LIMIT | `limit_mph` | between 50-90 |
| SPEED_LIMIT_CLEAR_PIN | `pin` | 4 digit PIN |
| SCHEDULE_SOFTWARE_UPDATE | `offset_sec` | seconds |
| CANCEL_SOFTWARE_UPDATE | | |
| SET_SENTRY_MODE | `on` | `true` or `false` |
| REMOTE_SEAT_HEATER_REQUEST | `heater`, `level` | seat 0-5, level 0-3 |
| REMOTE_AUTO_SEAT_CLIMATE_REQUEST | `auto_seat_position`, `auto_climate_on` | 1-2, `true` or `false` |
| REMOTE_SEAT_COOLING_REQUEST | `seat_position`, `seat_cooler_level` | |
| REMOTE_STEERING_WHEEL_HEATER_REQUEST | `on` | `true` or `false` |

<sup>1</sup> requires car version 2021.36 or higher. Setting `charging_amps` to 2 or 3 results in 3A and setting to 0 or 1 results in 2A.

<sup>2</sup> `close` requires `lat` and `lon` values to be near the current location of the car.

## Exceptions

Basic exception handling:

```python
try:
    vehicles[0].command('HONK_HORN')
except teslapy.HTTPError as e:
    print(e)
```

All `requests.exceptions` and `oauthlib.oauth2.rfc6749.errors` classes are imported by the module. When the vehicle is asleep or offline and the vehicle needs to be online for the API endpoint to be executed, the following exception is raised: `requests.exceptions.HTTPError: 408 Client Error: vehicle unavailable`. The exception can be caught as `teslapy.HTTPError`.

Additionally, `sync_wake_up()` raises `teslapy.VehicleError` when the vehicle does not come online within the specified timeout. And `command()` also raises `teslapy.VehicleError` when the vehicle command response result is `False`. For instance, if one of the media endpoints is called and there is no user present in the vehicle, the following exception is raised: `VehicleError: user_not_present`.

As of January 29, 2021, Tesla updated this endpoint to follow [RFC 7523](https://tools.ietf.org/html/rfc7523) and requires the use of the SSO service (auth.tesla.com) for authentication. If you get a `requests.exceptions.HTTPError: 400 Client Error: endpoint_deprecated:_please_update_your_app for url: https://owner-api.teslamotors.com/oauth/token` then you are probably using an old version of this module.

As of September 3, 2021, Tesla has added ReCaptcha to the login form. This caused the headless login implemented by TeslaPy to break. If you get a `ValueError: Credentials rejected. Recaptcha is required` and you are using correct credentials then you are probably using an old version of this module.

As of January 12, 2022, Tesla has deprecated the use of [RFC 7523](https://tools.ietf.org/html/rfc7523) tokens and requires the SSO tokens to be used for API access. If you get a `requests.exceptions.HTTPError: 401 Client Error: Unauthorized for url: https://owner-api.teslamotors.com/api/1/vehicles` and you are using correct credentials then you are probably using an old version of this module.

As of January 7, 2024, Tesla has removed the VEHICLE_LIST endpoint. If you get a `requests.exceptions.HTTPError: 412 Client Error: Endpoint is only available on fleetapi. Visit https://developer.tesla.com/docs for more info` then you are probably using an old version of this module.

## Demo applications

The source repository contains three demo applications that *optionally* use [pywebview](https://pypi.org/project/pywebview/) version 3.0 or higher or [selenium](https://pypi.org/project/selenium/) version 3.13.0 or higher to automate weblogin. Selenium 4.0.0 or higher is required for Edge Chromium.

[cli.py](https://github.com/tdorssers/TeslaPy/blob/master/cli.py) is a simple CLI application that can use almost all functionality of the TeslaPy module. The filter option allows you to select a product if more than one product is linked to your account. API output is JSON formatted:

```
usage: cli.py [-h] -e EMAIL [-f FILTER] [-a API [KEYVALUE ...]] [-k KEYVALUE]
              [-c COMMAND] [-t TIMEOUT] [-p PROXY] [-R REFRESH] [-U URL] [-l]
              [-o] [-v] [-w] [-g] [-b] [-n] [-m] [-s] [-d] [-r] [-S] [-H] [-V]
              [-L] [-u] [--chrome] [--edge]

Tesla Owner API CLI

optional arguments:
  -h, --help            show this help message and exit
  -e EMAIL              login email
  -f FILTER             filter on id, vin, etc.
  -a API [KEYVALUE ...]
                        API call endpoint name
  -k KEYVALUE           API parameter (key=value)
  -c COMMAND            product command endpoint
  -t TIMEOUT            connect/read timeout
  -p PROXY              proxy server URL
  -R REFRESH            use this refresh token
  -U URL                SSO service base URL
  -l, --list            list all selected vehicles/batteries
  -o, --option          list vehicle option codes
  -v, --vin             vehicle identification number decode
  -w, --wake            wake up selected vehicle(s)
  -g, --get             get rollup of all vehicle data
  -b, --battery         get detailed battery state and config
  -n, --nearby          list nearby charging sites
  -m, --mobile          get mobile enabled state
  -s, --site            get current site generation data
  -d, --debug           set logging level to debug
  -r, --stream          receive streaming vehicle data on-change
  -S, --service         get service self scheduling eligibility
  -H, --history         get charging history data
  -B, --basic           get basic vehicle data only
  -G, --location        get location (GPS) data, wake as needed
  -V, --verify          disable verify SSL certificate
  -L, --logout          clear token from cache and logout
  -u, --user            get user account details
  --chrome              use Chrome WebDriver
  --edge                use Edge WebDriver
```

Example usage of [cli.py](https://github.com/tdorssers/TeslaPy/blob/master/cli.py):

`python cli.py -e elon@tesla.com -w -a ACTUATE_TRUNK -k which_trunk=front`

[menu.py](https://github.com/tdorssers/TeslaPy/blob/master/menu.py) is a menu-based console application that displays vehicle data in a tabular format. The application depends on [geopy](https://pypi.org/project/geopy/) to convert GPS coordinates to a human readable address:

![](https://raw.githubusercontent.com/tdorssers/TeslaPy/master/media/menu.png)

[gui.py](https://github.com/tdorssers/TeslaPy/blob/master/gui.py) is a graphical user interface using `tkinter`. API calls are performed asynchronously using threading. The GUI supports auto refreshing of the vehicle data and displays a composed vehicle image. Note that the vehicle will not go to sleep, if auto refresh is enabled. The application depends on [geopy](https://pypi.org/project/geopy/) to convert GPS coordinates to a human readable address. If Tcl/Tk GUI toolkit version of your Python installation is lower than 8.6 then [pillow](https://pypi.org/project/Pillow/) is required to display the vehicle image. User preferences, such as which web browser to use for authentication, persist upon application restart.

![](https://raw.githubusercontent.com/tdorssers/TeslaPy/master/media/gui.png)

The vehicle charging history can be displayed in a graph as well.

![](https://raw.githubusercontent.com/tdorssers/TeslaPy/master/media/charge_history.png)

The demo applications can be containerized using the provided Dockerfile. A bind volume is used to store *cache.json* and *gui.ini* in the current directory on the host machine:

```
sudo docker build -t teslapy .
xhost +local:*
sudo docker run -ti --net=host --privileged -v "$(pwd)":/home/tsla teslapy
```

## Vehicle data

Example output of `get_vehicle_data()` or `python cli.py -e elon@tesla.com -w -g` below:

```json
{
    "id": 12345678901234567,
    "vehicle_id": 1234567890,
    "vin": "5YJ3E111111111111",
    "display_name": "Tim's Tesla",
    "option_codes": null,
    "color": null,
    "tokens": [
        "1234567890abcdef",
        "abcdef1234567890"
    ],
    "state": "online",
    "in_service": false,
    "id_s": "12345678901234567",
    "calendar_enabled": true,
    "api_version": 6,
    "backseat_token": null,
    "backseat_token_updated_at": null,
    "user_id": 123456,
    "charge_state": {
        "battery_heater_on": false,
        "battery_level": 44,
        "battery_range": 99.84,
        "charge_current_request": 16,
        "charge_current_request_max": 16,
        "charge_enable_request": true,
        "charge_energy_added": 14.54,
        "charge_limit_soc": 90,
        "charge_limit_soc_max": 100,
        "charge_limit_soc_min": 50,
        "charge_limit_soc_std": 90,
        "charge_miles_added_ideal": 66.5,
        "charge_miles_added_rated": 66.5,
        "charge_port_cold_weather_mode": false,
        "charge_port_door_open": true,
        "charge_port_latch": "Engaged",
        "charge_rate": 455.7,
        "charge_to_max_range": false,
        "charger_actual_current": 0,
        "charger_phases": null,
        "charger_pilot_current": 16,
        "charger_power": 100,
        "charger_voltage": 2,
        "charging_state": "Charging",
        "conn_charge_cable": "IEC",
        "est_battery_range": 78.13,
        "fast_charger_brand": "Tesla",
        "fast_charger_present": true,
        "fast_charger_type": "Combo",
        "ideal_battery_range": 99.84,
        "managed_charging_active": false,
        "managed_charging_start_time": null,
        "managed_charging_user_canceled": false,
        "max_range_charge_counter": 1,
        "minutes_to_full_charge": 15,
        "not_enough_power_to_heat": null,
        "scheduled_charging_pending": false,
        "scheduled_charging_start_time": null,
        "time_to_full_charge": 0.25,
        "timestamp": 1569952097456,
        "trip_charging": true,
        "usable_battery_level": 44,
        "user_charge_enable_request": null
    },
    "climate_state": {
        "battery_heater": false,
        "battery_heater_no_power": null,
        "climate_keeper_mode": "off",
        "driver_temp_setting": 21.0,
        "fan_status": 3,
        "inside_temp": 21.0,
        "is_auto_conditioning_on": true,
        "is_climate_on": true,
        "is_front_defroster_on": false,
        "is_preconditioning": false,
        "is_rear_defroster_on": false,
        "left_temp_direction": 54,
        "max_avail_temp": 28.0,
        "min_avail_temp": 15.0,
        "outside_temp": 13.5,
        "passenger_temp_setting": 21.0,
        "remote_heater_control_enabled": true,
        "right_temp_direction": 54,
        "seat_heater_left": 0,
        "seat_heater_right": 0,
        "side_mirror_heaters": false,
        "smart_preconditioning": false,
        "timestamp": 1569952097456,
        "wiper_blade_heater": false
    },
    "drive_state": {
        "gps_as_of": 1569952096,
        "heading": 240,
        "latitude": 52.531951,
        "longitude": 6.156999,
        "native_latitude": 52.531951,
        "native_location_supported": 1,
        "native_longitude": 6.156999,
        "native_type": "wgs",
        "power": -100,
        "shift_state": null,
        "speed": null,
        "timestamp": 1569952097456
    },
    "gui_settings": {
        "gui_24_hour_time": true,
        "gui_charge_rate_units": "km/hr",
        "gui_distance_units": "km/hr",
        "gui_range_display": "Rated",
        "gui_temperature_units": "C",
        "show_range_units": false,
        "timestamp": 1569952097456
    },
    "vehicle_config": {
        "can_accept_navigation_requests": true,
        "can_actuate_trunks": true,
        "car_special_type": "base",
        "car_type": "model3",
        "charge_port_type": "CCS",
        "eu_vehicle": true,
        "exterior_color": "SolidBlack",
        "has_air_suspension": false,
        "has_ludicrous_mode": false,
        "key_version": 2,
        "motorized_charge_port": true,
        "plg": false,
        "rear_seat_heaters": 0,
        "rear_seat_type": null,
        "rhd": false,
        "roof_color": "Glass",
        "seat_type": null,
        "spoiler_type": "None",
        "sun_roof_installed": null,
        "third_row_seats": "<invalid>",
        "timestamp": 1569952097456,
        "use_range_badging": true,
        "wheel_type": "Pinwheel18"
    },
    "vehicle_state": {
        "api_version": 6,
        "autopark_state_v2": "unavailable",
        "calendar_supported": true,
        "car_version": "2019.32.11.1 d39e85a",
        "center_display_state": 2,
        "df": 0,
        "dr": 0,
        "fd_window": 0,
        "fp_window": 0,
        "ft": 0,
        "is_user_present": true,
        "locked": false,
        "media_state": {
            "remote_control_enabled": true
        },
        "notifications_supported": true,
        "odometer": 6963.081561,
        "parsed_calendar_supported": true,
        "pf": 0,
        "pr": 0,
        "rd_window": 0,
        "remote_start": false,
        "remote_start_enabled": true,
        "remote_start_supported": true,
        "rp_window": 0,
        "rt": 0,
        "sentry_mode": false,
        "sentry_mode_available": true,
        "software_update": {
            "expected_duration_sec": 2700,
            "status": ""
        },
        "speed_limit_mode": {
            "active": false,
            "current_limit_mph": 85.0,
            "max_limit_mph": 90,
            "min_limit_mph": 50,
            "pin_code_set": false
        },
        "sun_roof_percent_open": null,
        "sun_roof_state": "unknown",
        "timestamp": 1569952097456,
        "valet_mode": false,
        "valet_pin_needed": true,
        "vehicle_name": "Tim's Tesla"
    }
}
```

Example output of `get_service_scheduling_data()` or `python cli.py -e elon@tesla.com --service` below:

```json
{
    "vin": "5YJ3E111111111111",
    "next_appt_timestamp": "2021-06-08T13:15:00",
    "next_appt_end_timestamp": null,
    "show_badge": false
}
```

## Powerwall data

Example output of `get_battery_data()` or `python cli.py -e elon@tesla.com -b` below:

```json
{
    "energy_site_id": 111110110110,
    "resource_type": "battery",
    "site_name": "Elon's House",
    "id": "STE10110111-00101",
    "gateway_id": "1111100-11-A--AAA11110A1A111",
    "asset_site_id": "a1100111-1a11-1aaa-a111-1a0011aa1111",
    "energy_left": 0,
    "total_pack_energy": 13746,
    "percentage_charged": 0,
    "battery_type": "ac_powerwall",
    "backup_capable": true,
    "battery_power": 0,
    "sync_grid_alert_enabled": false,
    "breaker_alert_enabled": false,
    "components": {
        "solar": true,
        "solar_type": "pv_panel",
        "battery": true,
        "grid": true,
        "backup": true,
        "gateway": "teg",
        "load_meter": true,
        "tou_capable": true,
        "storm_mode_capable": true,
        "flex_energy_request_capable": false,
        "car_charging_data_supported": false,
        "off_grid_vehicle_charging_reserve_supported": false,
        "vehicle_charging_performance_view_enabled": false,
        "vehicle_charging_solar_offset_view_enabled": false,
        "battery_solar_offset_view_enabled": true,
        "show_grid_import_battery_source_cards": true,
        "battery_type": "ac_powerwall",
        "configurable": false,
        "grid_services_enabled": false
    },
    "grid_status": "Active",
    "backup": {
        "backup_reserve_percent": 0,
        "events": null
    },
    "user_settings": {
        "storm_mode_enabled": false,
        "sync_grid_alert_enabled": false,
        "breaker_alert_enabled": false
    },
    "default_real_mode": "self_consumption",
    "operation": "self_consumption",
    "installation_date": "2020-01-01T10:10:00+08:00",
    "power_reading": [
        {
            "timestamp": "2021-02-24T04:25:39+08:00",
            "load_power": 5275,
            "solar_power": 3,
            "grid_power": 5262,
            "battery_power": 10,
            "generator_power": 0
        }
    ],
    "battery_count": 1
}
```

## Energy site data

Example output of `get_site_data()` or `python cli.py -e elon@tesla.com -s` below:

```json
{
    "energy_site_id": 111110110110,
    "resource_type": "solar",
    "id": "111aaa00-111a-11a1-00aa-00a1aa1aa0aa",
    "asset_site_id": "a1100111-1a11-1aaa-a111-1a0011aa1111",
    "solar_power": 11892.01953125,
    "solar_type": "pv_panel",
    "storm_mode_enabled": null,
    "powerwall_onboarding_settings_set": null,
    "sync_grid_alert_enabled": false,
    "breaker_alert_enabled": false,
    "components": {
        "battery": false,
        "solar": true,
        "solar_type": "pv_panel",
        "grid": true,
        "load_meter": true,
        "market_type": "residential"
    },
    "energy_left": 0,
    "total_pack_energy": 1,
    "percentage_charged": 0,
    "battery_power": 0,
    "load_power": 0,
    "grid_status": "Unknown",
    "grid_services_active": false,
    "grid_power": -11892.01953125,
    "grid_services_power": 0,
    "generator_power": 0,
    "island_status": "island_status_unknown",
    "storm_mode_active": false,
    "timestamp": "2022-08-15T17:12:26Z",
    "wall_connectors": null
}
```

## Installation

TeslaPy is available on PyPI:

`python -m pip install teslapy 'urllib3<2'`

Make sure you have [Python](https://www.python.org/) 2.7+ or 3.5+ installed on your system. Alternatively, clone the repository to your machine and run demo application [cli.py](https://github.com/tdorssers/TeslaPy/blob/master/cli.py), [menu.py](https://github.com/tdorssers/TeslaPy/blob/master/menu.py) or [gui.py](https://github.com/tdorssers/TeslaPy/blob/master/gui.py) to get started, after installing [requests_oauthlib](https://pypi.org/project/requests-oauthlib/) 0.8.0+, [geopy](https://pypi.org/project/geopy/) 1.14.0+, [pywebview](https://pypi.org/project/pywebview/) 3.0+ (optional), [selenium](https://pypi.org/project/selenium/) 3.13.0+ (optional) and [websocket-client](https://pypi.org/project/websocket-client/) 0.59+ using [PIP](https://pypi.org/project/pip/) as follows:

`python -m pip install requests_oauthlib geopy pywebview selenium websocket-client`

and install [ChromeDriver](https://sites.google.com/chromium.org/driver/) to use Selenium or on Ubuntu as follows:

`sudo apt-get install python3-requests-oauthlib python3-geopy python3-webview python3-selenium python3-websocket`
