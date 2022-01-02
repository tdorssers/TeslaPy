""" Tesla Owner API GUI application using TeslaPy module """

# Author: Tim Dorssers

import ssl
import time
import logging
import threading
import webbrowser
import multiprocessing
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
try:
    from Tkinter import *
    from tkSimpleDialog import *
    from ConfigParser import *
except ImportError:
    from tkinter import *
    from tkinter.simpledialog import *
    from configparser import *
import teslapy

class LabelGridDialog(Dialog):
    """ Display dialog box with table without cancel button """

    def __init__(self, master, title=None, table=None):
        self.table = table or []
        # The Dialog constructor must be called last
        Dialog.__init__(self, master, title)

    def body(self, master):
        for args in self.table:
            Label(master, text=args.pop('text')).grid(args)

    def buttonbox(self):
        box = Frame(self)
        w = Button(box, text="OK", width=10, command=self.ok, default=ACTIVE)
        w.pack(side=LEFT, padx=5, pady=5)
        self.bind("<Return>", self.ok)
        box.pack()

class SeatHeaterDialog(Dialog):
    """ Display dialog box with comboboxes to select seat heaters """

    def __init__(self, master):
        Dialog.__init__(self, master, title='Seat Heater')

    def body(self, master):
        Label(master, text="Heater:").grid(row=0, sticky=E)
        Label(master, text="Level:").grid(row=1, sticky=E)
        lst = ['0: Front Left', '1: Front Right', '2: Rear left',
               '3: Rear center', '4: Rear right']
        self.heater = StringVar(value=lst[0])
        OptionMenu(master, self.heater, *lst).grid(row=0, column=1, sticky=W)
        self.level = IntVar(value=0)
        OptionMenu(master, self.level, 0, 1, 2, 3).grid(row=1, column=1, sticky=W)

    def apply(self):
        # Only return heater ID and level
        self.result = (int(self.heater.get()[0]), self.level.get())

class ControlDialog(Dialog):
    """ Display dialog box with radio buttons to select sunroof/window state """

    def __init__(self, master, title=None):
        Dialog.__init__(self, master, title)

    def body(self, master):
        self.state = StringVar(value='vent')
        Radiobutton(master, text="Vent", variable=self.state,
                    value='vent').pack(anchor=W)
        Radiobutton(master, text="Close", variable=self.state,
                    value='close').pack(anchor=W)

    def apply(self):
        self.result = self.state.get()

class ChargingDialog(Dialog):
    """ Display dialog box to get scheduled charging parameters """

    def __init__(self, master, title='Scheduled charging'):
        Dialog.__init__(self, master, title)

    def body(self, master):
        self.enable = BooleanVar()
        Checkbutton(master, text='Enable', variable=self.enable).pack()
        self.time = StringVar()
        self.time.set('0:00')
        Label(master, text='Time:').pack(side=LEFT)
        Entry(master, textvariable=self.time).pack(side=LEFT)

    def apply(self):
        parts = self.time.get().split(':')
        self.result = {'enable': self.enable.get(),
                       'time': int(parts[0]) * 60 + int(parts[1])}

class DepartureDialog(Dialog):
    """ Display dialog box to get scheduled departure parameters """

    def __init__(self, master, title='Scheduled departure'):
        Dialog.__init__(self, master, title)

    def body(self, master):
        self.depart_time = StringVar()
        self.depart_time.set('8:00')
        Label(master, text='Departure Time:').grid()
        Entry(master, textvariable=self.depart_time).grid(row=0, column=1)
        self.enable = BooleanVar()
        Checkbutton(master, text='Enable', variable=self.enable).grid(row=0, column=2)
        group = LabelFrame(master, text='Preconditioning')
        self.hvac = BooleanVar()
        Checkbutton(group, text='Enable', variable=self.hvac).pack(side=LEFT)
        self.hvac_weekdays = BooleanVar()
        Checkbutton(group, text='Weekdays',
                    variable=self.hvac_weekdays).pack(side=RIGHT)
        group.grid(columnspan=3, sticky=EW, padx=5)
        group = LabelFrame(master, text='Off Peak Charging')
        self.off_peak = BooleanVar()
        Checkbutton(group, text='Enable', variable=self.off_peak).grid(sticky=W)
        self.off_peak_weekdays = BooleanVar()
        Checkbutton(group, text='Weekdays',
                    variable=self.off_peak_weekdays).grid(row=0, column=1, sticky=E)
        self.end_time = StringVar()
        self.end_time.set('6:00')
        Label(group, text='Off Peak End Time:').grid()
        Entry(group, textvariable=self.end_time).grid(row=1, column=1, padx=5, pady=5)
        group.grid(columnspan=3, sticky=EW, padx=5)

    def apply(self):
        depart = self.depart_time.get().split(':')
        end = self.end_time.get().split(':')
        self.result = {'enable': self.enable.get(),
                       'departure_time': int(depart[0]) * 60 + int(depart[1]),
                       'preconditioning_enabled': self.hvac.get(),
                       'preconditioning_weekdays_only': self.hvac_weekdays.get(),
                       'off_peak_charging_enabled': self.off_peak.get(),
                       'off_peak_charging_weekdays_only': self.off_peak_weekdays.get(),
                       'end_off_peak_time': int(end[0]) * 60 + int(end[1])}

