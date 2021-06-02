""" Tesla Owner API CLI application using TeslaPy module """

# Author: Tim Dorssers

from __future__ import print_function
import ast
import logging
import getpass
import argparse
import tempfile
import webbrowser
from teslapy import Tesla, Vehicle

raw_input = vars(__builtins__).get('raw_input', input)  # Py2/3 compatibility

def get_passcode(args):
    return args.passcode if args.passcode else raw_input('Passcode: ')

def get_captcha(svg):
    with tempfile.NamedTemporaryFile(suffix='.svg', delete=False) as f:
        f.write(svg)
    webbrowser.open('file://' + f.name)
    return raw_input('Captcha: ')

def main():
    parser = argparse.ArgumentParser(description='Tesla Owner API CLI')
    parser.add_argument('-e', dest='email', help='login email', required=True)
    parser.add_argument('-p', dest='password', nargs='?', const='',
                        help='prompt/specify login password')
    parser.add_argument('-t', dest='passcode', help='two factor passcode')
    parser.add_argument('-u', dest='factor', help='use two factor device name')
    parser.add_argument('-f', dest='filter', help='filter on id, vin, etc.')
    parser.add_argument('-a', dest='api', help='API call endpoint name')
    parser.add_argument('-k', dest='keyvalue', help='API parameter (key=value)',
                        action='append', type=lambda kv: kv.split('=', 1))
    parser.add_argument('-c', dest='command', help='product command endpoint')
    parser.add_argument('-l', '--list', action='store_true',
                        help='list all selected vehicles/batteries')
    parser.add_argument('-o', '--option', action='store_true',
                        help='list vehicle option codes')
    parser.add_argument('-v', '--vin', action='store_true',
                        help='vehicle identification number decode')
    parser.add_argument('-w', '--wake', action='store_true',
                        help='wake up selected vehicle(s)')
    parser.add_argument('-g', '--get', action='store_true',
                        help='get rollup of all vehicle data')
    parser.add_argument('-b', '--battery', action='store_true',
                        help='get detailed battery state and config')
    parser.add_argument('-n', '--nearby', action='store_true',
                        help='list nearby charging sites')
    parser.add_argument('-m', '--mobile', action='store_true',
                        help='get mobile enabled state')
    parser.add_argument('-s', '--start', action='store_true',
                        help='remote start drive')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='set logging level to debug')
    args = parser.parse_args()
    default_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format=default_format)
    if args.password == '':
        password = getpass.getpass('Password: ')
    else:
        password = args.password
    with Tesla(args.email, password, lambda: get_passcode(args),
               (lambda _: args.factor) if args.factor else None,
               get_captcha) as tesla:
        tesla.fetch_token()
        selected = prod = tesla.vehicle_list() + tesla.battery_list()
        if args.filter:
            selected = [p for p in prod for v in p.values() if v == args.filter]
        logging.info('%d product(s), %d selected', len(prod), len(selected))
        for i, product in enumerate(selected):
            print('Product %d:' % i)
            # Show information or invoke API depending on arguments
            if args.list:
                print(product)
            if isinstance(product, Vehicle):
                if args.option:
                    print(', '.join(product.option_code_list()))
                if args.vin:
                    print(product.decode_vin())
                if args.wake:
                    product.sync_wake_up()
                if args.get:
                    print(product.get_vehicle_data())
                if args.nearby:
                    print(product.get_nearby_charging_sites())
                if args.mobile:
                    print(product.mobile_enabled())
                if args.start:
                    print(product.remote_start_drive())
            elif args.battery:
                print(product.get_battery_data())
            if args.api:
                data = {}
                for key, value in args.keyvalue or []:
                    try:
                        data[key] = ast.literal_eval(value)
                    except ValueError:
                        data[key] = value
                print(product.api(args.api, **data))

if __name__ == "__main__":
    main()
