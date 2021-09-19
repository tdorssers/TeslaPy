""" Tesla Owner API CLI application using TeslaPy module """

# Author: Tim Dorssers

from __future__ import print_function
import ast
import logging
import argparse
try:
    from selenium import webdriver  # 3.13.0 or higher required
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except ImportError:
    webdriver = None  # Optional import
from teslapy import Tesla, Vehicle

raw_input = vars(__builtins__).get('raw_input', input)  # Py2/3 compatibility

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
    with Tesla(args.email, verify=args.verify, proxy=args.proxy) as tesla:
        if webdriver:
            tesla.authenticator = custom_auth
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
                if args.stream:
                    product.stream(lambda x: print(x))
                if args.service:
                    print(product.get_service_scheduling_data())
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
    parser = argparse.ArgumentParser(description='Tesla Owner API CLI')
    parser.add_argument('-e', dest='email', help='login email', required=True)
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
    parser.add_argument('-r', '--stream', action='store_true',
                        help='receive streaming vehicle data on-change')
    parser.add_argument('--service', action='store_true',
                        help='get service self scheduling eligibility')
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
