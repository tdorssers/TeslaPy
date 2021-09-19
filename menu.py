""" Tesla API menu-based console application using TeslaPy module """

# Author: Tim Dorssers

from __future__ import print_function
import ssl
import logging
import argparse
import geopy.geocoders
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
try:
    from selenium import webdriver  # 3.13.0 or higher required
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except ImportError:
    webdriver = None  # Optional import
from teslapy import Tesla

raw_input = vars(__builtins__).get('raw_input', input)  # Py2/3 compatibility

def heading_to_str(deg):
    lst = ['NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW',
           'W', 'WNW', 'NW', 'NNW', 'N']
    return lst[int(abs((deg - 11.25) % 360) / 22.5)]

def show_vehicle_data(vehicle):
    cl = vehicle['climate_state']
    ve = vehicle['vehicle_state']
    dr = vehicle['drive_state']
    ch = vehicle['charge_state']
    co = vehicle['vehicle_config']
    # Lookup address at coordinates
    coords = '%s, %s' % (dr['latitude'], dr['longitude'])
    try:
        osm = Nominatim(user_agent='TeslaPy', proxies=vehicle.tesla.proxies)
        location = osm.reverse(coords).address
    except GeocoderTimedOut as e:
        logging.error(e)
        location = coords
    # Climate state
    fmt = 'Outside Temperature: {:17} Inside Temperature: {}'
    print(fmt.format(vehicle.temp_units(cl['outside_temp']),
                     vehicle.temp_units(cl['inside_temp'])))
    fmt = 'Driver Temperature Setting: {:10} Passenger Temperature Setting: {}'
    print(fmt.format(vehicle.temp_units(cl['driver_temp_setting']),
                     vehicle.temp_units(cl['passenger_temp_setting'])))
    fmt = 'Is Climate On: {:23} Fan Speed: {}'
    print(fmt.format(str(cl['is_climate_on']), cl['fan_status']))
    fmt = 'Driver Seat Heater: {:18} Passenger Seat Heater: {}'
    print(fmt.format(str(cl['seat_heater_left']), str(cl['seat_heater_right'])))
    fmt = 'Is Front Defroster On: {:15} Is Rear Defroster On: {}'
    print(fmt.format(str(cl['is_front_defroster_on']),
                     str(cl['is_rear_defroster_on'])))
    print('-'*80)
    # Vehicle state
    fmt = 'Vehicle Name: {:24} Odometer: {}'
    print(fmt.format(ve['vehicle_name'], vehicle.dist_units(ve['odometer'])))
    fmt = 'Car Version: {:25} Locked: {}'
    print(fmt.format(ve['car_version'], ve['locked']))
    door = ['Closed', 'Open']
    fmt = 'Driver/Pass Front Door: {:14} Driver/Pass Rear Door: {}/{}'
    print(fmt.format('%s/%s' % (door[bool(ve['df'])], door[bool(ve['pf'])]),
                     door[bool(ve['dr'])], door[bool(ve['pr'])]))
    window = {0: 'Closed', 1: 'Venting', 2: 'Open'}
    fmt = 'Drvr/Pass Front Window: {:14} Driver/Pass Rear Window: {}/{}'
    print(fmt.format('%s/%s' % (window.get(ve.get('fd_window')),
                                window.get(ve.get('fp_window'))),
                     window.get(ve.get('rd_window')),
                     window.get(ve.get('rp_window'))))
    fmt = 'Front Trunk: {:25} Rear Trunk: {}'
    print(fmt.format(door[ve['ft']], door[ve['rt']]))
    fmt = 'Remote Start: {:24} Is User Present: {}'
    print(fmt.format(str(ve['remote_start']), str(ve['is_user_present'])))
    fmt = 'Speed Limit Mode: {:20} Current Limit: {}'
    limit = vehicle.dist_units(ve['speed_limit_mode']['current_limit_mph'], True)
    print(fmt.format(str(ve['speed_limit_mode']['active']), limit))
    fmt = 'Speed Limit Pin Set: {:17} Sentry Mode: {}'
    print(fmt.format(str(ve['speed_limit_mode']['pin_code_set']),
                     str(ve.get('sentry_mode'))))
    fmt = 'Valet Mode: {:26} Valet Pin Set: {}'
    print(fmt.format(str(ve['valet_mode']), str(not 'valet_pin_needed' in ve)))
    print('-'*80)
    # Drive state
    speed = 0 if dr['speed'] is None else dr['speed']
    fmt = 'Power: {:31} Speed: {}'
    print(fmt.format(str(dr['power']) + ' kW', vehicle.dist_units(speed, True)))
    fmt = 'Shift State: {:25} Heading: {}'
    print(fmt.format(str(dr['shift_state']), heading_to_str(dr['heading'])))
    print(u'GPS: {:.75}'.format(location))
    print('-'*80)
    # Charging state
    fmt = 'Charging State: {:22} Time To Full Charge: {:02.0f}:{:02.0f}'
    print(fmt.format(ch['charging_state'],
                     *divmod(ch['time_to_full_charge'] * 60, 60)))
    phases = '3 x ' if ch['charger_phases'] == 2 else ''
    fmt = 'Charger Voltage: {:21} Charger Actual Current: {}{:d} A'
    print(fmt.format(str(ch['charger_voltage']) + ' V',
                     phases, ch['charger_actual_current']))
    fmt = 'Charger Power: {:23} Charge Rate: {}'
    print(fmt.format(str(ch['charger_power']) + ' kW',
                     vehicle.dist_units(ch['charge_rate'], True)))
    fmt = 'Battery Level: {:23} Battery Range: {}'
    print(fmt.format(str(ch['battery_level']) + ' %',
                     vehicle.dist_units(ch['battery_range'])))
    fmt = 'Charge Energy Added: {:17} Charge Range Added: {}'
    print(fmt.format(str(ch['charge_energy_added']) + ' kWh',
                     vehicle.dist_units(ch['charge_miles_added_rated'])))
    fmt = 'Charge Limit SOC: {:20} Estimated Battery Range: {}'
    print(fmt.format(str(ch['charge_limit_soc']) + ' %',
                     vehicle.dist_units(ch['est_battery_range'])))
    fmt = 'Charge Port Door Open: {:15} Charge Port Latch: {}'
    print(fmt.format(str(ch['charge_port_door_open']),
                     str(ch['charge_port_latch'])))
    print('-'*80)
    # Vehicle config
    fmt = 'Car Type: {:28} Exterior Color: {}'
    print(fmt.format(co['car_type'], co['exterior_color']))
    fmt = 'Wheel Type: {:26} Spoiler Type: {}'
    print(fmt.format(co['wheel_type'], co['spoiler_type']))
    fmt = 'Roof Color: {:26} Charge Port Type: {}'
    print(fmt.format(co['roof_color'], co['charge_port_type']))

