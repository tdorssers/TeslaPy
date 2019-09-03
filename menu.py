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
    
def show_vehicle_data(data):
    cl = data['climate_state']
    ve = data['vehicle_state']
    dr = data['drive_state']
    ch = data['charge_state']
    co = data['vehicle_config']
    # Lookup address at coordinates
    try:
        osm = Nominatim(user_agent='test')
        location = osm.reverse('%s, %s' % (dr['latitude'], dr['longitude']))
    except GeocoderTimedOut as e:
        logging.error(e)
        location = None
    # Climate state
    fmt = 'Outside Temperature: {:15} Inside Temperature: {} C'
    print(fmt.format(str(cl['outside_temp']) + ' C', cl['inside_temp']))
    fmt = 'Driver Temperature Setting: {:8} Passenger Temperature Setting: {} C'
    print(fmt.format(str(cl['driver_temp_setting']) + ' C',
                     cl['passenger_temp_setting']))
    fmt = 'Is Climate On: {:21} Fan Speed: {}'
    print(fmt.format(str(cl['is_climate_on']), cl['fan_status']))
    fmt = 'Driver Seat Heater: {:16} Passenger Seat Heater: {}'
    print(fmt.format(str(cl['seat_heater_left']), str(cl['seat_heater_right'])))
    print('-'*80)
    # Vehicle state
    fmt = 'Vehicle Name: {:22} Odometer: {:.1f} km'
    print(fmt.format(ve['vehicle_name'], ve['odometer'] / 0.62137119))
    fmt = 'Car Version: {:23} Locked: {}'
    print(fmt.format(ve['car_version'], ve['locked']))
    door = ['Closed', 'Open']
    fmt = 'Driver Front Door: {:17} Passenger Front Door: {}'
    print(fmt.format(door[ve['df']], door[ve['pf']]))
    fmt = 'Driver Rear Door: {:18} Passenger Rear Door: {}'
    print(fmt.format(door[ve['dr']], door[ve['pr']]))
    fmt = 'Front Trunk: {:23} Rear Trunk: {}'
    print(fmt.format(door[ve['ft']], door[ve['rt']]))
    fmt = 'Center Display State: {:14} Panoramic Roof State: {}'
    print(fmt.format('On' if ve['center_display_state'] else 'Off',
                     ve['sun_roof_state']))
    fmt = 'Speed Limit Mode: {:18} Current Limit: {:.1f} km/h'
    print(fmt.format(str(ve['speed_limit_mode']['active']),
                     ve['speed_limit_mode']['current_limit_mph'] / 0.62137119))
    fmt = 'Speed Limit Pin Set: {:15} Sentry Mode: {}'
    print(fmt.format(str(ve['speed_limit_mode']['pin_code_set']),
                     str(ve['sentry_mode'])))
    fmt = 'Valet Mode: {:24} Valet Pin Set: {}'
    print(fmt.format(str(ve['valet_mode']), str(not 'valet_pin_needed' in ve)))
    fmt = 'Remote Start Enabled: {:14} Remote Start: {}'
    print(fmt.format(str(ve['remote_start_enabled']), str(ve['remote_start'])))
    print('-'*80)
    # Drive state
    speed = 0 if dr['speed'] is None else dr['speed'] / 0.62137119
    fmt = 'Power: {:29} Speed: {:.1f} km/h'
    print(fmt.format(str(dr['power']) + ' kW', speed))
    fmt = 'Shift State: {:23} Heading: {}'
    print(fmt.format(str(dr['shift_state']), heading_to_str(dr['heading'])))
    if location is None:
        print('GPS: %s, %s' % (dr['latitude'], dr['longitude']))
    else:
        print('GPS: ' + location.address)
    print('-'*80)
    # Charging state
    fmt = 'Charging State: {:20} Time To Full Charge: {:02.0f}:{:02.0f}'
    print(fmt.format(ch['charging_state'],
                     *divmod(ch['time_to_full_charge'] * 60, 60)))
    phases = '3 x ' if ch['charger_phases'] == 2 else ''
    fmt = 'Charger Voltage: {:19} Charger Actual Current: {}{:d} A'
    print(fmt.format(str(ch['charger_voltage']) + ' V',
                     phases, ch['charger_actual_current']))
    fmt = 'Charger Power: {:21} Charge Rate: {:.1f} km/h'
    print(fmt.format(str(ch['charger_power']) + ' kW',
                     ch['charge_rate'] / 0.62137119))
    fmt = 'Battery Level: {:21} Battery Range: {:.1f} km'
    print(fmt.format(str(ch['battery_level']) + ' %',
                     ch['battery_range'] / 0.62137119))
    fmt = 'Charge Energy Added: {:15} Charge Range Added: {:.1f} km'
    print(fmt.format(str(ch['charge_energy_added']) + ' kWh',
                     ch['charge_miles_added_ideal'] / 0.62137119))
    fmt = 'Charge Limit SOC: {:18} Estimated Battery Range: {:.1f} km'
    print(fmt.format(str(ch['charge_limit_soc']) + ' %',
                     ch['est_battery_range'] / 0.62137119))
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

