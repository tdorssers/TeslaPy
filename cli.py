""" Tesla Owner API CLI application using TeslaPy module """

# Author: Tim Dorssers

from __future__ import print_function
import ast
import logging
import argparse
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
from teslapy import Tesla, Vehicle, Battery, SolarPanel

raw_input = vars(__builtins__).get('raw_input', input)  # Py2/3 compatibility

def custom_auth(url):
    # Use pywebview if no web browser specified
    if getattr(args, 'web', None) is None:
        result = ['']
        window = webview.create_window('Login', url)
        def on_loaded():
            result[0] = window.get_current_url()
            if 'void/callback' in result[0].split('?')[0]:
                window.destroy()
        window.loaded += on_loaded
        webview.start()
        return result[0]
    # Use selenium to control specified web browser
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
        if (webdriver and args.web is not None) or webview:
            tesla.authenticator = custom_auth
        if args.timeout:
            tesla.timeout = args.timeout
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
                if args.stream:
                    product.stream(print)
                if args.service:
                    print(product.get_service_scheduling_data())
            elif isinstance(product, Battery) and args.battery:
                print(product.get_battery_data())
            elif isinstance(product, SolarPanel) and args.site:
                print(product.get_site_data())
            if args.api or args.command:
                data = {}
                for key, value in args.keyvalue or []:
                    try:
                        data[key] = ast.literal_eval(value)
                    except (SyntaxError, ValueError):
                        data[key] = value
                if args.api:
                    print(product.api(args.api, **data))
                else:
                    print(product.command(args.command, **data))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Tesla Owner API CLI')
    parser.add_argument('-e', dest='email', help='login email', required=True)
    parser.add_argument('-f', dest='filter', help='filter on id, vin, etc.')
    parser.add_argument('-a', dest='api', help='API call endpoint name')
    parser.add_argument('-k', dest='keyvalue', help='API parameter (key=value)',
                        action='append', type=lambda kv: kv.split('=', 1))
    parser.add_argument('-c', dest='command', help='product command endpoint')
    parser.add_argument('-t', dest='timeout', type=int,
                        help='connect/read timeout')
    parser.add_argument('-p', dest='proxy', help='proxy server URL')
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
    parser.add_argument('-s', '--site', action='store_true',
                        help='get current site generation data')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='set logging level to debug')
    parser.add_argument('-r', '--stream', action='store_true',
                        help='receive streaming vehicle data on-change')
    parser.add_argument('-S', '--service', action='store_true',
                        help='get service self scheduling eligibility')
    parser.add_argument('-V', '--verify', action='store_false',
                        help='disable verify SSL certificate')
    if webdriver:
        for c, s in enumerate(('chrome', 'edge', 'firefox', 'opera', 'safari')):
            d, h = (0, ' (default)') if not webview and c == 0 else (None, '')
            parser.add_argument('--' + s, action='store_const', dest='web',
                                help='use %s WebDriver' % s.title() + h,
                                const=c, default=d)
    args = parser.parse_args()
    main()
