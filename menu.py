""" Tesla API menu-based console application using TeslaPy module """

# Author: Tim Dorssers

from __future__ import print_function
import ssl
import logging
import argparse
import geopy.geocoders  # 1.14.0 or higher required
from geopy.geocoders import Nominatim
from geopy.exc import *
try:
    import webview  # Optional pywebview 3.0 or higher
except ImportError:
    webview = None
try:
    from selenium import webdriver  # Optional selenium 3.13.0 or higher
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except ImportError:
    webdriver = None
from teslapy import Tesla

raw_input = vars(__builtins__).get('raw_input', input)  # Py2/3 compatibility

def heading_to_str(deg):
    return ['NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW',
           'W', 'WNW', 'NW', 'NNW', 'N'][int(abs((deg - 11.25) % 360) / 22.5)]

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
    except (GeocoderTimedOut, GeocoderUnavailable) as e:
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
    print('-' * 80)
    # Vehicle state
    fmt = 'Vehicle Name: {:24} Odometer: {}'
    print(fmt.format(str(ve['vehicle_name']), vehicle.dist_units(ve['odometer'])))
    fmt = 'Car Version: {:25} Locked: {}'
    print(fmt.format(ve['car_version'], ve['locked']))
    door = {0: 'Closed', 1: 'Open'}
    fmt = 'Driver/Pass Front Door: {:14} Driver/Pass Rear Door: {}/{}'
    print(fmt.format('%s/%s' % (door.get(ve['df']), door.get(ve['pf'])),
                     door.get(ve['dr']), door.get(ve['pr'])))
    window = {0: 'Closed', 1: 'Venting', 2: 'Open'}
    fmt = 'Drvr/Pass Front Window: {:14} Driver/Pass Rear Window: {}/{}'
    print(fmt.format('%s/%s' % (window.get(ve.get('fd_window')),
                                window.get(ve.get('fp_window'))),
                     window.get(ve.get('rd_window')),
                     window.get(ve.get('rp_window'))))
    fmt = 'Front Trunk: {:25} Rear Trunk: {}'
    print(fmt.format(door.get(ve['ft']), door.get(ve['rt'])))
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
    print('-' * 80)
    # Drive state
    speed = 0 if dr['speed'] is None else dr['speed']
    fmt = 'Power: {:31} Speed: {}'
    print(fmt.format(str(dr['power']) + ' kW', vehicle.dist_units(speed, True)))
    fmt = 'Shift State: {:25} Heading: {}'
    print(fmt.format(str(dr['shift_state']), heading_to_str(dr['heading'])))
    print(u'GPS: {:.75}'.format(location))
    print('-' * 80)
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
    print('-' * 80)
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
    print('-' * 80)
    print('Superchargers:')
    fmt = '{:57} {} {}/{} stalls'
    for site in sites['superchargers']:
        print(fmt.format(site['name'],
                         vehicle.dist_units(site['distance_miles']),
                         site['available_stalls'], site['total_stalls']))

def show_charging_history(data):
    print(data['screen_title'])
    print('-' * 80)
    print('%s\t%s %s' % (data['total_charged']['title'],
                         data['total_charged']['value'],
                         data['total_charged']['after_adornment']))
    print('-' * 80)
    for point in data['charging_history_graph']['data_points']:
        if point['values'][0].get('raw_value', 0) <= 0:
            continue
        print('%s\t%s %s\t%s' % (point['timestamp']['display_string'],
                                 point['values'][0]['value'],
                                 point['values'][0]['after_adornment'],
                                 point['values'][0]['sub_title']))
    print('-' * 80)
    for item in data['total_charged_breakdown'].values():
        print('%s %s %s' % (item['value'], item['after_adornment'],
                            item['sub_title']))