class ChargeHistoryDialog(Dialog):
    """ Display dialog box with charging history graph """

    def __init__(self, master, data):
        self.data = data
        Dialog.__init__(self, master, title='Charging History')

    def body(self, master):
        Label(master, text=self.data['screen_title'],
              font=('TkTextFont', 12)).pack()
        Label(master, text=self.data['total_charged']['title'],
              anchor=W).pack(fill=X)
        text = '%s %s' % (self.data['total_charged']['value'],
                          self.data['total_charged']['after_adornment'])
        Label(master, text=text, anchor=W,
              font=('TkTextFont', 12, 'bold')).pack(fill=X)
        # Draw graph
        canvas = Canvas(master, width=440, height=410)
        scale = self.data['charging_history_graph']['y_range_max'] / 320
        for y in self.data['charging_history_graph']['horizontal_grid_lines']:
            y_scaled = 335 - y / scale
            canvas.create_line(5, y_scaled, 403, y_scaled, dash=(2, 2))
        for x in self.data['charging_history_graph']['vertical_grid_lines']:
            canvas.create_line(14 + x * 13, 15, 14 + x * 13, 335, dash=(2, 2))
        for label in self.data['charging_history_graph']['x_labels']:
            canvas.create_text(14 + label['raw_value'] * 13, 335,
                               text=label['value'], anchor=NE)
        for label in self.data['charging_history_graph']['y_labels']:
            text = label['value'] + '\n' + label.get('after_adornment', '')
            canvas.create_text(408, 335 - label.get('raw_value', 0) / scale,
                               text=text.strip(), anchor=W)
        # Stacked bars
        x = 8
        for point in self.data['charging_history_graph']['data_points']:
            y = 335
            for idx, value in enumerate(point['values']):
                if idx == 0:
                    if value.get('raw_value', 0) <= 0:
                        canvas.create_line(x, y, x, y - 2, width=7)
                    continue
                color = {1: 'blue', 2: 'red', 3: 'grey'}.get(idx)
                y_new = y - value.get('raw_value', 0) / scale
                canvas.create_line(x, y, x, y_new, width=7, fill=color)
                y = y_new - 1
            x += 13
        # Breakdown
        x = 5
        for idx, key in enumerate(self.data['total_charged_breakdown']):
            color = {'home': 'blue', 'super_charger': 'red',
                     'other': 'grey'}.get(key)
            canvas.create_oval(10 + idx * 165, 370, 20 + idx * 165, 380,
                               fill=color, outline=color)
            item = self.data['total_charged_breakdown'][key]
            text = '%s%s\n%s' % (item['value'], item['after_adornment'],
                                 item['sub_title'])
            canvas.create_text(25 + idx * 165, 375, text=text, anchor=W)
            x_new = x + item.get('raw_value', 0) * 4.1
            canvas.create_line(x, 400, x_new, 400, width=7, fill=color)
            x = x_new + 1
        canvas.pack()

    def buttonbox(self):
        box = Frame(self)
        w = Button(box, text="OK", width=10, command=self.ok, default=ACTIVE)
        w.pack(side=LEFT, padx=5, pady=5)
        self.bind("<Return>", self.ok)
        box.pack()

class StatusBar(Frame):
    """ Status bar widget with transient and permanent status messages """

    def __init__(self, master, **kwargs):
        Frame.__init__(self, master, **kwargs)
        self.text_value = StringVar()
        Label(self, bd=1, relief=SUNKEN, anchor=W,
              textvariable=self.text_value).pack(fill=X, side=LEFT, expand=1)
        self.status_value = StringVar()
        Label(self, bd=1, relief=SUNKEN, anchor=W,
              textvariable=self.status_value).pack(fill=X, side=LEFT, expand=1)
        self.indicator_label = Label(self, bd=1, relief=SUNKEN, width=1)
        self.indicator_label.pack(side=LEFT)
        # Save default background color
        self.no_color = self.indicator_label.cget('bg')

    def text(self, text):
        """ Set informational text """
        self.text_value.set(str(text)[:120])

    def status(self, status):
        """ Set status text """
        self.status_value.set(status)

    def indicator(self, color):
        """ Set or reset indicator color """
        self.indicator_label.config(bg=color if color else self.no_color)
        self.update_idletasks()

class LabelVarGrid(Label):
    """ Label widget with updatable textvariable and grid positioning """

    def __init__(self, master, **kwargs):
        Label.__init__(self, master)
        self.value = StringVar()
        self.config(textvariable=self.value)
        self.grid(**kwargs)

    def text(self, text):
        """ Set textvariable of label """
        self.value.set(text)

