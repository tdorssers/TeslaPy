""" Tesla API menu-based console application using TeslaPy module """

# Author: Tim Dorssers

from __future__ import print_function
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import teslapy
import logging
import getpass

raw_input = vars(__builtins__).get('raw_input', input)  # Py2/3 compatibility

CLIENT_ID='e4a9949fcfa04068f59abb5a658f2bac0a3428e4652315490b659d5ab3f35a9e'
CLIENT_SECRET='c75f14bbadc8bee3a7594412c31416f8300256d7668ea7e6e7f06727bfb9d220'
EMAIL=''
PASSWORD=''

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
        osm = Nominatim(user_agent='TeslaPy')
        location = osm.reverse(coords)
    except GeocoderTimedOut as e:
        logging.error(e)
        location = coords
    # Climate state
    fmt = 'Outside Temperature: {:15} Inside Temperature: {}'
    print(fmt.format(vehicle.temp_units(cl['outside_temp']),
                     vehicle.temp_units(cl['inside_temp'])))
    fmt = 'Driver Temperature Setting: {:8} Passenger Temperature Setting: {}'
    print(fmt.format(vehicle.temp_units(cl['driver_temp_setting']),
                     vehicle.temp_units(cl['passenger_temp_setting'])))
    fmt = 'Is Climate On: {:21} Fan Speed: {}'
    print(fmt.format(str(cl['is_climate_on']), cl['fan_status']))
    fmt = 'Driver Seat Heater: {:16} Passenger Seat Heater: {}'
    print(fmt.format(str(cl['seat_heater_left']), str(cl['seat_heater_right'])))
    fmt = 'Is Front Defroster On: {:13} Is Rear Defroster On: {}'
    print(fmt.format(str(cl['is_front_defroster_on']), str(cl['is_rear_defroster_on'])))
    print('-'*80)
    # Vehicle state
    fmt = 'Vehicle Name: {:22} Odometer: {}'
    print(fmt.format(ve['vehicle_name'], vehicle.dist_units(ve['odometer'])))
    fmt = 'Car Version: {:23} Locked: {}'
    print(fmt.format(ve['car_version'], ve['locked']))
    door = ['Closed', 'Open']
    fmt = 'Driver Front Door: {:17} Passenger Front Door: {}'
    print(fmt.format(door[ve['df']], door[ve['pf']]))
    fmt = 'Driver Rear Door: {:18} Passenger Rear Door: {}'
    print(fmt.format(door[ve['dr']], door[ve['pr']]))
    fmt = 'Front Trunk: {:23} Rear Trunk: {}'
    print(fmt.format(door[ve['ft']], door[ve['rt']]))
    fmt = 'Remote Start: {:22} Sun Roof Percent Open: {}'
    print(fmt.format(str(ve['remote_start']), ve['sun_roof_percent_open']))
    fmt = 'Speed Limit Mode: {:18} Current Limit: {}'
    limit = vehicle.dist_units(ve['speed_limit_mode']['current_limit_mph'], True)
    print(fmt.format(str(ve['speed_limit_mode']['active']), limit))
    fmt = 'Speed Limit Pin Set: {:15} Sentry Mode: {}'
    print(fmt.format(str(ve['speed_limit_mode']['pin_code_set']),
                     str(ve['sentry_mode'])))
    fmt = 'Valet Mode: {:24} Valet Pin Set: {}'
    print(fmt.format(str(ve['valet_mode']), str(not 'valet_pin_needed' in ve)))
    print('-'*80)
    # Drive state
    speed = 0 if dr['speed'] is None else dr['speed']
    fmt = 'Power: {:29} Speed: {}'
    print(fmt.format(str(dr['power']) + ' kW', vehicle.dist_units(speed, True)))
    fmt = 'Shift State: {:23} Heading: {}'
    print(fmt.format(str(dr['shift_state']), heading_to_str(dr['heading'])))
    print('GPS: {:.75}'.format(str(location)))
    print('-'*80)
    # Charging state
    fmt = 'Charging State: {:20} Time To Full Charge: {:02.0f}:{:02.0f}'
    print(fmt.format(ch['charging_state'],
                     *divmod(ch['time_to_full_charge'] * 60, 60)))
    phases = '3 x ' if ch['charger_phases'] == 2 else ''
    fmt = 'Charger Voltage: {:19} Charger Actual Current: {}{:d} A'
    print(fmt.format(str(ch['charger_voltage']) + ' V',
                     phases, ch['charger_actual_current']))
    fmt = 'Charger Power: {:21} Charge Rate: {}'
    print(fmt.format(str(ch['charger_power']) + ' kW',
                     vehicle.dist_units(ch['charge_rate'], True)))
    fmt = 'Battery Level: {:21} Battery Range: {}'
    print(fmt.format(str(ch['battery_level']) + ' %',
                     vehicle.dist_units(ch['battery_range'])))
    fmt = 'Charge Energy Added: {:15} Charge Range Added: {}'
    print(fmt.format(str(ch['charge_energy_added']) + ' kWh',
                     vehicle.dist_units(ch['charge_miles_added_ideal'])))
    fmt = 'Charge Limit SOC: {:18} Estimated Battery Range: {}'
    print(fmt.format(str(ch['charge_limit_soc']) + ' %',
                     vehicle.dist_units(ch['est_battery_range'])))
    fmt = 'Charge Port Door Open: {:13} Charge Port Latch: {}'
    print(fmt.format(str(ch['charge_port_door_open']),
                     str(ch['charge_port_latch'])))
    print('-'*80)
    # Vehicle config
    fmt = 'Car Type: {:26} Exterior Color: {}'
    print(fmt.format(co['car_type'], co['exterior_color']))
    fmt = 'Wheel Type: {:24} Spoiler Type: {}'
    print(fmt.format(co['wheel_type'], co['spoiler_type']))
    fmt = 'Roof Color: {:24} Charge Port Type: {}'
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
           'Actuate frunk', 'Actuate trunk', 'Remote start drive',
           'Set charge limit', 'Open/close charge port', 'Start/stop charge',
           'Seat heater request', 'Sun roof control', 'Toggle media playback']
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
        elif opt == 1:
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
            vehicle.command('ACTUATE_TRUNK', which_trunk='front')
        elif opt == 10:
            vehicle.command('ACTUATE_TRUNK', which_trunk='rear')
        elif opt == 11:
            vehicle.remote_start_drive()
        elif opt == 12:
            limit = int(raw_input("Enter charge limit: "))
            vehicle.command('CHANGE_CHARGE_LIMIT', percent=limit)
        elif opt == 13:
            if vehicle['charge_state']['charge_port_door_open']:
                vehicle.command('CHARGE_PORT_DOOR_CLOSE')
            else:
                vehicle.command('CHARGE_PORT_DOOR_OPEN')
        elif opt == 14:
            if vehicle['charge_state']['charging_state'].lower() == 'charging':
                vehicle.command('STOP_CHARGE')
            else:
                vehicle.command('START_CHARGE')
        elif opt == 15:
            heater = int(raw_input("Enter heater (0=Driver,1=Passenger,"
                                   "2=Rear left,3=Rear center,4=Rear right): "))
            level = int(raw_input("Enter level (0..3): "))
            vehicle.command('REMOTE_SEAT_HEATER_REQUEST', heater=heater,
                            level=level)
        elif opt == 16:
            state = raw_input("Enter state (close/vent):")
            vehicle.command('CHANGE_SUNROOF_STATE', state=state)
        elif opt == 17:
            vehicle.command('MEDIA_TOGGLE_PLAYBACK')

def main():
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - %(message)s')
    email = raw_input('Enter email: ') if not EMAIL else EMAIL
    password = getpass.getpass('Password: ') if not PASSWORD else PASSWORD
    with teslapy.Tesla(email, password, CLIENT_ID, CLIENT_SECRET) as tesla:
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
    main()