def menu(vehicle):
    lst = ['Refresh', 'Charging history', 'Wake up', 'Nearby charging sites',
           'Honk horn', 'Flash lights', 'Lock/unlock', 'Climate on/off',
           'Set temperature', 'Actuate frunk/trunk', 'Remote start drive',
           'Set charge limit', 'Open/close charge port', 'Start/stop charge',
           'Seat heater request', 'Toggle media playback', 'Window control',
           'Max defrost', 'Set charging amps']
    opt = 0
    while True:
        if vehicle['state'] == 'online':
            if vehicle['in_service']:
                print('Vehicle is in service')
                print('-' * 80)
            elif not vehicle.mobile_enabled():
                print('Mobile access is not enabled for this vehicle')
                print('-' * 80)
                break
            # Display vehicle info, except after charging history/sites
            if opt != 2 and opt != 4:
                show_vehicle_data(vehicle.get_vehicle_data())
        else:
            print('Wake up vehicle to use remote functions/telemetry')
        print('-' * 80)
        # Display 3 column menu
        for i, option in enumerate(lst, 1):
            print('{:2} {:23}'.format(i, option), end='' if i % 3 else '\n')
        if i % 3:
            print()
        print('-' * 80)
        # Get user choice
        opt = int(raw_input("Choice (0 to quit): "))
        print('-' * 80)
        # Check if vehicle is still online, otherwise force refresh
        if opt > 3:
            vehicle.get_vehicle_summary()
            if vehicle['state'] != 'online' or vehicle['in_service']:
                opt = 1
        # Perform menu option
        class VehicleController:
    def __init__(self, vehicle):
        self.vehicle = vehicle
        self.actions = {
            1: self.no_action,
            2: self.show_history,
            3: self.wake_up,
            4: self.show_sites,
            5: self.honk,
            6: self.flash_lights,
            7: self.toggle_lock,
            8: self.toggle_climate,
            9: self.set_temperature,
            10: self.actuate_trunk,
            11: self.remote_start,
            12: self.set_charge_limit,
            13: self.toggle_charge_port,
            14: self.toggle_charging,
            15: self.set_seat_heater,
            16: self.toggle_media,
            17: self.window_control,
            18: self.max_defrost_toggle,
            19: self.set_charging_amps,
        }

    # ------------------ Action methods ------------------
    def no_action(self):
        pass

    def show_history(self):
        show_charging_history(self.vehicle.get_charge_history())

    def wake_up(self):
        print('Please wait...')
        self.vehicle.sync_wake_up()
        print('-' * 80)

    def show_sites(self):
        show_charging_sites(self.vehicle)

    def honk(self):
        self.vehicle.command('HONK_HORN')

    def flash_lights(self):
        self.vehicle.command('FLASH_LIGHTS')

    def toggle_lock(self):
        locked = self.vehicle['vehicle_state']['locked']
        self.vehicle.command('UNLOCK' if locked else 'LOCK')

    def toggle_climate(self):
        is_on = self.vehicle['climate_state']['is_climate_on']
        self.vehicle.command('CLIMATE_OFF' if is_on else 'CLIMATE_ON')

    def set_temperature(self):
        temp = float(input("Enter temperature: "))
        self.vehicle.command('CHANGE_CLIMATE_TEMPERATURE_SETTING',
                             driver_temp=temp, passenger_temp=temp)

    def actuate_trunk(self):
        which_trunk = input("Which trunk (front/rear): ")
        self.vehicle.command('ACTUATE_TRUNK', which_trunk=which_trunk)

    def remote_start(self):
        self.vehicle.command('REMOTE_START')

    def set_charge_limit(self):
        limit = int(input("Enter charge limit: "))
        self.vehicle.command('CHANGE_CHARGE_LIMIT', percent=limit)

    def toggle_charge_port(self):
        if self.vehicle['charge_state']['charge_port_door_open']:
            self.vehicle.command('CHARGE_PORT_DOOR_CLOSE')
        else:
            self.vehicle.command('CHARGE_PORT_DOOR_OPEN')

    def toggle_charging(self):
        charging = self.vehicle['charge_state']['charging_state'].lower()
        self.vehicle.command('STOP_CHARGE' if charging == 'charging' else 'START_CHARGE')

    def set_seat_heater(self):
        heater = int(input("Enter heater (0=Driver,1=Passenger,2=Rear left,3=Rear center,4=Rear right): "))
        level = int(input("Enter level (0..3): "))
        self.vehicle.command('REMOTE_SEAT_HEATER_REQUEST', heater=heater, level=level)

    def toggle_media(self):
        self.vehicle.command('MEDIA_TOGGLE_PLAYBACK')

    def window_control(self):
        command = input("Enter command (close/vent): ")
        self.vehicle.command('WINDOW_CONTROL', command=command, lat=0, lon=0)

    def max_defrost_toggle(self):
        try:
            if self.vehicle['climate_state']['defrost_mode']:
                self.vehicle.command('MAX_DEFROST', on=False)
            else:
                self.vehicle.command('MAX_DEFROST', on=True)
        except KeyError:
            print('Not available')

    def set_charging_amps(self):
        amps = int(input("Enter charging amps: "))
        self.vehicle.command('CHARGING_AMPS', charging_amps=amps)

    # ------------------ Handler ------------------
    def handle_option(self, opt):
        action = self.actions.get(opt)
        if action:
            action()
        else:
            print("Invalid option.")