class Dashboard(Frame):
    """ Dashboard widget showing vehicle data """

    def __init__(self, master, **kwargs):
        Frame.__init__(self, master, **kwargs)
        left = Frame(self)
        left.pack(side=LEFT, padx=5)
        right = Frame(self)
        right.pack(side=LEFT, padx=5)
        # Vehicle image on right frame
        self.vehicle_image = Label(right)
        self.vehicle_image.pack()
        # Climate state on left frame
        self.layout(left, 'Climate State',
                    [('outside_temp', 'Outside Temperature:'),
                     ('inside_temp', 'Inside Temperature:'),
                     ('driver_temp', 'Driver Temperature Setting:'),
                     ('passenger_temp', 'Passenger Temperature Setting:'),
                     ('is_climate_on', 'Is Climate On:'),
                     ('fan_status', 'Fan Speed:'),
                     ('driver_heater', 'Driver Seat Heater:'),
                     ('passenger_heater', 'Passenger Seat Heater:'),
                     ('front_defroster', 'Is Front Defroster On:'),
                     ('rear_defroster', 'Is Rear Defroster On:')])
        # Vehicle state on left frame
        self.layout(left, 'Vehicle State',
                    [('vehicle_name', 'Vehicle Name:'),
                     ('odometer', 'Odometer:'),
                     ('car_version', 'Car Version:'),
                     ('locked', 'Locked:'),
                     ('df', 'Driver Front Door:'),
                     ('pf', 'Passenger Front Door:'),
                     ('dr', 'Driver Rear Door:'),
                     ('pr', 'Passenger Rear Door:'),
                     ('fd', 'Driver Front Window:'),
                     ('fp', 'Passenger Front Window:'),
                     ('rd', 'Driver Rear Window:'),
                     ('rp', 'Passenger Rear Window:'),
                     ('ft', 'Front Trunk:'),
                     ('rt', 'Rear Trunk:'),
                     ('remote_start', 'Remote Start:'),
                     ('user_present', 'Is User Present:'),
                     ('speed_limit', 'Speed Limit Mode:'),
                     ('current_limit', 'Current Limit:'),
                     ('speed_limit_pin', 'Speed Limit Pin Set:'),
                     ('sentry_mode', 'Sentry Mode:'),
                     ('valet_mode', 'Valet Mode:'),
                     ('valet_pin', 'Valet Pin Set:'),
                     ('sw_update', 'Software Update:'),
                     ('sw_duration', 'Expected Duration:'),
                     ('update_ver', 'Update Version:'),
                     ('inst_perc', 'Install Percentage:')])
        # Drive state on right frame
        group = self.layout(right, 'Drive State',
                            [('power', 'Power:'),
                             ('speed', 'Speed:'),
                             ('shift_state', 'Shift State:'),
                             ('heading', 'Heading:')])
        Label(group, text='GPS:').grid(row=2, column=0, sticky=E)
        self.gps = LabelVarGrid(group, row=2, column=1, columnspan=3, sticky=W)
        self.gps.config(wraplength=330, justify=LEFT)
        # Charging state on right frame
        self.layout(right, 'Charging State',
                    [('charging_state', 'Charging State:'),
                     ('time_to_full', 'Time To Full Charge:'),
                     ('charger_voltage', 'Charger Voltage:'),
                     ('charger_request', 'Requested Current:'),
                     ('charger_current', 'Charger Actual Current:'),
                     ('charger_power', 'Charger Power:'),
                     ('battery_level', 'Battery Level:'),
                     ('charge_rate', 'Charge Rate:'),
                     ('battery_range', 'Battery Range:'),
                     ('energy_added', 'Charge Energy Added:'),
                     ('range_added', 'Charge Range Added:'),
                     ('charge_limit_soc', 'Charge Limit SOC:'),
                     ('est_battery_range', 'Estimated Battery Range:'),
                     ('charge_port_door', 'Charge Port Door Open:'),
                     ('charge_port_latch', 'Charge Port Latch:'),
                     ('fast_charger', 'Fast Charger:'),
                     ('trip_charging', 'Trip Charging:'),
                     ('charging_pending', 'Scheduled Charging:'),
                     ('charging_start', 'Charging Start Time:'),
                     ('scheduled_charging', 'Scheduled Charging Mode:'),
                     ('departure_time', 'Scheduled Departure:'),
                     ('off_peak_charge', 'Off Peak Charging:'),
                     ('off_peak_times', 'Off Peak Charging Times:'),
                     ('off_peak_end_time', 'Off Peak End Time:'),
                     ('preconditioning', 'Preconditioning:'),
                     ('preconditioning_times', 'Preconditioning Times:')])
        # Vehicle config on left frame
        self.layout(left, 'Vehicle Config',
                    [('car_type', 'Car Type:'),
                     ('exterior_color', 'Exterior Color:'),
                     ('wheel_type', 'Wheel Type:'),
                     ('spoiler_type', 'Spoiler Type:'),
                     ('roof_color', 'Roof Color:'),
                     ('charge_port_type', 'Charge Port Type:')])
        # Service on left frame
        self.layout(left, 'Service', [('next_appt', 'Next appointment:')])

    def layout(self, master, text, labels):
        """ Group four columns of widgets from list of tupels """
        group = LabelFrame(master, text=text, padx=5, pady=5)
        group.pack(padx=5, pady=5, fill=X)
        for i, (name, txt) in enumerate(labels):
            Label(group, text=txt).grid(row=i // 2, column=i % 2 * 2, sticky=E)
            w = LabelVarGrid(group, row=i // 2, column=i % 2 * 2 + 1, sticky=W)
            setattr(self, name, w)  # Set named widget to dashboard
        return group

    def update_widgets(self):
        """ Set values of dashboard widgets """
        cl = app.vehicle['climate_state']
        ve = app.vehicle['vehicle_state']
        dr = app.vehicle['drive_state']
        ch = app.vehicle['charge_state']
        co = app.vehicle['vehicle_config']
        # pylint: disable=E1101
        # Climate state
        self.outside_temp.text(app.vehicle.temp_units(cl['outside_temp']))
        self.inside_temp.text(app.vehicle.temp_units(cl['inside_temp']))
        self.driver_temp.text(app.vehicle.temp_units(cl['driver_temp_setting']))
        self.passenger_temp.text(app.vehicle.temp_units(cl['passenger_temp_setting']))
        self.is_climate_on.text(str(cl['is_climate_on']))
        self.fan_status.text(cl['fan_status'])
        self.driver_heater.text(cl['seat_heater_left'])
        self.passenger_heater.text(cl['seat_heater_right'])
        self.front_defroster.text(str(cl['is_front_defroster_on']))
        self.rear_defroster.text(str(cl['is_rear_defroster_on']))
        # Vehicle state
        self.vehicle_name.text(ve['vehicle_name'])
        self.odometer.text(app.vehicle.dist_units(ve['odometer']))
        self.car_version.text(ve['car_version'])
        self.locked.text(str(ve['locked']))
        door = ['Closed', 'Open']
        self.df.text(door[bool(ve['df'])])
        self.pf.text(door[bool(ve['pf'])])
        self.dr.text(door[bool(ve['dr'])])
        self.pr.text(door[bool(ve['pr'])])
        window = {0: 'Closed', 1: 'Venting', 2: 'Open'}
        self.fd.text(window.get(ve.get('fd_window')))
        self.fp.text(window.get(ve.get('fp_window')))
        self.rd.text(window.get(ve.get('rd_window')))
        self.rp.text(window.get(ve.get('rp_window')))
        self.ft.text(door[bool(ve['ft'])])
        self.rt.text(door[bool(ve['rt'])])
        self.remote_start.text(str(ve['remote_start']))
        self.user_present.text(str(ve['is_user_present']))
        self.speed_limit.text(str(ve['speed_limit_mode']['active']))
        limit = ve['speed_limit_mode']['current_limit_mph']
        self.current_limit.text(app.vehicle.dist_units(limit, True))
        self.speed_limit_pin.text(str(ve['speed_limit_mode']['pin_code_set']))
        self.sentry_mode.text(str(ve.get('sentry_mode')))
        self.valet_mode.text(str(ve['valet_mode']))
        self.valet_pin.text(str(not 'valet_pin_needed' in ve))
        status = ve['software_update']['status'] or 'unavailable'
        wt = ve['software_update'].get('warning_time_remaining_ms', 0) / 1000
        status += ' in {:02.0f}:{:02.0f}'.format(*divmod(wt, 60)) if wt else ''
        self.sw_update.text(status.capitalize())
        sueds = divmod(ve['software_update']['expected_duration_sec'] / 60, 60)
        self.sw_duration.text('{:02.0f}:{:02.0f}'.format(*sueds))
        self.update_ver.text(ve['software_update'].get('version') or 'None')
        self.inst_perc.text(ve['software_update'].get('install_perc') or 'None')
        # Drive state
        power = 0 if dr['power'] is None else dr['power']
        self.power.text('%d kW' % power)
        speed = 0 if dr['speed'] is None else dr['speed']
        self.speed.text(app.vehicle.dist_units(speed, True))
        self.shift_state.text(str(dr['shift_state']))
        self.heading.text(self._heading_to_str(dr['heading']))
        self.gps.text(app.update_thread.location)
        # Charging state
        self.charging_state.text(ch['charging_state'])
        ttfc = divmod(ch['time_to_full_charge'] * 60, 60)
        self.time_to_full.text('{:02.0f}:{:02.0f}'.format(*ttfc))
        volt = 0 if ch['charger_voltage'] is None else ch['charger_voltage']
        self.charger_voltage.text('%d V' % volt)
        self.charger_request.text('%d A' % ch['charge_current_request'])
        ph = '3 x ' if ch['charger_phases'] == 2 else ''
        amps = 0 if ch['charger_actual_current'] is None else ch['charger_actual_current']
        self.charger_current.text('%s%d A' % (ph, amps))
        charger_power = 0 if ch['charger_power'] is None else ch['charger_power']
        self.charger_power.text('%d kW' % charger_power)
        if ch['usable_battery_level'] < ch['battery_level']:
            usable = ' (%d %% usable)' % ch['usable_battery_level']
        else:
            usable = ''
        self.battery_level.text('%d %%%s' % (ch['battery_level'], usable))
        self.charge_rate.text(app.vehicle.dist_units(ch['charge_rate'], True))
        self.battery_range.text(app.vehicle.dist_units(ch['battery_range']))
        self.energy_added.text('%.1f kWh' % ch['charge_energy_added'])
        self.range_added.text(app.vehicle.dist_units(ch['charge_miles_added_rated']))
        self.charge_limit_soc.text('%d %%' % ch['charge_limit_soc'])
        self.est_battery_range.text(app.vehicle.dist_units(ch['est_battery_range']))
        self.charge_port_door.text(str(ch['charge_port_door_open']))
        self.charge_port_latch.text(str(ch['charge_port_latch']))
        self.fast_charger.text(str(ch['fast_charger_present']))
        self.trip_charging.text(str(ch['trip_charging']))
        self.charging_pending.text(str(ch['scheduled_charging_pending']))
        if ch['scheduled_charging_start_time']:
            st = time.localtime(ch['scheduled_charging_start_time'])
            self.charging_start.text(time.strftime('%X', st))
        else:
            self.charging_start.text(None)
        self.scheduled_charging.text(ch.get('scheduled_charging_mode'))
        if ch.get('scheduled_departure_time'):
            dt = time.localtime(ch['scheduled_departure_time'])
            self.departure_time.text(time.strftime('%X', dt))
        else:
            self.departure_time.text(None)
        self.off_peak_charge.text(str(ch.get('off_peak_charging_enabled')))
        self.off_peak_times.text(ch.get('off_peak_charging_times'))
        if 'off_peak_hours_end_time' in ch:
            ophet = divmod(ch['off_peak_hours_end_time'], 60)
            self.off_peak_end_time.text('{:02.0f}:{:02.0f}'.format(*ophet))
        else:
            self.off_peak_end_time.text(None)
        self.preconditioning.text(str(ch.get('preconditioning_enabled')))
        self.preconditioning_times.text(ch.get('preconditioning_times'))
        # Vehicle config
        self.car_type.text(co['car_type'])
        self.exterior_color.text(co['exterior_color'])
        self.wheel_type.text(co['wheel_type'])
        self.spoiler_type.text(co['spoiler_type'])
        self.roof_color.text(co['roof_color'])
        self.charge_port_type.text(co['charge_port_type'])

    @staticmethod
    def _heading_to_str(deg):
        """ Convert heading in degrees to a direction string """
        return ['NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW',
                'NNW', 'N'][int(abs((deg - 11.25) % 360) / 22.5)]

def show_webview(url):
    """ Shows the SSO page in a webview and returns the redirected URL """
    result = ['']
    window = webview.create_window('Login', url)
    def on_loaded():
        result[0] = window.get_current_url()
        if 'void/callback' in result[0].split('?')[0]:
            window.destroy()
    window.loaded += on_loaded
    webview.start()  # Blocks the main thread until webview is closed
    return result[0]

class App(Tk):
    """ Main application class """

    def __init__(self, **kwargs):
        Tk.__init__(self, **kwargs)
        self.title('Tesla')
        self.protocol('WM_DELETE_WINDOW', self.save_and_quit)
        # Add menu bar
        menu = Menu(self)
        app_menu = Menu(menu, tearoff=0)
        app_menu.add_command(label='Login', command=self.login)
        app_menu.add_command(label='Logout', command=self.logout)
        app_menu.add_separator()
        app_menu.add_command(label='Exit', command=self.save_and_quit)
        menu.add_cascade(label='App', menu=app_menu)
        self.vehicle_menu = Menu(menu, tearoff=0)
        self.vehicle_menu.add_command(label='Show option codes', state=DISABLED,
                                      command=self.option_codes)
        self.vehicle_menu.add_command(label='Decode VIN', state=DISABLED,
                                      command=self.decode_vin)
        self.vehicle_menu.add_command(label='Charge history', state=DISABLED,
                                      command=self.charge_history)
        self.vehicle_menu.add_separator()
        menu.add_cascade(label='Vehicle', menu=self.vehicle_menu)
        self.cmd_menu = Menu(menu, tearoff=0)
        self.cmd_menu.add_command(label='Wake up', state=DISABLED,
                                  command=self.wake_up)
        self.cmd_menu.add_command(label='Nearby charging sites', state=DISABLED,
                                  command=self.charging_sites)
        self.cmd_menu.add_command(self.add_cmd_args('HONK_HORN'))
        self.cmd_menu.add_command(self.add_cmd_args('FLASH_LIGHTS'))
        self.cmd_menu.add_command(label='Lock/unlock', state=DISABLED,
                                  command=self.lock_unlock)
        self.cmd_menu.add_command(label='Climate on/off', state=DISABLED,
                                  command=self.climate_on_off)
        self.cmd_menu.add_command(label='Set temperature', state=DISABLED,
                                  command=self.set_temperature)
        self.cmd_menu.add_command(label='Actuate frunk', state=DISABLED,
                                  command=lambda: self.actuate_trunk('front'))
        self.cmd_menu.add_command(label='Actuate trunk', state=DISABLED,
                                  command=lambda: self.actuate_trunk('rear'))
        self.cmd_menu.add_command(label='Remote start drive', state=DISABLED,
                                  command=lambda: self.cmd('REMOTE_START'))
        self.cmd_menu.add_command(label='Set charge limit', state=DISABLED,
                                  command=self.set_charge_limit)
        self.cmd_menu.add_command(label='Open/close charge port', state=DISABLED,
                                  command=self.open_close_charge_port)
        self.cmd_menu.add_command(label='Start/stop charge', state=DISABLED,
                                  command=self.start_stop_charge)
        self.cmd_menu.add_command(label='Seat heater request', state=DISABLED,
                                  command=self.seat_heater)
        self.cmd_menu.add_command(label='Control sun roof', state=DISABLED,
                                  command=self.vent_close_sun_roof)
        self.media_menu = Menu(menu, tearoff=0)
        self.cmd_menu.add_cascade(label='Media', state=DISABLED,
                                  menu=self.media_menu)
        for endpoint in ['MEDIA_TOGGLE_PLAYBACK', 'MEDIA_NEXT_TRACK',
                         'MEDIA_PREVIOUS_TRACK', 'MEDIA_NEXT_FAVORITE',
                         'MEDIA_PREVIOUS_FAVORITE', 'MEDIA_VOLUME_UP',
                         'MEDIA_VOLUME_DOWN']:
            self.media_menu.add_command(self.add_cmd_args(endpoint))
        self.cmd_menu.add_command(label='Schedule sw update', state=DISABLED,
                                  command=self.schedule_sw_update)
        self.cmd_menu.add_command(self.add_cmd_args('CANCEL_SOFTWARE_UPDATE'))
        self.cmd_menu.add_command(label='Control windows', state=DISABLED,
                                  command=self.window_control)
        self.cmd_menu.add_command(label='Max defrost', state=DISABLED,
                                  command=self.max_defrost)
        self.cmd_menu.add_command(label='Set charge amps', state=DISABLED,
                                  command=self.charging_amps)
        self.cmd_menu.add_command(label='Scheduled charging', state=DISABLED,
                                  command=self.scheduled_charging)
        self.cmd_menu.add_command(label='Scheduled departure', state=DISABLED,
                                  command=self.scheduled_departure)
        menu.add_cascade(label='Command', menu=self.cmd_menu)
        opt_menu = Menu(menu, tearoff=0)
        self.auto_refresh = BooleanVar()
        opt_menu.add_checkbutton(label='Auto refresh',
                                 variable=self.auto_refresh,
                                 command=self.update_dashboard)
        self.debug = BooleanVar()
        opt_menu.add_checkbutton(label='Console debugging', variable=self.debug,
                                 command=self.apply_settings)
        self.verify = BooleanVar()
        self.verify.set(1)
        opt_menu.add_checkbutton(label='Verify SSL', variable=self.verify,
                                 command=self.apply_settings)
        opt_menu.add_command(label='Set proxy URL', command=self.set_proxy)
        web_menu = Menu(menu, tearoff=0)
        opt_menu.add_cascade(label='Web browser', menu=web_menu,
                             state=NORMAL if webdriver else DISABLED)
        self.browser = IntVar()
        for v, l in enumerate(('Chrome', 'Edge', 'Firefox', 'Opera', 'Safari')):
            web_menu.add_radiobutton(label=l, value=v, variable=self.browser)
        self.selenium = BooleanVar()
        opt_menu.add_checkbutton(label='Use selenium', variable=self.selenium,
                                 state=NORMAL if webdriver else DISABLED,
                                 command=self.apply_settings)
        menu.add_cascade(label='Options', menu=opt_menu)
        help_menu = Menu(menu, tearoff=0)
        help_menu.add_command(label='About', command=self.about)
        menu.add_cascade(label='Help', menu=help_menu)
        self.config(menu=menu)
        self.update_scheduled = 0
        # Add widgets
        self.dashboard = Dashboard(self)
        self.dashboard.pack(pady=5, fill=X)
        self.status = StatusBar(self)
        self.status.pack(side=BOTTOM, fill=X)
        self.status.text('Not logged in')
        # Read config
        config = RawConfigParser()
        self.email = ''
        self.proxy = ''
        try:
            config.read('gui.ini')
            self.email = config.get('app', 'email')
            self.verify.set(config.get('app', 'verify'))
            self.proxy = config.get('app', 'proxy')
            self.browser.set(config.get('app', 'browser'))
            self.selenium.set(config.get('app', 'selenium'))
            self.auto_refresh.set(config.get('display', 'auto_refresh'))
            self.debug.set(config.get('display', 'debug'))
        except (NoSectionError, NoOptionError, ParsingError):
            pass
        # Initialize logging
        default_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        logging.basicConfig(format=default_format)
        self.apply_settings()

    def add_cmd_args(self, endpoint):
        """ Return add_command arguments for given named endpoint """
        return {'label': endpoint.capitalize().replace('_', ' '),
                'state': DISABLED, 'command': lambda: self.cmd(endpoint)}

    def custom_auth(self, url):
        """ Automated or manual authentication """
        # Use pywebview if available and selenium not selected
        if webview and not self.selenium.get():
            return pool.apply(show_webview, (url, ))  # Run in separate process
        # Use selenium if available and selected
        if webdriver and self.selenium.get():
            with [webdriver.Chrome, webdriver.Edge,
                  webdriver.Firefox, webdriver.Opera,
                  webdriver.Safari][self.browser.get()]() as browser:
                browser.get(url)
                wait = WebDriverWait(browser, 300)
                wait.until(EC.url_contains('void/callback'))
                return browser.current_url
        # Fallback to manual authentication
        webbrowser.open(url)
        # Ask user for callback URL in new dialog
        result = [None]
        event = threading.Event()
        def show_dialog():
            """ Inner function to show dialog from main thread """
            result[0] = askstring('Login', 'URL after authentication:')
            event.set()  # Signal completion
        self.after_idle(show_dialog)  # Start from main thread
        event.wait()  # Block login thread until URL is entered
        return result[0]

    def login(self):
        """ Display login dialog and start new thread to get vehicle list """
        prompt = 'Email:' if (webdriver and self.selenium.get()) or \
                 (webview and not self.selenium.get()) else 'Use browser' \
                 ' to login.\nPage Not Found will be shown at success.\n\nEmail:'
        result = askstring('Login', prompt, initialvalue=self.email)
        if result:
            self.email = result
            self.status.text('Logging in...')
            retry = teslapy.Retry(total=2,
                                  status_forcelist=(500, 502, 503, 504))
            tesla = teslapy.Tesla(self.email, authenticator=self.custom_auth,
                                  verify=self.verify.get(), proxy=self.proxy,
                                  retry=retry)
            # Create and start login thread. Check thread status after 100 ms
            self.login_thread = LoginThread(tesla)
            self.login_thread.start()
            self.after(100, self.process_login)

    def process_login(self):
        """ Waits for thread to finish and updates vehicle menu """
        if self.login_thread.is_alive():
            # Check again after 100 ms
            self.after(100, self.process_login)
        elif self.login_thread.exception:
            self.status.text(self.login_thread.exception)
        else:
            # Remove vehicles from menu
            self.vehicle_menu.delete(4, END)
            # Add to menu and select first vehicle
            self.selected = IntVar(value=0)
            for i, vehicle in enumerate(self.login_thread.vehicles):
                label = '%s (%s)' % (vehicle['display_name'], vehicle['vin'])
                self.vehicle_menu.add_radiobutton(label=label, value=i,
                                                  variable=self.selected,
                                                  command=self.select)
            if self.login_thread.vehicles:
                # Enable show option codes and wake up command
                for i in range(0, 3):
                    self.vehicle_menu.entryconfig(i, state=NORMAL)
                self.cmd_menu.entryconfig(0, state=NORMAL)
                self.select()
            else:
                self.status.text('No vehicles')

    def logout(self):
        """ Sign out and redraw dashboard """
        if not hasattr(self, 'login_thread'):
            return
        # Use pywebview if available and selenium not selected
        if webview and not self.selenium.get():
            # Run in separate process
            pool.apply(show_webview, (self.login_thread.tesla.logout(), ))
        # Do not sign out if selenium is available and selected
        self.login_thread.tesla.logout(not (webdriver and self.selenium.get()))
        del self.vehicle
        # Redraw dashboard
        self.dashboard.pack_forget()
        self.dashboard = Dashboard(self)
        self.dashboard.pack(pady=5, fill=X)
        # Remove vehicles from menu
        self.vehicle_menu.delete(4, END)
        # Disable commands
        for i in range(0, 3):
            self.vehicle_menu.entryconfig(i, state=DISABLED)
        for i in range(0, self.cmd_menu.index(END) + 1):
            self.cmd_menu.entryconfig(i, state=DISABLED)
        for i in range(0, self.media_menu.index(END) + 1):
            self.media_menu.entryconfig(i, state=DISABLED)
        self.status.text('Not logged in')

    def select(self):
        """ Select vehicle and start new thread to get vehicle image """
        self.vehicle = self.login_thread.vehicles[self.selected.get()]
        # Create and start image thread. Check thread status after 100 ms
        self.image_thread = ImageThread(self.vehicle)
        self.image_thread.start()
        self.after(100, self.process_select)
        # Create and start service thread. Check thread status after 100 ms
        self.service_thread = ServiceThread(self.vehicle)
        self.service_thread.start()
        self.after(100, self.process_service)
        # Start status thread only once
        if not hasattr(self, 'status_thread'):
            self.update_status()
        self.update_dashboard()

    def process_select(self):
        """ Waits for thread to finish and displays vehicle image """
        if self.image_thread.is_alive():
            # Check again after 100 ms
            self.after(100, self.process_select)
        elif self.image_thread.exception:
            # Handle errors
            self.status.text(self.image_thread.exception)
        else:
            # Display vehicle image
            self.dashboard.vehicle_image.config(image=self.image_thread.photo)

    def process_service(self):
        """ Waits for thread to finish and displays service data """
        if self.service_thread.is_alive():
            # Check again after 100 ms
            self.after(100, self.process_service)
        elif self.service_thread.exception:
            # Handle errors
            self.status.text(self.service_thread.exception)
        else:
            # Display service data
            nat = self.service_thread.data.get('next_appt_timestamp')
            # pylint: disable=E1101
            self.dashboard.next_appt.text(nat)

    def show_status(self):
        """ Display vehicle state """
        self.status.text('%s is %s' % (self.vehicle['display_name'],
                                       self.vehicle['state']))
        # Enable/disable commands
        state = NORMAL if self.vehicle['state'] == 'online' else DISABLED
        for i in range(1, self.cmd_menu.index(END) + 1):
            if self.cmd_menu.entrycget(i, 'state') != state:
                self.cmd_menu.entryconfig(i, state=state)
        for i in range(0, self.media_menu.index(END) + 1):
            if self.media_menu.entrycget(i, 'state') != state:
                self.media_menu.entryconfig(i, state=state)

    def update_status(self):
        """ Creates a new thread to get vehicle summary """
        self.status_thread = StatusThread(self.vehicle)
        # Don't start if auto refresh is enabled
        if not self.auto_refresh.get() or self.vehicle['state'] != 'online':
            self.status_thread.start()
        self.after(100, self.process_status)

    def process_status(self):
        """ Waits for thread to finish and updates status """
        if self.status_thread.is_alive():
            self.after(100, self.process_status)
        else:
            # Increase status polling rate if vehicle is online
            delay = 60000 if self.vehicle['state'] == 'online' else 240000
            # Run thread again and show status
            self.after(delay, self.update_status)
            if self.status_thread.exception:
                self.status.text(self.status_thread.exception)
            else:
                self.show_status()

    def update_dashboard(self, scheduled=False):
        """ Create new thread to get vehicle data """
        if scheduled:
            self.update_scheduled = False
        if hasattr(self, 'vehicle') and self.vehicle['state'] != 'online':
            return
        # pylint: disable=E0203
        if hasattr(self, 'update_thread') and self.update_thread.is_alive():
            return
        if hasattr(self, 'vehicle') and not self.update_scheduled:
            self.show_status()
            self.update_thread = UpdateThread(self.vehicle)
            self.update_thread.start()
            self.after(100, self.process_update_dashboard)

    def process_update_dashboard(self):
        """ Waits for thread to finish and updates dashboard data """
        if self.update_thread.is_alive():
            self.after(100, self.process_update_dashboard)
            return
        try:
            delay = 4000  # Default update polling rate
            if self.update_thread.exception:
                self.status.text(self.update_thread.exception)
                self.status.indicator('red')
            else:
                timestamp_ms = self.vehicle['vehicle_state']['timestamp']
                self.status.status(time.ctime(timestamp_ms / 1000))
                self.status.indicator('green')
                self.dashboard.update_widgets()
                # Increase polling rate if charging or user present
                if (self.vehicle['charge_state']['charging_state'] == 'Charging'
                        or self.vehicle['vehicle_state']['is_user_present']):
                    delay = 1000
            # Run again if auto refresh is on and fail threshold is not exceeded
            if self.auto_refresh.get() and self.update_thread.fail_cnt < 10:
                self.after(delay, self.update_dashboard, True)
                self.update_scheduled = True
            else:
                self.auto_refresh.set(FALSE)
                self.status.indicator(None)
        except Exception as e:
            # On error turn off auto refresh and re-raise
            import sys
            self.status.text('{}: {}'.format(*sys.exc_info()[:2]))
            self.auto_refresh.set(FALSE)
            self.status.indicator(None)
            raise

    def wake_up(self):
        """ Creates a new thread to wake up vehicle """
        self.status.text('Please wait...')
        self.wake_up_thread = WakeUpThread(self.vehicle)
        self.wake_up_thread.start()
        self.after(100, self.process_wake_up)
        # Disable wake up command
        self.cmd_menu.entryconfig(0, state=DISABLED)

    def process_wake_up(self):
        """ Waits for thread to finish and updates widgets """
        if self.wake_up_thread.is_alive():
            self.after(100, self.process_wake_up)
        elif self.wake_up_thread.exception:
            self.status.text(self.wake_up_thread.exception)
            self.cmd_menu.entryconfig(0, state=NORMAL)
        else:
            # Enable wake up command and start update thread
            self.cmd_menu.entryconfig(0, state=NORMAL)
            self.update_dashboard()

    def about(self):
        """ Show about dialog """
        LabelGridDialog(self, 'About',
                        [{'text': 'Tesla Owner API Python GUI by Tim Dorssers'},
                         {'text': 'Tcl/Tk toolkit version %s' % TkVersion}])

    def option_codes(self):
        """ Show vehicle option codes in a dialog """
        table = []
        for i, item in enumerate(self.vehicle.option_code_list()):
            table.append(dict(text=item, row=i // 2, column=i % 2, sticky=W))
        LabelGridDialog(self, 'Option codes', table)

    def decode_vin(self):
        """ Show decoded vin in a dialog """
        table = []
        for i, item in enumerate(self.vehicle.decode_vin().items()):
            table.append(dict(text=item[0] + ':', row=i, sticky=E))
            table.append(dict(text=item[1], row=i, column=1, sticky=W))
        LabelGridDialog(self, 'Decode VIN', table)

    def charging_sites(self):
        """ Creates a new thread to get nearby charging sites """
        self.status.text('Please wait...')
        self.nearby_sites_thread = NearbySitesThread(self.vehicle)
        self.nearby_sites_thread.start()
        self.after(100, self.process_charging_sites)

    def process_charging_sites(self):
        """ Waits for thread to finish and displays sites in a dialog box """
        if self.nearby_sites_thread.is_alive():
            self.after(100, self.process_charging_sites)
        elif self.nearby_sites_thread.exception:
            self.status.text(self.nearby_sites_thread.exception)
        else:
            self.show_status()
            # Prepare list of label and grid attributes for table view
            table = [dict(text='Destination Charging:', columnspan=2)]
            r = 1
            for site in self.nearby_sites_thread.sites['destination_charging']:
                table.append(dict(text=site['name'], row=r, sticky=W))
                dist = self.vehicle.dist_units(site['distance_miles'])
                table.append(dict(text=dist, row=r, column=1, sticky=W))
                r += 1
            table.append(dict(text='Superchargers:', row=r, columnspan=2))
            r += 1
            for site in self.nearby_sites_thread.sites['superchargers']:
                table.append(dict(text=site['name'], row=r, sticky=W))
                dist = self.vehicle.dist_units(site['distance_miles'])
                table.append(dict(text=dist, row=r, column=1, sticky=W))
                text = '%d/%d free stalls' % (site['available_stalls'],
                                              site['total_stalls'])
                table.append(dict(text=text, row=r, column=2, sticky=W))
                r += 1
            LabelGridDialog(self, 'Nearby Charging Sites', table)

    def charge_history(self):
        """ Creates a new thread to get charging history """
        self.status.text('Please wait...')
        self.charge_history_thread = ChargeHistoryThread(self.vehicle)
        self.charge_history_thread.start()
        self.after(100, self.process_charge_history)
        
    def process_charge_history(self):
        """ Waits for thread to finish and displays history in a dialog box """
        if self.charge_history_thread.is_alive():
            self.after(100, self.process_charge_history)
        elif self.charge_history_thread.exception:
            self.status.text(self.charge_history_thread.exception)
        else:
            self.show_status()
            ChargeHistoryDialog(self, self.charge_history_thread.result)

    def cmd(self, name, **kwargs):
        """ Creates a new thread to command vehicle """
        self.status.text('Please wait...')
        self.command_thread = CommandThread(self.vehicle, name, **kwargs)
        self.command_thread.start()
        self.after(100, self.process_cmd)

    def process_cmd(self):
        """ Waits for thread to finish and update widgets """
        if self.command_thread.is_alive():
            self.after(100, self.process_cmd)
        elif self.command_thread.exception:
            self.status.text(self.command_thread.exception)
        else:
            # Update dashboard after 1 second if auto refresh is disabled
            if not self.auto_refresh.get():
                self.after(1000, self.update_dashboard)

    def lock_unlock(self):
        """ Lock or unlock vehicle """
        if self.vehicle['vehicle_state']['locked']:
            self.cmd('UNLOCK')
        else:
            self.cmd('LOCK')

    def climate_on_off(self):
        """ Turn climate control on or off """
        if self.vehicle['climate_state']['is_climate_on']:
            self.cmd('CLIMATE_OFF')
        else:
            self.cmd('CLIMATE_ON')

    def set_temperature(self):
        """ Set climate control temperature """
        # Get user input using a simple dialog box
        temp = askfloat('Set', 'Temperature')
        if temp:
            self.cmd('CHANGE_CLIMATE_TEMPERATURE_SETTING', driver_temp=temp,
                     passenger_temp=temp)

    def actuate_trunk(self, which_trunk):
        """ Actuate trunk or frunk """
        self.cmd('ACTUATE_TRUNK', which_trunk=which_trunk)

    def set_charge_limit(self):
        """ Set charging limit """
        limit = askinteger('Set', 'Charge Limit')
        if limit:
            self.cmd('CHANGE_CHARGE_LIMIT', percent=limit)

    def open_close_charge_port(self):
        """ Open, unlock or close charging port """
        if (self.vehicle['charge_state']['charge_port_door_open'] and
                self.vehicle['charge_state']['charge_port_latch'] != 'Engaged'):
            self.cmd('CHARGE_PORT_DOOR_CLOSE')
        else:
            self.cmd('CHARGE_PORT_DOOR_OPEN')

    def start_stop_charge(self):
        """ Start or stop vehicle charging """
        if self.vehicle['charge_state']['charging_state'].lower() == 'charging':
            self.cmd('STOP_CHARGE')
        else:
            self.cmd('START_CHARGE')

    def seat_heater(self):
        """ Ask user which seat to heat """
        dlg = SeatHeaterDialog(self)
        if dlg.result:
            self.cmd('REMOTE_SEAT_HEATER_REQUEST', heater=dlg.result[0],
                     level=dlg.result[1])

    def vent_close_sun_roof(self):
        """ Ask user to vent or close the sun roof """
        dlg = ControlDialog(self, 'Sun Roof')
        if dlg.result:
            self.cmd('CHANGE_SUNROOF_STATE', state=dlg.result)

    def schedule_sw_update(self):
        """ Start software upgrade in two minutes """
        self.cmd('SCHEDULE_SOFTWARE_UPDATE', offset_sec=120)

    def window_control(self):
        """ Ask user to vent or close windows """
        dlg = ControlDialog(self, 'Windows')
        if dlg.result:
            self.cmd('WINDOW_CONTROL', command=dlg.result, lat=0, lon=0)

    def max_defrost(self):
        """ Set max defrost mode """
        try:
            if self.vehicle['climate_state']['defrost_mode']:
                self.cmd('MAX_DEFROST', on=False)
            else:
                self.cmd('MAX_DEFROST', on=True)
        except KeyError:
            pass

    def charging_amps(self):
        """ Set charging amps """
        # Get user input using a simple dialog box
        temp = askinteger('Set', 'Amperage')
        if temp:
            self.cmd('CHARGING_AMPS', charging_amps=temp)

    def scheduled_charging(self):
        """ Set scheduled charging """
        dlg = ChargingDialog(self)
        if dlg.result:
            self.cmd('SCHEDULED_CHARGING', **dlg.result)

    def scheduled_departure(self):
        """ Set scheduled departure """
        dlg = DepartureDialog(self)
        if dlg.result:
            self.cmd('SCHEDULED_DEPARTURE', **dlg.result)

    def apply_settings(self):
        """ Set logging level and SSL context """
        level = logging.DEBUG if self.debug.get() else logging.WARNING
        logging.getLogger().setLevel(level)
        # Set Nominatim SSL verify
        if self.verify.get():
            geopy.geocoders.options.default_ssl_context = None
        else:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            geopy.geocoders.options.default_ssl_context = ctx

    def set_proxy(self):
        """ Set proxy server URL """
        temp = askstring('Set', 'Proxy URL', initialvalue=self.proxy)
        self.proxy = '' if temp is None else temp

    def save_and_quit(self):
        """ Save settings to file and quit app """
        config = RawConfigParser()
        config.add_section('app')
        config.add_section('display')
        try:
            config.set('app', 'email', self.email)
            config.set('app', 'proxy', self.proxy)
            config.set('app', 'verify', self.verify.get())
            config.set('app', 'browser', self.browser.get())
            config.set('app', 'selenium', self.selenium.get())
            config.set('display', 'auto_refresh', self.auto_refresh.get())
            config.set('display', 'debug', self.debug.get())
            with open('gui.ini', 'w') as configfile:
                config.write(configfile)
        except (IOError, AttributeError):
            pass
        finally:
            self.quit()

class UpdateThread(threading.Thread):
    """ Retrieves vehicle data and looks up address if coordinates change """

    _coords = None
    location = None
    fail_cnt = 0

    def __init__(self, vehicle):
        threading.Thread.__init__(self)
        self.vehicle = vehicle
        self.exception = None

    def run(self):
        try:
            self.vehicle.get_vehicle_data()
        except (teslapy.RequestException, ValueError) as e:
            # Detect if vehicle went to sleep
            try:
                self.vehicle.get_vehicle_summary()
            except (teslapy.RequestException, ValueError) as e:
                pass
            UpdateThread.fail_cnt += 1  # Increase for consecutive errors
            self.exception = e
        else:
            coords = '%s, %s' % (self.vehicle['drive_state']['latitude'],
                                 self.vehicle['drive_state']['longitude'])
            # Have coordinates changed over previous instance?
            if self._coords != coords:
                UpdateThread._coords = coords
                # Fallback to coordinates if lookup fails
                self.location = coords
                try:
                    # Lookup address at coordinates
                    osm = Nominatim(user_agent='TeslaPy',
                                    proxies=self.vehicle.tesla.proxies)
                    self.location = osm.reverse(coords).address
                except GeocoderTimedOut:
                    UpdateThread._coords = None  # Force lookup
                except GeopyError as e:
                    UpdateThread._coords = None
                    UpdateThread.fail_cnt += 1
                    self.exception = e
                finally:
                    UpdateThread.location = self.location  # Save location
            UpdateThread.fail_cnt = 0

class WakeUpThread(threading.Thread):
    """ Wake vehicle up """

    def __init__(self, vehicle):
        threading.Thread.__init__(self)
        self.vehicle = vehicle
        self.exception = None

    def run(self):
        try:
            self.vehicle.sync_wake_up()
        except (teslapy.VehicleError, teslapy.RequestException) as e:
            self.exception = e

class ImageThread(threading.Thread):
    """ Compose vehicle image """

    def __init__(self, vehicle):
        threading.Thread.__init__(self)
        self.vehicle = vehicle
        self.exception = None
        self.photo = None

    def run(self):
        try:
            response = self.vehicle.compose_image(size=300)
        except teslapy.RequestException as e:
            self.exception = e
        else:
            # Tk 8.6 has native PNG support, older Tk require PIL
            try:
                import base64
                self.photo = PhotoImage(data=base64.b64encode(response))
            except TclError:
                from PIL import Image, ImageTk
                import io
                self.photo = ImageTk.PhotoImage(Image.open(io.BytesIO(response)))

class LoginThread(threading.Thread):
    """ Authenticate and retrieve vehicle list """

    def __init__(self, tesla):
        threading.Thread.__init__(self)
        self.tesla = tesla
        self.exception = None
        self.vehicles = []

    def run(self):
        try:
            self.tesla.fetch_token()
            self.vehicles = self.tesla.vehicle_list()
        except Exception as e:
            self.exception = str(e).replace('\n', '')

class StatusThread(threading.Thread):
    """ Retrieve vehicle status summary """

    def __init__(self, vehicle):
        threading.Thread.__init__(self)
        self.vehicle = vehicle
        self.exception = None

    def run(self):
        try:
            self.vehicle.get_vehicle_summary()
        except (teslapy.RequestException, ValueError) as e:
            self.exception = e

class CommandThread(threading.Thread):
    """ Send vehicle command """

    def __init__(self, vehicle, name, **kwargs):
        threading.Thread.__init__(self)
        self.vehicle = vehicle
        self.name = name
        self.data = kwargs
        self.exception = None

    def run(self):
        try:
            self.vehicle.command(self.name, **self.data)
        except (teslapy.VehicleError, teslapy.RequestException, ValueError) as e:
            self.exception = e

class NearbySitesThread(threading.Thread):
    """ Retrieve nearby charging sites """

    def __init__(self, vehicle):
        threading.Thread.__init__(self)
        self.vehicle = vehicle
        self.exception = None
        self.sites = None

    def run(self):
        try:
            self.sites = self.vehicle.get_nearby_charging_sites()
        except (teslapy.RequestException, ValueError) as e:
            self.exception = e

class ServiceThread(threading.Thread):
    """ Retrieve next service appointment """

    def __init__(self, vehicle):
        threading.Thread.__init__(self)
        self.vehicle = vehicle
        self.exception = None
        self.data = None

    def run(self):
        try:
            self.data = self.vehicle.get_service_scheduling_data()
        except (teslapy.RequestException, ValueError) as e:
            self.exception = e

class ChargeHistoryThread(threading.Thread):
    """ Retrieve charging history """

    def __init__(self, vehicle):
        threading.Thread.__init__(self)
        self.vehicle = vehicle
        self.exception = None
        self.result = None

    def run(self):
        try:
            self.result = self.vehicle.get_charge_history()
        except (teslapy.RequestException, ValueError) as e:
            self.exception = e

if __name__ == "__main__":
    pool = multiprocessing.Pool(1)
    app = App()
    app.mainloop()
    app.destroy()