def show_charging_sites(vehicle):
    sites = vehicle.get_nearby_charging_sites()
    print('Destination Charging:')
    fmt = '{:57} {}'
    for site in sites['destination_charging']:
        print(fmt.format(site['name'],
                         vehicle.dist_units(site['distance_miles'])))
    print('-'*80)
    print('Superchargers:')
    fmt = '{:57} {} {}/{} stalls'
    for site in sites['superchargers']:
        print(fmt.format(site['name'],
                         vehicle.dist_units(site['distance_miles']),
                         site['available_stalls'], site['total_stalls']))

def menu(vehicle):
    lst = ['Refresh', 'Wake up', 'Nearby charging sites', 'Honk horn',
           'Flash lights', 'Lock/unlock', 'Climate on/off', 'Set temperature',
           'Actuate frunk/trunk', 'Remote start drive',
           'Set charge limit', 'Open/close charge port', 'Start/stop charge',
           'Seat heater request', 'Toggle media playback', 'Window control',
           'Max defrost']
    opt = 0
    while True:
        # Display vehicle info, except after nearby charging sites
        if opt != 3:
            if vehicle['state'] == 'online':
                if not vehicle.mobile_enabled():
                    print('Mobile access is not enabled for this vehicle')
                    print('-'*80)
                show_vehicle_data(vehicle.get_vehicle_data())
            else:
                print('Wake up vehicle to use remote functions/telemetry')
        print('-'*80)
        # Display 3 column menu
        for i, option in enumerate(lst, 1):
            print('{:2} {:23}'.format(i, option), end='' if i % 3 else '\n')
        if i % 3:
            print()
        print('-'*80)
        # Get user choice
        opt = int(raw_input("Choice (0 to quit): "))
        print('-'*80)
        # Check if vehicle is still online, otherwise force refresh
        if opt > 2:
            vehicle.get_vehicle_summary()
            if vehicle['state'] != 'online':
                opt = 1
        # Perform menu option
        if opt == 0:
            break
        if opt == 1:
            pass
        elif opt == 2:
            print('Please wait...')
            vehicle.sync_wake_up()
            print('-'*80)
        elif opt == 3:
            show_charging_sites(vehicle)
        elif opt == 4:
            vehicle.command('HONK_HORN')
        elif opt == 5:
            vehicle.command('FLASH_LIGHTS')
        elif opt == 6:
            if vehicle['vehicle_state']['locked']:
                vehicle.command('UNLOCK')
            else:
                vehicle.command('LOCK')
        elif opt == 7:
            if vehicle['climate_state']['is_climate_on']:
                vehicle.command('CLIMATE_OFF')
            else:
                vehicle.command('CLIMATE_ON')
        elif opt == 8:
            temp = float(raw_input("Enter temperature: "))
            vehicle.command('CHANGE_CLIMATE_TEMPERATURE_SETTING', driver_temp=temp,
                            passenger_temp=temp)
        elif opt == 9:
            which_trunk = raw_input("Which trunk (front/rear):")
            vehicle.command('ACTUATE_TRUNK', which_trunk=which_trunk)
        elif opt == 10:
            vehicle.remote_start_drive()
        elif opt == 11:
            limit = int(raw_input("Enter charge limit: "))
            vehicle.command('CHANGE_CHARGE_LIMIT', percent=limit)
        elif opt == 12:
            if vehicle['charge_state']['charge_port_door_open']:
                vehicle.command('CHARGE_PORT_DOOR_CLOSE')
            else:
                vehicle.command('CHARGE_PORT_DOOR_OPEN')
        elif opt == 13:
            if vehicle['charge_state']['charging_state'].lower() == 'charging':
                vehicle.command('STOP_CHARGE')
            else:
                vehicle.command('START_CHARGE')
        elif opt == 14:
            heater = int(raw_input("Enter heater (0=Driver,1=Passenger,"
                                   "2=Rear left,3=Rear center,4=Rear right): "))
            level = int(raw_input("Enter level (0..3): "))
            vehicle.command('REMOTE_SEAT_HEATER_REQUEST', heater=heater,
                            level=level)
        elif opt == 15:
            vehicle.command('MEDIA_TOGGLE_PLAYBACK')
        elif opt == 16:
            command = raw_input("Enter command (close/vent):")
            vehicle.command('WINDOW_CONTROL', command=command, lat=0, lon=0)
        elif opt == 17:
            try:
                if vehicle['climate_state']['defrost_mode']:
                    vehicle.command('MAX_DEFROST', on=False)
                else:
                    vehicle.command('MAX_DEFROST', on=True)
            except KeyError:
                print('Not available')