# ------------------ Usage ------------------
def main():
    vehicle = get_vehicle_object()  # Replace with your actual vehicle object
    controller = VehicleController(vehicle)

    while True:
        print("\n--- Vehicle Control Menu ---")
        print("0. Exit")
        print("1. No Action")
        print("2. Show Charging History")
        print("3. Wake Up Vehicle")
        print("4. Show Charging Sites")
        print("5. Honk Horn")
        print("6. Flash Lights")
        print("7. Toggle Lock")
        print("8. Toggle Climate")
        print("9. Set Temperature")
        print("10. Actuate Trunk")
        print("11. Remote Start")
        print("12. Set Charge Limit")
        print("13. Toggle Charge Port Door")
        print("14. Start/Stop Charging")
        print("15. Set Seat Heater")
        print("16. Toggle Media Playback")
        print("17. Window Control")
        print("18. Max Defrost On/Off")
        print("19. Set Charging Amps")

        try:
            opt = int(input("Enter your option: "))
        except ValueError:
            print("Invalid input, please enter a number.")
            continue

        if opt == 0:
            print("Exiting...")
            break

        controller.handle_option(opt)


# Run the program
if __name__ == "__main__":
    main()

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
    with Tesla(email, verify=args.verify, proxy=args.proxy,
               sso_base_url=args.url) as tesla:
        if (webdriver and args.web is not None) or webview:
            tesla.authenticator = custom_auth
        if args.timeout:
            tesla.timeout = args.timeout
        vehicles = tesla.vehicle_list()
        print('-' * 80)
        fmt = '{:2} {:25} {:25} {:25}'
        print(fmt.format('ID', 'Display name', 'VIN', 'State'))
        for i, vehicle in enumerate(vehicles):
            print(fmt.format(i, vehicle['display_name'], vehicle['vin'],
                             vehicle['state']))
        print('-' * 80)
        idx = int(raw_input("Select vehicle: "))
        print('-' * 80)
        fmt = '{} last seen {} at {} % SoC'
        print(fmt.format(vehicles[0]['display_name'], vehicles[0].last_seen(),
                         vehicles[0]['charge_state']['battery_level']))
        print('-' * 80)
        print('VIN decode:', ', '.join(vehicles[idx].decode_vin().values()))
        print('Option codes:', ', '.join(vehicles[idx].option_code_list()))
        print('-' * 80)
        menu(vehicles[idx])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Tesla Owner API Menu')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='set logging level to debug')
    parser.add_argument('--url', help='SSO service base URL')
    parser.add_argument('--verify', action='store_false',
                        help='disable verify SSL certificate')
    parser.add_argument('--timeout', type=int, help='connect/read timeout')
    if webdriver:
        h = 'use Chrome browser' if webview else 'use Chrome browser (default)'
        parser.add_argument('--chrome', action='store_const', dest='web',
                            help=h, const=0, default=None if webview else 0)
        parser.add_argument('--opera', action='store_const', dest='web',
                                help='use Opera browser', const=1)
        if hasattr(webdriver.edge, 'options'):
            parser.add_argument('--edge', action='store_const', dest='web',
                                help='use Edge browser', const=2)
    parser.add_argument('--proxy', help='proxy server URL')
    args = parser.parse_args()
    main()

