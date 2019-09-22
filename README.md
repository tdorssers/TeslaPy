# TeslaPy

A Python implementation based on [unofficial documentation](https://tesla-api.timdorr.com/) of the client side interface to the Tesla Motors REST API, which provides functionality to monitor and control the vehicle remotely.

## Overview

The single file module *teslapy.py* depends on Python [requests](https://pypi.org/project/requests/). The `Tesla` class extends `requests.Session` and inherits methods like `get` and `post` that can be used to perform API calls. The class implements a custom OAuth 2.0 Password Grant, since *email* instead of *username* is used by the API for authentication. The authentication bearer token is cached to disk (*cache.json*) for reuse, so a password is only needed when a new token is requested. The token is automatically renewed when needed. The constructor takes four arguments required for authentication and one optional argument to specify a proxy server. The convenience method `api` uses named endpoints listed in *endpoints.json* to perform calls, so the module does not require changes if the API is updated. Any error message returned by the API is raised as an `HTTPError` exception. Additionally, the class implements the following methods:

| Call | Description |
| --- | --- |
| fetch_token() | requests a new bearer token using password grant |
| refresh_token() | requests a new token using a refresh token |
| vehicle_list() | returns a list of Vehicle objects |

The `Vehicle` class extends `dict` and stores vehicle data returned by the API. Additionally, the class implements the following methods:

| Call | Description |
| --- | --- |
| api() | perform API call to named endpoint with optional arguments |
| get_vehicle_summary() | get the state of the vehicle |
| sync_wake_up() | wake up and wait for the vehicle to come online |
| option_code_list() | lists known descriptions of vehicle option codes |
| get_vehicle_data() | rollup of all the data request endpoints plus vehicle config |
| get_nearby_charging_sites() | lists nearby Tesla-operated charging stations |
| mobile_enabled() | check if mobile access is enabled in the car |
| compose_image() | compose a vehicle image based on option codes |
| dist_units () | convert distance or speed units to GUI setting of the car |
| temp_units () | convert temperature units to GUI setting of the car |
| decode_vin() | decode the vehicle identification number |
| remote_start_drive() | enable keyless drive (requires password to be set) |
| command() | vehicle command request with error handling |

Only `vehicle_list()`, `get_vehicle_summary()`, `option_code_list()`, `compose_image()` and `decode_vin()` are available when the vehicle is asleep or offline. Other methods and API calls require the vehicle to be brought online by using `sync_wake_up()`.

## Usage

Basic usage of the module:

```python
import teslapy
with teslapy.Tesla(EMAIL, PASSWORD, CLIENT_ID, CLIENT_SECRET) as tesla:
	tesla.fetch_token()
	vehicles = tesla.vehicle_list()
	vehicles[0].sync_wake_up()
	vehicles[0].command('ACTUATE_TRUNK', which_trunk='front')
```

These are the major endpoints:

| Endpoint | Parameters |
| --- | --- |
| UNLOCK | |
| LOCK | |
| HONK_HORN | |
| FLASH_LIGHTS | |
| CLIMATE_ON | |
| CLIMATE_OFF | |
| CHANGE_CLIMATE_TEMPERATURE_SETTING | driver_temp, passenger_temp |
| CHANGE_CHARGE_LIMIT | percent |
| CHANGE_SUNROOF_STATE | state |
| ACTUATE_TRUNK | which_trunk |
| CHARGE_PORT_DOOR_OPEN | |
| CHARGE_PORT_DOOR_CLOSE | |
| START_CHARGE | |
| STOP_CHARGE | |
| MEDIA_TOGGLE_PLAYBACK | |
| MEDIA_NEXT_TRACK | |
| MEDIA_PREVIOUS_TRACK | |
| MEDIA_NEXT_FAVORITE | |
| MEDIA_PREVIOUS_FAVORITE | |
| MEDIA_VOLUME_UP | |
| MEDIA_VOLUME_DOWN | |
| SET_VALET_MODE | on, password|
| RESET_VALET_PIN | |
| SPEED_LIMIT_ACTIVATE | pin |
| SPEED_LIMIT_DEACTIVATE | pin |
| SPEED_LIMIT_SET_LIMIT | limit_mph |
| SPEED_LIMIT_CLEAR_PIN | pin |
| SCHEDULE_SOFTWARE_UPDATE | offset_sec |
| CANCEL_SOFTWARE_UPDATE | |
| SET_SENTRY_MODE | on |
| REMOTE_SEAT_HEATER_REQUEST | heater, level |
| REMOTE_STEERING_WHEEL_HEATER_REQUEST | on |

Basic exception handling:

```python
    try:
        vehicles[0].command('HONK_HORN')
    except teslapy.HTTPError as e:
        print(e)
```

All `requests.exceptions` classes are imported by the module. When the vehicle is asleep or offline and the vehicle needs to be online for the API endpoint to be executed, the following exception is raised: `requests.exceptions.HTTPError: 408 Client Error: vehicle unavailable`. The exception can be caught as `teslapy.HTTPError`. Additionally, `sync_wake_up()` raises `teslapy.VehicleError` when the vehicle does not come online within the specified timeout. And `command()` also raises `teslapy.VehicleError` when the API response result is false. If one of the media endpoints is called and there is no user in the vehicle, the following exception is raised: `VehicleError: user_not_present`.

## Applications

*cli.py* is a simple CLI application that can use almost all functionality of the TeslaPy module. The filter option allows you to select a vehicle if more than one vehicle is linked to your account. API output is JSON formatted:

```
usage: cli.py [-h] -e EMAIL [-p [PASSWORD]] [-f FILTER] [-a API] [-k KEYVALUE]
              [-l] [-o] [-v] [-w] [-g] [-n] [-m] [-s] [-d]

Tesla API CLI

optional arguments:
  -h, --help     show this help message and exit
  -e EMAIL       login email
  -p [PASSWORD]  prompt/specify login password
  -f FILTER      filter on id, vin, etc.
  -a API         API call endpoint name
  -k KEYVALUE    API parameter (key=value)
  -l, --list     list all selected vehicles
  -o, --option   list vehicle option codes
  -v, --vin      vehicle identification number decode
  -w, --wake     wake up selected vehicle(s)
  -g, --get      get rollup of all vehicle data
  -n, --nearby   list nearby charging sites
  -m, --mobile   get mobile enabled state
  -s, --start    remote start drive
  -d, --debug    set logging level to debug
```

Example usage of *cli.py* using a cached token:

`python cli.py -e EMAIL -w -a ACTUATE_TRUNK -k which_trunk=front`

*menu.py* is a menu-based console application that displays vehicle data in a tabular format. The application depends on [geopy](https://pypi.org/project/geopy/) to convert GPS coordinates to a human readable address:

![](media/menu.png)

*gui.py* is a graphical interface using `tkinter`. API calls are performed asynchronously using threading. The GUI also supports auto refreshing of the vehicle data and the GUI displays a composed vehicle image. Note that the vehicle will not go to sleep, if auto refresh is enabled. The application depends on [pillow](https://pypi.org/project/Pillow/) to display the vehicle image, if the Tcl/Tk GUI toolkit version of your Python installation is 8.5. Python 3.4+ should include Tcl/Tk 8.6, which natively supports PNG image format and therefore has no such dependency.

![](media/gui.png)

## Installation

Make sure you have [Python](https://www.python.org/) 2.7+ or 3.4+ installed on your system. Install [requests](https://pypi.org/project/requests/) and [geopy](https://pypi.org/project/geopy/) using [PIP](https://pypi.org/project/pip/) on Linux or macOS:

`pip install requests geopy`

or on Windows as follows:

`python -m pip install requests geopy`

or on Ubuntu as follows:

`sudo apt-get install python-requests python-geopy`

Put *teslapy.py*, *endpoints.json*, *option_codes.json*, *cli.py*, *menu.py* and *gui.py* in a directory and run *cli.py*, *menu.py* or *gui.py*.