def custom_auth(url):
    with [webdriver.Chrome, webdriver.Edge, webdriver.Firefox, webdriver.Opera,
          webdriver.Safari][args.web]() as browser:
        logging.info('Selenium opened %s', browser.capabilities['browserName'])
        browser.get(url)
        WebDriverWait(browser, 300).until(EC.url_contains('void/callback'))
        return browser.current_url

def main():
    default_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format=default_format)
    if not args.verify:
        # Disable SSL verify for Nominatim
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        geopy.geocoders.options.default_ssl_context = ctx
    email = raw_input('Enter email: ')
    with Tesla(email, verify=args.verify, proxy=args.proxy) as tesla:
        if webdriver:
            tesla.authenticator = custom_auth
        tesla.fetch_token()
        vehicles = tesla.vehicle_list()
        print('-'*80)
        fmt = '{:2} {:25} {:25} {:25}'
        print(fmt.format('ID', 'Display name', 'VIN', 'State'))
        for i, vehicle in enumerate(vehicles):
            print(fmt.format(i, vehicle['display_name'], vehicle['vin'],
                             vehicle['state']))
        print('-'*80)
        idx = int(raw_input("Select vehicle: "))
        print('-'*80)
        print('VIN decode:', ', '.join(vehicles[idx].decode_vin().values()))
        print('Option codes:', ', '.join(vehicles[idx].option_code_list()))
        print('-'*80)
        menu(vehicles[idx])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Tesla Owner API Menu')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='set logging level to debug')
    parser.add_argument('--verify', action='store_false',
                        help='disable verify SSL certificate')
    if webdriver:
        parser.add_argument('--chrome', action='store_const', dest='web',
                            const=0, default=0, help='use Chrome (default)')
        for c, s in enumerate(('edge', 'firefox', 'opera', 'safari'), start=1):
            parser.add_argument('--' + s, action='store_const', dest='web',
                                const=c, help='use %s browser' % s.title())
    parser.add_argument('--proxy', help='proxy server URL')
    args = parser.parse_args()
    main()
