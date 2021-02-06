""" Tesla Owner API GUI application using TeslaPy module """

# Author: Tim Dorssers

from __future__ import print_function
import time
import logging
import threading
from geopy.geocoders import Nominatim
from geopy.exc import *
try:
    from Tkinter import *
    from tkSimpleDialog import *
    from ConfigParser import *
except ImportError:
    from tkinter import *
    from tkinter.simpledialog import *
    from configparser import *
import teslapy

passcode = None

class LoginDialog(Dialog):
    """ Display dialog box to enter email and password """

    def __init__(self, master):
        Dialog.__init__(self, master, title='Login')

    def body(self, master):
        Label(master, text="Email:").grid(row=0, sticky=W)
        Label(master, text="Password:").grid(row=1, sticky=W)
        self.email = Entry(master)
        self.email.grid(row=0, column=1)
        # Set previously entered email as default value
        if hasattr(self.master, 'email'):
            self.email.insert(0, self.master.email)
        self.password = Entry(master, show='*')
        self.password.grid(row=1, column=1)
        return self.email

    def apply(self):
        self.result = (self.email.get(), self.password.get())

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
        lst = ['0: Driver', '1: Passenger', '2: Rear left', '3: Rear center',
               '4: Rear right']
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
        self.text_value.set(str(text)[:120])

    def status(self, status):
        self.status_value.set(status)

    def indicator(self, color):
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
        group = LabelFrame(left, text='Climate State', padx=5, pady=5)
        group.pack(padx=5, pady=5, fill=X)
        lst = ['Outside Temperature:', 'Inside Temperature:',
               'Driver Temperature Setting:', 'Passenger Temperature Setting:',
               'Is Climate On:', 'Fan Speed:', 'Driver Seat Heater:',
               'Passenger Seat Heater:', 'Is Front Defroster On:',
               'Is Rear Defroster On:']
        for i, t in enumerate(lst):
            Label(group, text=t).grid(row=i // 2, column=i % 2 * 2, sticky=E)
        self.outside_temp = LabelVarGrid(group, row=0, column=1, sticky=W)
        self.inside_temp = LabelVarGrid(group, row=0, column=3, sticky=W)
        self.driver_temp = LabelVarGrid(group, row=1, column=1, sticky=W)
        self.passenger_temp = LabelVarGrid(group, row=1, column=3, sticky=W)
        self.is_climate_on = LabelVarGrid(group, row=2, column=1, sticky=W)
        self.fan_status = LabelVarGrid(group, row=2, column=3, sticky=W)
        self.driver_heater = LabelVarGrid(group, row=3, column=1, sticky=W)
        self.passenger_heater = LabelVarGrid(group, row=3, column=3, sticky=W)
        self.front_defroster = LabelVarGrid(group, row=4, column=1, sticky=W)
        self.rear_defroster = LabelVarGrid(group, row=4, column=3, sticky=W)
        # Vehicle state on left frame
        group = LabelFrame(left, text='Vehicle State', padx=5, pady=5)
        group.pack(padx=5, pady=5, fill=X)
        lst = ['Vehicle Name:', 'Odometer:', 'Car Version:', 'Locked:',
               'Driver Front Door:', 'Passenger Front Door:',
               'Driver Rear Door:', 'Passenger Rear Door:',
               'Driver Front Window:', 'Passenger Front Window:',
               'Driver Rear Window:', 'Passenger Rear Window:', 'Front Trunk:',
               'Rear Trunk:', 'Remote Start:', 'Is User Present:',
               'Speed Limit Mode:', 'Current Limit:', 'Speed Limit Pin Set:',
               'Sentry Mode:', 'Valet Mode:', 'Valet Pin Set:',
               'Software Update:', 'Expected Duration:', 'Update Version:',
               'Install Percentage:']
        for i, t in enumerate(lst):
            Label(group, text=t).grid(row=i // 2, column=i % 2 * 2, sticky=E)
        self.vehicle_name = LabelVarGrid(group, row=0, column=1, sticky=W)
        self.odometer = LabelVarGrid(group, row=0, column=3, sticky=W)
        self.car_version = LabelVarGrid(group, row=1, column=1, sticky=W)
        self.locked = LabelVarGrid(group, row=1, column=3, sticky=W)
        self.df = LabelVarGrid(group, row=2, column=1, sticky=W)
        self.pf = LabelVarGrid(group, row=2, column=3, sticky=W)
        self.dr = LabelVarGrid(group, row=3, column=1, sticky=W)
        self.pr = LabelVarGrid(group, row=3, column=3, sticky=W)
        self.fd = LabelVarGrid(group, row=4, column=1, sticky=W)
        self.fp = LabelVarGrid(group, row=4, column=3, sticky=W)
        self.rd = LabelVarGrid(group, row=5, column=1, sticky=W)
        self.rp = LabelVarGrid(group, row=5, column=3, sticky=W)
        self.ft = LabelVarGrid(group, row=6, column=1, sticky=W)
        self.rt = LabelVarGrid(group, row=6, column=3, sticky=W)
        self.remote_start = LabelVarGrid(group, row=7, column=1, sticky=W)
        self.user_present = LabelVarGrid(group, row=7, column=3, sticky=W)
        self.speed_limit = LabelVarGrid(group, row=8, column=1, sticky=W)
        self.current_limit = LabelVarGrid(group, row=8, column=3, sticky=W)
        self.speed_limit_pin = LabelVarGrid(group, row=9, column=1, sticky=W)
        self.sentry_mode = LabelVarGrid(group, row=9, column=3, sticky=W)
        self.valet_mode = LabelVarGrid(group, row=10, column=1, sticky=W)
        self.valet_pin = LabelVarGrid(group, row=10, column=3, sticky=W)
        self.sw_update = LabelVarGrid(group, row=11, column=1, sticky=W)
        self.sw_duration = LabelVarGrid(group, row=11, column=3, sticky=W)
        self.update_ver = LabelVarGrid(group, row=12, column=1, sticky=W)
        self.inst_perc = LabelVarGrid(group, row=12, column=3, sticky=W)
        # Drive state on right frame
        group = LabelFrame(right, text='Drive State', padx=5, pady=5)
        group.pack(padx=5, pady=5, fill=X)
        lst = ['Power:', 'Speed:', 'Shift State:', 'Heading:', 'GPS:']
        for i, t in enumerate(lst):
            Label(group, text=t).grid(row=i // 2, column=i % 2 * 2, sticky=E)
        self.power = LabelVarGrid(group, row=0, column=1, sticky=W)
        self.speed = LabelVarGrid(group, row=0, column=3, sticky=W)
        self.shift_state = LabelVarGrid(group, row=1, column=1, sticky=W)
        self.heading = LabelVarGrid(group, row=1, column=3, sticky=W)
        self.gps = LabelVarGrid(group, row=2, column=1, columnspan=3, sticky=W)
        self.gps.config(wraplength=330, justify=LEFT)
        # Charging state on right frame
        group = LabelFrame(right, text='Charging State', padx=5, pady=5)
        group.pack(padx=5, pady=5, fill=X)
        lst = ['Charging State:', 'Time To Full Charge:', 'Charger Voltage:',
               'Charger Actual Current:', 'Charger Power:', 'Charge Rate:',
               'Battery Level:', 'Battery Range:', 'Charge Energy Added:',
               'Charge Range Added:', 'Charge Limit SOC:',
               'Estimated Battery Range:', 'Charge Port Door Open:',
               'Charge Port Latch:', 'Fast Charger:', 'Trip Charging:',
               'Scheduled Charging:', 'Charging Start Time:']
        for i, t in enumerate(lst):
            Label(group, text=t).grid(row=i // 2, column=i % 2 * 2, sticky=E)
        self.charging_state = LabelVarGrid(group, row=0, column=1, sticky=W)
        self.time_to_full = LabelVarGrid(group, row=0, column=3, sticky=W)
        self.charger_voltage = LabelVarGrid(group, row=1, column=1, sticky=W)
        self.charger_current = LabelVarGrid(group, row=1, column=3, sticky=W)
        self.charger_power = LabelVarGrid(group, row=2, column=1, sticky=W)
        self.charge_rate = LabelVarGrid(group, row=2, column=3, sticky=W)
        self.battery_level = LabelVarGrid(group, row=3, column=1, sticky=W)
        self.battery_range = LabelVarGrid(group, row=3, column=3, sticky=W)
        self.energy_added = LabelVarGrid(group, row=4, column=1, sticky=W)
        self.range_added = LabelVarGrid(group, row=4, column=3, sticky=W)
        self.charge_limit_soc = LabelVarGrid(group, row=5, column=1, sticky=W)
        self.est_battery_range = LabelVarGrid(group, row=5, column=3, sticky=W)
        self.charge_port_door = LabelVarGrid(group, row=6, column=1, sticky=W)
        self.charge_port_latch = LabelVarGrid(group, row=6, column=3, sticky=W)
        self.fast_charger = LabelVarGrid(group, row=7, column=1, sticky=W)
        self.trip_charging = LabelVarGrid(group, row=7, column=3, sticky=W)
        self.charging_pending = LabelVarGrid(group, row=8, column=1, sticky=W)
        self.charging_start = LabelVarGrid(group, row=8, column=3, sticky=W)
        # Vehicle config on left frame
        group = LabelFrame(left, text='Vehicle Config', padx=5, pady=5)
        group.pack(padx=5, pady=5, fill=X)
        lst = ['Car Type:', 'Exterior Color:', 'Wheel Type:', 'Spoiler Type:',
               'Roof Color:', 'Charge Port Type:']
        for i, t in enumerate(lst):
            Label(group, text=t).grid(row=i // 2, column=i % 2 * 2, sticky=E)
        self.car_type = LabelVarGrid(group, row=0, column=1, sticky=W)
        self.exterior_color = LabelVarGrid(group, row=0, column=3, sticky=W)
        self.wheel_type = LabelVarGrid(group, row=1, column=1, sticky=W)
        self.spoiler_type = LabelVarGrid(group, row=1, column=3, sticky=W)
        self.roof_color = LabelVarGrid(group, row=2, column=1, sticky=W)
        self.charge_port_type = LabelVarGrid(group, row=2, column=3, sticky=W)

    def update_widgets(self):
        cl = app.vehicle['climate_state']
        ve = app.vehicle['vehicle_state']
        dr = app.vehicle['drive_state']
        ch = app.vehicle['charge_state']
        co = app.vehicle['vehicle_config']
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
        self.ft.text(door[ve['ft']])
        self.rt.text(door[ve['rt']])
        self.remote_start.text(str(ve['remote_start']))
        self.user_present.text(str(ve['is_user_present']))
        self.speed_limit.text(str(ve['speed_limit_mode']['active']))
        limit = ve['speed_limit_mode']['current_limit_mph']
        self.current_limit.text(app.vehicle.dist_units(limit, True))
        self.speed_limit_pin.text(str(ve['speed_limit_mode']['pin_code_set']))
        self.sentry_mode.text(str(ve['sentry_mode']))
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
        self.gps.text(app.update_thread.location.address)
        # Charging state
        self.charging_state.text(ch['charging_state'])
        ttfc = divmod(ch['time_to_full_charge'] * 60, 60)
        self.time_to_full.text('{:02.0f}:{:02.0f}'.format(*ttfc))
        volt = 0 if ch['charger_voltage'] is None else ch['charger_voltage']
        self.charger_voltage.text('%d V' % volt)
        ph = '3 x ' if ch['charger_phases'] == 2 else ''
        amps = 0 if ch['charger_actual_current'] is None else ch['charger_actual_current']
        self.charger_current.text('%s%d A' % (ph, amps))
        charger_power = 0 if ch['charger_power'] is None else ch['charger_power']
        self.charger_power.text('%d kW' % charger_power)
        self.charge_rate.text(app.vehicle.dist_units(ch['charge_rate'], True))
        if ch['usable_battery_level'] < ch['battery_level']:
            usable = ' (%d %% usable)' % ch['usable_battery_level']
        else:
            usable = ''
        self.battery_level.text('%d %%%s' % (ch['battery_level'], usable))
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
        # Vehicle config
        self.car_type.text(co['car_type'])
        self.exterior_color.text(co['exterior_color'])
        self.wheel_type.text(co['wheel_type'])
        self.spoiler_type.text(co['spoiler_type'])
        self.roof_color.text(co['roof_color'])
        self.charge_port_type.text(co['charge_port_type'])

    @staticmethod
    def _heading_to_str(deg):
        lst = ['NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW',
               'WSW', 'W', 'WNW', 'NW', 'NNW', 'N']
        return lst[int(abs((deg - 11.25) % 360) / 22.5)]

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
        app_menu.add_separator()
        app_menu.add_command(label='Exit', command=self.save_and_quit)
        menu.add_cascade(label='App', menu=app_menu)
        self.vehicle_menu = Menu(menu, tearoff=0)
        self.vehicle_menu.add_command(label='Show option codes', state=DISABLED,
                                      command=self.option_codes)
        self.vehicle_menu.add_command(label='Decode VIN', state=DISABLED,
                                      command=self.decode_vin)
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
                                  command=self.remote_start_drive)
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
        menu.add_cascade(label='Command', menu=self.cmd_menu)
        display_menu = Menu(menu, tearoff=0)
        self.auto_refresh = BooleanVar()
        display_menu.add_checkbutton(label='Auto refresh',
                                     variable=self.auto_refresh,
                                     command=self.update_dashboard)
        self.debug = BooleanVar()
        display_menu.add_checkbutton(label='Console debugging',
                                     variable=self.debug, command=self.set_log)
        menu.add_cascade(label='Display', menu=display_menu)
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
        try:
            config.read('gui.ini')
            self.email = config.get('app', 'email')
            self.auto_refresh.set(config.get('display', 'auto_refresh'))
            self.debug.set(config.get('display', 'debug'))
        except (NoSectionError, NoOptionError, ParsingError):
            pass
        # Initialize logging
        logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s')
        self.set_log()

    def add_cmd_args(self, endpoint):
        """ Return add_command arguments for given named endpoint """
        return {'label': endpoint.capitalize().replace('_', ' '),
                'state': DISABLED, 'command': lambda: self.cmd(endpoint)}

    def get_passcode(self):
        """ Ask user for passcode string in new dialog """
        def show_dialog():
            """ Inner function to use simpledialog from non-main thread """
            global passcode
            root = Tk()
            root.withdraw()
            passcode = askstring('Tesla', 'Passcode:', parent=root)
            root.destroy()
        self.after_idle(show_dialog)  # Start from main thread
        while passcode is None:
            time.sleep(0.1)  # Block current thread until passcode is entered
        return passcode

    def login(self):
        """ Display login dialog and start new thread to get vehicle list """
        dlg = LoginDialog(self)
        if dlg.result:
            self.email, self.password = dlg.result
            self.status.text('Logging in...')
            tesla = teslapy.Tesla(self.email, self.password, self.get_passcode)
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
            self.vehicle_menu.delete(3, END)
            # Add to menu and select first vehicle
            self.selected = IntVar(value=0)
            for i, vehicle in enumerate(self.login_thread.vehicles):
                label = '%s (%s)' % (vehicle['display_name'], vehicle['vin'])
                self.vehicle_menu.add_radiobutton(label=label, value=i,
                                                  variable=self.selected,
                                                  command=self.select)
            if self.login_thread.vehicles:
                # Enable show option codes and wake up command
                for i in range(0, 2):
                    self.vehicle_menu.entryconfig(i, state=NORMAL)
                self.cmd_menu.entryconfig(0, state=NORMAL)
                self.select()
            else:
                self.status.text('No vehicles')

    def select(self):
        """ Select vehicle and start new thread to get vehicle image """
        self.vehicle = self.login_thread.vehicles[self.selected.get()]
        # Create and start image thread. Check thread status after 100 ms
        self.image_thread = ImageThread(self.vehicle)
        self.image_thread.start()
        self.after(100, self.process_select)
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

    def show_status(self):
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
        LabelGridDialog(self, 'About',
                        [{'text': 'Tesla Owner API Python GUI by Tim Dorssers'},
                         {'text': 'Tcl/Tk toolkit version %s' % TkVersion}])

    def option_codes(self):
        table = []
        for i, item in enumerate(self.vehicle.option_code_list()):
            table.append(dict(text=item, row=i // 2, column=i % 2, sticky=W))
        LabelGridDialog(self, 'Option codes', table)

    def decode_vin(self):
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
        if self.vehicle['vehicle_state']['locked']:
            self.cmd('UNLOCK')
        else:
            self.cmd('LOCK')

    def climate_on_off(self):
        if self.vehicle['climate_state']['is_climate_on']:
            self.cmd('CLIMATE_OFF')
        else:
            self.cmd('CLIMATE_ON')

    def set_temperature(self):
        # Get user input using a simple dialog box
        temp = askfloat('Set', 'Temperature')
        if temp:
            self.cmd('CHANGE_CLIMATE_TEMPERATURE_SETTING', driver_temp=temp,
                     passenger_temp=temp)

    def actuate_trunk(self, which_trunk):
        self.cmd('ACTUATE_TRUNK', which_trunk=which_trunk)

    def remote_start_drive(self):
        if self.password:
            self.cmd('REMOTE_START', password=self.password)
        else:
            self.status.text('Password required')

    def set_charge_limit(self):
        limit = askinteger('Set', 'Charge Limit')
        if limit:
            self.cmd('CHANGE_CHARGE_LIMIT', percent=limit)

    def open_close_charge_port(self):
        if self.vehicle['charge_state']['charge_port_door_open']:
            self.cmd('CHARGE_PORT_DOOR_CLOSE')
        else:
            self.cmd('CHARGE_PORT_DOOR_OPEN')

    def start_stop_charge(self):
        if self.vehicle['charge_state']['charging_state'].lower() == 'charging':
            self.cmd('STOP_CHARGE')
        else:
            self.cmd('START_CHARGE')

    def seat_heater(self):
        dlg = SeatHeaterDialog(self)
        if dlg.result:
            self.cmd('REMOTE_SEAT_HEATER_REQUEST', heater=dlg.result[0],
                     level=dlg.result[1])

    def vent_close_sun_roof(self):
        dlg = ControlDialog(self, 'Sun Roof')
        if dlg.result:
            self.cmd('CHANGE_SUNROOF_STATE', state=dlg.result)

    def schedule_sw_update(self):
        self.cmd('SCHEDULE_SOFTWARE_UPDATE', offset_sec=120)

    def window_control(self):
        dlg = ControlDialog(self, 'Windows')
        if dlg.result:
            self.cmd('WINDOW_CONTROL', command=dlg.result, lat=0, lon=0)

    def max_defrost(self):
        try:
            if self.vehicle['climate_state']['defrost_mode']:
                self.cmd('MAX_DEFROST', on=False)
            else:
                self.cmd('MAX_DEFROST', on=True)
        except KeyError:
            pass

    def set_log(self):
        level = logging.DEBUG if self.debug.get() else logging.WARNING
        logging.getLogger().setLevel(level)

    def save_and_quit(self):
        config = RawConfigParser()
        config.add_section('app')
        config.add_section('display')
        if hasattr(self, 'email'):
            config.set('app', 'email', self.email)
        try:
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
                    osm = Nominatim(user_agent='TeslaPy')
                    self.location = osm.reverse(coords)
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

    def __init__(self, tesla):
        threading.Thread.__init__(self)
        self.tesla = tesla
        self.exception = None
        self.vehicles = None

    def run(self):
        try:
            self.tesla.fetch_token()
            self.vehicles = self.tesla.vehicle_list()
        except (teslapy.RequestException, ValueError) as e:
            self.exception = e

class StatusThread(threading.Thread):

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

if __name__ == "__main__":
    app = App()
    app.mainloop()
    app.destroy()