def show_charging_sites(data):
    print('Destination Charging:')
    fmt = '{:57} {:.1f} km'
    for site in data['destination_charging']:
        print(fmt.format(site['name'], site['distance_miles'] / 0.62137119))
    print('-'*80)
    print('Superchargers:')
    fmt = '{:57} {:.1f} km {}/{} stalls'
    for site in data['superchargers']:
        print(fmt.format(site['name'], site['distance_miles'] / 0.62137119,
                         site['available_stalls'], site['total_stalls']))

def menu(vehicle):
    lst = ['Refresh', 'Wake up', 'Nearby charging sites', 'Honk horn',
           'Flash lights', 'Lock/unlock', 'Climate on/off', 'Set temperature',
           'Actuate frunk', 'Actuate trunk', 'Remote start drive',
           'Set charge limit', 'Charge port open/close', 'Start/stop charge',
           'Seat heater request']
    opt = 0
    while True:
        if opt != 3:
            # Show vehicle status
            if vehicle['state'] == 'online':
                if not vehicle.mobile_enabled():
                    print('Mobile access is not enabled for this vehicle')
                    print('-'*80)
                try:
                    show_vehicle_data(vehicle.get_vehicle_data())
                except teslapy.HTTPError as e:
                    logging.error(e)
            else:
                print('Wake up vehicle to use remote functions/telemetry')
        print('-'*80)
        # Display 3 column menu
        for i, option in enumerate(lst, 1):
            print('{:2} {:23}'.format(i, option), end='' if i % 3 else '\n')
        if i % 3:
            print()
        print('-'*80)
        opt = int(raw_input("Choice (0 to quit): "))
        print('-'*80)
        # Perform menu option
        if opt == 0:
            break
        elif opt == 1:
            pass
        elif opt == 2:
            print('Please wait...')
            try:
                vehicle.sync_wake_up()
            except (teslapy.TimeoutError, teslapy.HTTPError) as e:
                logging.error(e)
            print('-'*80)
        elif opt == 3:
            show_charging_sites(vehicle.get_nearby_charging_sites())
        elif opt == 4:
            vehicle.api('HONK_HORN')
        elif opt == 5:
            vehicle.api('FLASH_LIGHTS')
        elif opt == 6:
            if vehicle['vehicle_state']['locked']:
                vehicle.api('UNLOCK')
            else:
                vehicle.api('LOCK')
        elif opt == 7:
            if vehicle['climate_state']['is_climate_on']:
                vehicle.api('CLIMATE_OFF')
            else:
                vehicle.api('CLIMATE_ON')
        elif opt == 8:
            temp = float(raw_input("Enter temperature: "))
            data = {'driver_temp': temp, 'passenger_temp': temp}
            vehicle.api('CHANGE_CLIMATE_TEMPERATURE_SETTING', data=data)
        elif opt == 9:
            vehicle.api('ACTUATE_TRUNK', data={'which_trunk': 'front'})
        elif opt == 10:
            vehicle.api('ACTUATE_TRUNK', data={'which_trunk': 'rear'})
        elif opt == 11:
            vehicle.api('REMOTE_START', data={'password': PASSWORD})
        elif opt == 12:
            limit = int(raw_input("Enter charge limit: "))
            data = {'percent': limit}
            vehicle.api('CHANGE_CHARGE_LIMIT', data=data)
        elif opt == 13:
            if vehicle['charge_state']['charge_port_door_open']:
                vehicle.api('CHARGE_PORT_DOOR_CLOSE')
            else:
                vehicle.api('CHARGE_PORT_DOOR_OPEN')
        elif opt == 14:
            if vehicle['charge_state']['charging_state'].lower() == 'charging':
                vehicle.api('STOP_CHARGE')
            else:
                vehicle.api('START_CHARGE')
        elif opt == 15:
            heater = int(raw_input("Enter heater (0=Driver,1=Passenger,"
                                   "2=Rear left,3=Rear center,4=Rear right): "))
            level = int(raw_input("Enter level (0..3): "))
            data = {'heater': heater, 'level': level}
            vehicle.api('REMOTE_SEAT_HEATER_REQUEST', data=data)

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
        print('Option codes:', ', '.join(vehicles[idx].option_code_list()))
        print('-'*80)
        menu(vehicles[idx])

if __name__ == "__main__":
    main()
