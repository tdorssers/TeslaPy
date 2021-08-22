# TeslaPy

A Python implementation based on [unofficial documentation](https://tesla-api.timdorr.com/) of the client side interface to the Tesla Motors Owner API, which provides functionality to monitor and control Tesla products remotely.

## Overview

This module depends on Python [requests](https://pypi.org/project/requests/), [requests_oauthlib](https://pypi.org/project/requests-oauthlib/) and [websocket-client](https://pypi.org/project/websocket-client/). The `Tesla` class extends `requests.Session` and therefore inherits methods like `get()` and `post()` that can be used to perform API calls. All calls to the Owner API are intercepted by the `request()` method to add the JSON Web Token (JWT) bearer, which is acquired after authentication. Module characteristics:

* It implements Tesla's new [OAuth 2](https://oauth.net/2/) Single Sign-On service.
* And supports Multi-Factor Authentication (MFA) Time-based One-Time Passwords (TOTP).
* Acquired tokens are cached to disk (*cache.json*) for persistence.
* The cache stores tokens of each authorized identity (email).
* Authentication is only needed when a new token is requested.
* The token is automatically refreshed when expired without the need to reauthenticate.
* An email registered in another region (e.g. auth.tesla.cn) is also supported.
* Captcha verification support if required by the login form.
* Streaming API support using a [WebSocket](https://datatracker.ietf.org/doc/html/rfc6455).

The constructor takes these arguments:

| Argument | Description |
| --- | --- |
| `email` | SSO identity |
| `password` | SSO credential. May be an empty string when using a cached identity |
| `passcode_getter` | (optional) function that returns the TOTP passcode |
| `factor_selector` | (optional) function with one argument, a list of factor dicts, that returns the selected dict or factor name |
| `captcha_solver` | (optional) function with one argument, SVG image content, that returns the captcha characters |
| `verify` | (optional) verify SSL certificate |
| `proxy` | (optional) URL of proxy server |
| `retry` | (optional) number of connection retries or `Retry` instance |
| `user_agent` | (optional) the User-Agent string |
| `cache_file` | (optional) path to cache file used by default loader and dumper |
| `cache_loader` | (optional) function that returns the cache dict |
| `cache_dumper` | (optional) function with one argument, the cache dict |

The class will use `stdio` to get a passcode, factor and captcha by default. The captcha image is opened in the system's default web browser.

The convenience method `api()` uses named endpoints listed in *endpoints.json* to perform calls, so the module does not require changes if the API is updated. Any error message returned by the API is raised as an `HTTPError` exception. Additionally, the class implements the following methods:

| Call | Description |
| --- | --- |
| `fetch_token()` | requests a new JWT bearer token using Authorization Code grant with [PKCE](https://oauth.net/2/pkce/) extension |
| `refresh_token()` | requests a new JWT bearer token using [Refresh Token](https://oauth.net/2/grant-types/refresh-token/) grant |
| `vehicle_list()` | returns a list of Vehicle objects |
| `battery_list()` | returns a list of Battery objects |

The `Vehicle` class extends `dict` and stores vehicle data returned by the Owner API, which is a pull API. The streaming API pushes vehicle data on-change after subscription. The `stream()` method takes an optional argument, a callback function that is called with one argument, a dict holding the changed data. The `Vehicle` object is always updated with the pushed data. If there are no changes within 10 seconds, the vehicle stops streaming data. The `stream()` method has two more optional arguments to control restarting. Additionally, the class implements the following methods:

| Call | Description |
| --- | --- |
| `api()` | performs an API call to named endpoint requiring vehicle_id with optional arguments |
| `get_vehicle_summary()` | gets the state of the vehicle (online, asleep, offline) |
| `sync_wake_up()` | wakes up and waits for the vehicle to come online |
| `option_code_list()` <sup>1</sup> | lists known descriptions (read from *option_codes.json*) of the vehicle option codes |
| `get_vehicle_data()` | gets a rollup of all the data request endpoints plus vehicle config |
| `get_nearby_charging_sites()` | lists nearby Tesla-operated charging stations |
| `get_service_scheduling_data()` | retrieves next service appointment for this vehicle |
| `mobile_enabled()` | checks if mobile access is enabled in the vehicle |
| `compose_image()` <sup>2</sup> | composes a vehicle image based on vehicle option codes |
| `dist_units()` | converts distance or speed units to GUI setting of the vehicle |
| `temp_units()` | converts temperature units to GUI setting of the vehicle |
| `decode_vin()` | decodes the vehicle identification number to a dict |
| `remote_start_drive()` | enables keyless drive (requires password to be set) |
| `command()` | wrapper around `api()` for vehicle command response error handling |

<sup>1</sup> Option codes appear to be deprecated. Vehicles return a generic set of codes related to a Model 3.

<sup>2</sup> Pass vehicle option codes to this method or the image may not be accurate.

Only `get_vehicle_summary()`, `option_code_list()`, `get_service_scheduling_data()`, `compose_image()` and `decode_vin()` are available when the vehicle is asleep or offline. These methods will not prevent your vehicle from sleeping. Other methods and API calls require the vehicle to be brought online by using `sync_wake_up()` and can prevent your vehicle from sleeping if called within too short a period.

The `Product` class extends `dict` and stores product data of Powerwalls and solar panels returned by the API. Additionally, the class implements the following methods:

| Call | Description |
| --- | --- |
| `api()` | performs an API call to named endpoint requiring battery_id or site_id with optional arguments |
| `get_history_data()` | Retrieve live status of product |
| `get_calendar_history_data()` | Retrieve live status of product |
| `command()` | wrapper around `api()` for battery command response error handling |

The `Battery` class extends `Product` and stores Powerwall data returned by the API. Additionally, the class implements the following methods:

| Call | Description |
| --- | --- |
| `get_battery_data()` | Retrieve detailed state and configuration of the battery |
| `set_operation()` | Set battery operation to self_consumption, backup or autonomous |
| `set_backup_reserve_percent()` | Set the minimum backup reserve percent for that battery |

The `SolarPanel` class extends `Product` and stores solar panel data returned by the API. Additionally, the class implements the following methods:

| Call | Description |
| --- | --- |
| `get_site_data()` | Retrieve current site generation data |

## Usage

Basic usage of the module:

```python
import teslapy
with teslapy.Tesla('elon@tesla.com', 'starship') as tesla:
	tesla.fetch_token()
	vehicles = tesla.vehicle_list()
	vehicles[0].sync_wake_up()
	vehicles[0].command('ACTUATE_TRUNK', which_trunk='front')
	print(vehicles[0].get_vehicle_data()['vehicle_state']['car_version'])
```

The constructor takes a function that returns a passcode string as the third argument in case your Tesla account has MFA enabled and you don't want to use the default passcode getter method:

```python
with teslapy.Tesla('elon@tesla.com', 'starship', lambda: '123456') as tesla:
```

Tesla allows you to enable more than one MFA device. If you don't want to use the default factor selector method, you can pass a function that takes a list of dicts as an argument and returns the selected factor dict as the constructor's fourth argument. The function may return the selected factor name as well:

```python
with teslapy.Tesla('elon@tesla.com', 'starship', lambda: '123456', lambda _: 'Device #1') as tesla:
```

If you don't want to use the default captcha solver method, you can pass a function that takes the SVG image as an argument and returns the verification code as the constructor's fifth argument. The `passcode_getter`, `factor_selector` and `captcha_solver` optional arguments are also accessible as attributes:

```python
def solve_captcha(svg):
    with open('captcha.svg', 'wb') as f:
        f.write(svg)
    return input('Captcha: ')

with teslapy.Tesla('elon@tesla.com', 'starship') as tesla:
    tesla.captcha_solver = solve_captcha
    tesla.fetch_token()
```

The `Tesla` class implements a pluggable cache method. If you don't want to use the default disk caching, you can pass a function to load and return the cache dict, and a function that takes a dict as an argument to dump the cache dict, as arguments to the constructor. The `cache_loader` and `cache_dumper` arguments are accessible as attributes as well.

```python
import json
import sqlite3

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

with teslapy.Tesla('elon@tesla.com', 'starship', cache_loader=db_load, cache_dumper=db_dump) as tesla:
	tesla.fetch_token()
```

Take a look at [cli.py](https://github.com/tdorssers/TeslaPy/blob/master/cli.py), [menu.py](https://github.com/tdorssers/TeslaPy/blob/master/menu.py) or [gui.py](https://github.com/tdorssers/TeslaPy/blob/master/gui.py) for more code examples.

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
| CHANGE_CHARGE_LIMIT | `percent` | percentage |
| CHANGE_SUNROOF_STATE | `state` | `vent` or `close` |
| WINDOW_CONTROL <sup>1</sup> | `command`, `lat`, `lon` | `vent` or `close`, `0`, `0` |
| ACTUATE_TRUNK | `which_trunk` | `rear` or `front` |
| REMOTE_START | `password` | password |
| TRIGGER_HOMELINK | `lat`, `lon` | current lattitude and logitude |
| CHARGE_PORT_DOOR_OPEN | | |
| CHARGE_PORT_DOOR_CLOSE | | |
| START_CHARGE | | |
| STOP_CHARGE | | |
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
| REMOTE_STEERING_WHEEL_HEATER_REQUEST | `on` | `true` or `false` |

<sup>1</sup> `close` requires `lat` and `lon` values to be near the current location of the car.

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

When the `passcode_getter` or `factor_selector` function return an empty string and your account has MFA enabled, then the module will cancel the transaction and this exception will be raised: `CustomOAuth2Error: (login_cancelled) User cancelled login`.

If you get a `requests.exceptions.HTTPError: 400 Client Error: endpoint_deprecated:_please_update_your_app for url: https://owner-api.teslamotors.com/oauth/token` then you are probably using an old version of this module. As of January 29, 2021, Tesla updated this endpoint to follow [RFC 7523](https://tools.ietf.org/html/rfc7523) and requires the use of the SSO service (auth.tesla.com) for authentication.

As of May 28, 2021, Tesla has added captcha verification to the login form. The User-Agent string might influence the presence of the captcha. If you get a `ValueError: Credentials rejected` and you are using correct credentials then you are probably using an old version of this module.

## Demo applications

The source repository contains three demo applications.

[cli.py](https://github.com/tdorssers/TeslaPy/blob/master/cli.py) is a simple CLI application that can use almost all functionality of the TeslaPy module. The filter option allows you to select a product if more than one product is linked to your account. API output is JSON formatted:

```
usage: cli.py [-h] -e EMAIL [-p [PASSWORD]] [-t PASSCODE] [-u FACTOR]
              [-f FILTER] [-a API] [-k KEYVALUE] [-c COMMAND] [-l] [-o] [-v]
              [-w] [-g] [-b] [-n] [-m] [-s] [-d] [-r] [--service] [--verify]
              [--proxy PROXY]

Tesla Owner API CLI

optional arguments:
  -h, --help     show this help message and exit
  -e EMAIL       login email
  -p [PASSWORD]  prompt/specify login password
  -t PASSCODE    two factor passcode
  -u FACTOR      use two factor device name
  -f FILTER      filter on id, vin, etc.
  -a API         API call endpoint name
  -k KEYVALUE    API parameter (key=value)
  -c COMMAND     product command endpoint
  -l, --list     list all selected vehicles/batteries
  -o, --option   list vehicle option codes
  -v, --vin      vehicle identification number decode
  -w, --wake     wake up selected vehicle(s)
  -g, --get      get rollup of all vehicle data
  -b, --battery  get detailed battery state and config
  -n, --nearby   list nearby charging sites
  -m, --mobile   get mobile enabled state
  -s, --start    remote start drive
  -d, --debug    set logging level to debug
  -r, --stream   receive streaming vehicle data on-change
  --service      get service self scheduling eligibility
  --verify       disable verify SSL certificate
  --proxy PROXY  proxy server URL
```

Example usage of [cli.py](https://github.com/tdorssers/TeslaPy/blob/master/cli.py) using a cached token:

`python cli.py -e elon@tesla.com -w -a ACTUATE_TRUNK -k which_trunk=front`

[menu.py](https://github.com/tdorssers/TeslaPy/blob/master/menu.py) is a menu-based console application that displays vehicle data in a tabular format. The application depends on [geopy](https://pypi.org/project/geopy/) to convert GPS coordinates to a human readable address:

![](https://raw.githubusercontent.com/tdorssers/TeslaPy/master/media/menu.png)

[gui.py](https://github.com/tdorssers/TeslaPy/blob/master/gui.py) is a graphical interface using `tkinter`. API calls are performed asynchronously using threading. The GUI supports auto refreshing of the vehicle data and the GUI displays a composed vehicle image. Note that the vehicle will not go to sleep, if auto refresh is enabled. The application depends on [geopy](https://pypi.org/project/geopy/) to convert GPS coordinates to a human readable address, [pillow](https://pypi.org/project/Pillow/) to display the vehicle image and [svglib](https://pypi.org/project/svglib/) to display the captcha image if required by the login form.

![](https://raw.githubusercontent.com/tdorssers/TeslaPy/master/media/gui.png)

## Vehicle data

Example output of `get_vehicle_data()` or `python cli.py -e elon@tesla.com -w -g` below:

```json
{
    "id": 12345678901234567,
    "vehicle_id": 1234567890,
    "vin": "5YJ3E111111111111",
    "display_name": "Tim's Tesla",
    "option_codes": "AD15,MDL3,PBSB,RENA,BT37,ID3W,RF3G,S3PB,DRLH,DV2W,W39B,APF0,COUS,BC3B,CH07,PC30,FC3P,FG31,GLFR,HL31,HM31,IL31,LTPB,MR31,FM3B,RS3H,SA3P,STCP,SC04,SU3C,T3CA,TW00,TM00,UT3P,WR00,AU3P,APH3,AF00,ZCST,MI00,CDM0",
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
    "response": {
        "enabled_vins": [
            {
                "vin": "5YJ3E111111111111",
                "next_appt_timestamp": "2021-06-08T13:15:00",
                "next_appt_end_timestamp": null,
                "show_badge": false
            }
        ]
    }
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

## Installation

TeslaPy is available on PyPI:

`python -m pip install teslapy`

Make sure you have [Python](https://www.python.org/) 2.7+ or 3.5+ installed on your system. Alternatively, clone the repository to your machine and run demo application [cli.py](https://github.com/tdorssers/TeslaPy/blob/master/cli.py), [menu.py](https://github.com/tdorssers/TeslaPy/blob/master/menu.py) or [gui.py](https://github.com/tdorssers/TeslaPy/blob/master/gui.py) to get started, after installing [requests_oauthlib](https://pypi.org/project/requests-oauthlib/), [geopy](https://pypi.org/project/geopy/), [svglib](https://pypi.org/project/svglib/) and [websocket-client](https://pypi.org/project/websocket-client/) using [PIP](https://pypi.org/project/pip/) as follows:

`python -m pip install requests_oauthlib geopy svglib websocket-client`

or on Ubuntu as follows:

`sudo apt-get install python3-requests-oauthlib python3-geopy`
