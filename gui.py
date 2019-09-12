""" Tesla API GUI application using TeslaPy module """

# Author: Tim Dorssers

from __future__ import print_function
from geopy.geocoders import Nominatim
from geopy.exc import *
try:
    from Tkinter import *
    from tkSimpleDialog import *
except ImportError:
    from tkinter import *
    from tkinter.simpledialog import *
import time
import teslapy
import threading

CLIENT_ID='e4a9949fcfa04068f59abb5a658f2bac0a3428e4652315490b659d5ab3f35a9e'
CLIENT_SECRET='c75f14bbadc8bee3a7594412c31416f8300256d7668ea7e6e7f06727bfb9d220'

class LoginDialog(Dialog):
    """ Display dialog box to enter email and password """

    def __init__(self, master):
        Dialog.__init__(self, master, title='Login')

    def body(self, master):
        Label(master, text="Email:").grid(row=0, sticky=W)
        Label(master, text="Password:").grid(row=1, sticky=W)
        self.email = Entry(master)
        self.email.grid(row=0, column=1)
        self.password = Entry(master, show='*')
        self.password.grid(row=1, column=1)
        return self.email

    def apply(self):
        self.result = (self.email.get(), self.password.get())

class LabelGridDialog(Dialog):
    """ Display dialog box with label table and single button """

    def __init__(self, master, title=None, table=[]):
        self.table = table
        # The Dialog constructor must be called last
        Dialog.__init__(self, master, title)

    def body(self, master):
        for label in self.table:
            if isinstance(label, dict):
                Label(master, text=label.pop('text')).grid(label)
            else:
                Label(master, text=label).grid()

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

class SunRoofDialog(Dialog):
    """ Display dialog box with radio buttons to select sun roof state """

    def __init__(self, master):
        Dialog.__init__(self, master, title='Sun Roof')

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
    """ Label widget with textvariable and grid positioning """

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
        lst =['Vehicle Name:', 'Odometer:', 'Car Version:', 'Locked:',
              'Driver Front Door:', 'Passenger Front Door:',
              'Driver Rear Door:', 'Passenger Rear Door:', 'Front Trunk:',
              'Rear Trunk:', 'Remote Start:', 'Sun Roof Percent Open:',
              'Speed Limit Mode:', 'Current Limit:', 'Speed Limit Pin Set:',
              'Sentry Mode:', 'Valet Mode:', 'Valet Pin Set:']
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
        self.ft = LabelVarGrid(group, row=4, column=1, sticky=W)
        self.rt = LabelVarGrid(group, row=4, column=3, sticky=W)
        self.remote_start = LabelVarGrid(group, row=5, column=1, sticky=W)
        self.sun_roof = LabelVarGrid(group, row=5, column=3, sticky=W)
        self.speed_limit = LabelVarGrid(group, row=6, column=1, sticky=W)
        self.current_limit = LabelVarGrid(group, row=6, column=3, sticky=W)
        self.speed_limit_pin = LabelVarGrid(group, row=7, column=1, sticky=W)
        self.sentry_mode = LabelVarGrid(group, row=7, column=3, sticky=W)
        self.valet_mode = LabelVarGrid(group, row=8, column=1, sticky=W)
        self.valet_pin = LabelVarGrid(group, row=8, column=3, sticky=W)
        # Drive state on right frame
        group = LabelFrame(right, text='Drive State', padx=5, pady=5)
        group.pack(padx=5, pady=5, fill=X)
        lst =['Power:', 'Speed:', 'Shift State:', 'Heading:', 'GPS:']
        for i, t in enumerate(lst):
            Label(group, text=t).grid(row=i // 2, column=i % 2 * 2, sticky=E)
        self.power = LabelVarGrid(group, row=0, column=1, sticky=W)
        self.speed = LabelVarGrid(group, row=0, column=3, sticky=W)
        self.shift_state = LabelVarGrid(group, row=1, column=1, sticky=W)
        self.heading= LabelVarGrid(group, row=1, column=3, sticky=W)
        self.gps = LabelVarGrid(group, row=2, column=1, columnspan=3, sticky=W)
        self.gps.config(wraplength=350, justify=LEFT)
        # Charging state on right frame
        group = LabelFrame(right, text='Charging State', padx=5, pady=5)
        group.pack(padx=5, pady=5, fill=X)
        lst = ['Charging State:', 'Time To Full Charge:', 'Charger Voltage:',
               'Charger Actual Current:', 'Charger Power:', 'Charge Rate:',
               'Battery Level:', 'Battery Range:', 'Charge Energy Added:',
               'Charge Range Added:', 'Charge Limit SOC:',
               'Estimated Battery Range:', 'Charge Port Door Open:',
               'Charge Port Latch:']
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
        # Vehicle config on left frame
        group = LabelFrame(left, text='Vehicle Config', padx=5, pady=5)
        group.pack(padx=5, pady=5, fill=X)
        lst = ['Car Type:', 'Exterior Color:', 'Wheel Type:', 'Spoiler Type:',
               'Roof Color:', 'Charge Port Type:']
        for i, t in enumerate(lst):
            Label(group, text=t).grid(row=i // 2, column=i % 2 * 2, sticky=E)
        self.car_type = LabelVarGrid(group, row=0, column=1, sticky=W)
        self.exterior_color= LabelVarGrid(group, row=0, column=3, sticky=W)
        self.wheel_type = LabelVarGrid(group, row=1, column=1, sticky=W)
        self.spoiler_type = LabelVarGrid(group, row=1, column=3, sticky=W)
        self.roof_color = LabelVarGrid(group, row=2, column=1, sticky=W)
        self.charge_port_type = LabelVarGrid(group, row=2, column=3, sticky=W)
        
    def update_widgets(self, app):
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
        self.df.text(door[ve['df']])
        self.pf.text(door[ve['pf']])
        self.dr.text(door[ve['dr']])
        self.pr.text(door[ve['pr']])
        self.ft.text(door[ve['ft']])
        self.rt.text(door[ve['rt']])
        self.remote_start.text(str(ve['remote_start']))
        self.sun_roof.text(ve['sun_roof_percent_open'])
        self.speed_limit.text(str(ve['speed_limit_mode']['active']))
        limit = ve['speed_limit_mode']['current_limit_mph']
        self.current_limit.text(app.vehicle.dist_units(limit, True))
        self.speed_limit_pin.text(str(ve['speed_limit_mode']['pin_code_set']))
        self.sentry_mode.text(str(ve['sentry_mode']))
        self.valet_mode.text(str(ve['valet_mode']))
        self.valet_pin.text(str(not 'valet_pin_needed' in ve))
        # Drive state
        self.power.text('%d kW' % dr['power'])
        speed = 0 if dr['speed'] is None else dr['speed']
        self.speed.text(app.vehicle.dist_units(speed, True))
        self.shift_state.text(str(dr['shift_state']))
        self.heading.text(self._heading_to_str(dr['heading']))
        self.gps.text(app.update_thread.location)
        # Charging state
        self.charging_state.text(ch['charging_state'])
        ttfc = divmod(ch['time_to_full_charge'] * 60, 60)
        self.time_to_full.text('{:02.0f}:{:02.0f}'.format(*ttfc))
        self.charger_voltage.text('%d V' % ch['charger_voltage'])
        ph = '3 x ' if ch['charger_phases'] == 2 else ''
        self.charger_current.text('%s%d A' % (ph, ch['charger_actual_current']))
        self.charger_power.text('%d kW' % ch['charger_power'])
        self.charge_rate.text(app.vehicle.dist_units(ch['charge_rate'], True))
        self.battery_level.text('%d %%' % ch['battery_level'])
        self.battery_range.text(app.vehicle.dist_units(ch['battery_range']))
        self.energy_added.text('%.1f kWh' % ch['charge_energy_added'])
        self.range_added.text(app.vehicle.dist_units(ch['charge_miles_added_ideal']))
        self.charge_limit_soc.text('%d %%' % ch['charge_limit_soc'])
        self.est_battery_range.text(app.vehicle.dist_units(ch['est_battery_range']))
        self.charge_port_door.text(str(ch['charge_port_door_open']))
        self.charge_port_latch.text(str(ch['charge_port_latch']))
        # Vehicle config
        self.car_type.text(co['car_type'])
        self.exterior_color.text(co['exterior_color'])
        self.wheel_type.text(co['wheel_type'])
        self.spoiler_type.text(co['spoiler_type'])
        self.roof_color.text(co['roof_color'])
        self.charge_port_type.text(co['charge_port_type'])

    def _heading_to_str(self, deg):
        lst = ['NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW',
               'WSW', 'W', 'WNW', 'NW', 'NNW', 'N']
        return lst[int(abs((deg - 11.25) % 360) / 22.5)]

class App(Tk):
    """ Main application class """

    def __init__(self, **kwargs):
        Tk.__init__(self, **kwargs)
        self.title('Tesla')
        self.protocol('WM_DELETE_WINDOW', self.quit)
        # Add menu bar
        menu = Menu(self)
        app_menu = Menu(menu, tearoff=0)
        app_menu.add_command(label='Login', command=self.login)
        app_menu.add_separator()
        app_menu.add_command(label='Exit', command=self.quit)
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
        self.cmd_menu.add_command(label='Honk horn', state=DISABLED,
                                  command=lambda: self.api('HONK_HORN'))
        self.cmd_menu.add_command(label='Flash lights', state=DISABLED,
                                  command=lambda: self.api('FLASH_LIGHTS'))
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
        self.cmd_menu.add_command(label='Vent/close sun roof', state=DISABLED,
                                  command=self.vent_close_sun_roof)
        menu.add_cascade(label='Command', menu=self.cmd_menu)
        display_menu = Menu(menu, tearoff=0)
        self.auto_refresh = BooleanVar()
        display_menu.add_checkbutton(label='Auto refresh',
                                     variable=self.auto_refresh,
                                     command=self.update_dashboard)
        menu.add_cascade(label='Display', menu=display_menu)
        help_menu = Menu(menu, tearoff=0)
        help_menu.add_command(label='About', command=self.about)
        menu.add_cascade(label='Help', menu=help_menu)
        self.config(menu=menu)
        # Add widgets
        self.dashboard = Dashboard(self)
        self.dashboard.pack(pady=5, fill=X)
        self.status = StatusBar(self)
        self.status.pack(side=BOTTOM, fill=X)
        self.status.text('Not logged in')

    def login(self):
        """ Display login dialog and start new thread to get vehicle list """
        dlg = LoginDialog(self)
        if dlg.result:
            self.email, self.password = dlg.result
            self.status.text('Logging in...')
            tesla = teslapy.Tesla(self.email, self.password, CLIENT_ID, CLIENT_SECRET)
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
            if len(self.login_thread.vehicles):
                # Enable show option codes and wake up command
                for i in range(0, 2):
                    self.vehicle_menu.entryconfig(i, state=NORMAL)
                self.cmd_menu.entryconfig(0, state=NORMAL)
                self.select()

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

    def update_status(self):
        """ Creates a new thread to get vehicle summary """
        self.status_thread = StatusThread(self.vehicle)
        self.status_thread.start()
        self.after(100, self.process_status)

    def process_status(self):
        """ Waits for thread to finish and updates status """
        if self.status_thread.is_alive():
            self.after(100, self.process_status)
        else:
            # Reduce status polling rate if vehicle is not online
            delay = 60000 if self.vehicle['state'] == 'online' else 240000
            # Run thread again and show status
            self.after(delay, self.update_status)
            if self.status_thread.exception:
                self.status.text(self.status_thread.exception)
            else:
                self.show_status()

    def update_dashboard(self):
        """ Create new thread to get vehicle data """
        # Make sure only one instance is running
        if hasattr(self, 'update_thread') and self.update_thread.is_alive():
            return
        if hasattr(self, 'vehicle'):
            self.show_status()
            if self.vehicle['state'] == 'online':
                self.update_thread = UpdateThread(self.vehicle)
                self.update_thread.start()
                self.after(100, self.process_update_dashboard)

    def process_update_dashboard(self):
        """ Waits for thread to finish and updates dashboard data """
        if self.update_thread.is_alive():
            self.after(100, self.process_update_dashboard)
        else:
            delay = 4000  # Default update polling rate
            if self.update_thread.exception:
                self.status.text(self.update_thread.exception)
                self.status.indicator('red')
            else:
                # Show time stamp
                timestamp_ms = self.vehicle['vehicle_state']['timestamp']
                self.status.status(time.ctime(timestamp_ms / 1000))
                self.status.indicator('green')
                # Update dashboard with new vehicle data
                self.dashboard.update_widgets(self)
                # Increase polling rate if charging or user present
                if (self.vehicle['charge_state']['charging_state'] == 'Charging'
                    or self.vehicle['vehicle_state']['is_user_present']):
                        delay = 1000
            # Run again if fail threshold is not exceeded and auto refresh is on
            if self.auto_refresh.get() and self.update_thread.fail_cnt < 10:
                self.after(delay, self.update_dashboard)
            else:
                self.auto_refresh.set(FALSE)
                self.status.indicator(None)

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
                        ['Tesla API Python GUI by Tim Dorssers',
                         'Tcl/Tk toolkit ' + str(TkVersion)])

    def option_codes(self):
        codes = self.vehicle.option_code_list()
        LabelGridDialog(self, 'Option codes',
                        [dict(text=opt, sticky=W) for opt in codes])

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

    def api(self, name, **kwargs):
        """ Creates a new thread to perform API call """
        self.status.text('Please wait...')
        self.api_thread = ApiThread(self.vehicle, name, **kwargs)
        self.api_thread.start()
        self.after(100, self.process_api)

    def process_api(self):
        """ Waits for thread to finish and update widgets """
        if self.api_thread.is_alive():
            self.after(100, self.process_api)
        elif self.api_thread.exception:
            self.status.text(self.api_thread.exception)
        else:
            # Update dashboard after 1 second if auto refresh is disabled
            if not self.auto_refresh.get():
                self.after(1000, self.update_dashboard)

    def lock_unlock(self):
        if self.vehicle['vehicle_state']['locked']:
            self.api('UNLOCK')
        else:
            self.api('LOCK')
                
    def climate_on_off(self):
        if self.vehicle['climate_state']['is_climate_on']:
            self.api('CLIMATE_OFF')
        else:
            self.api('CLIMATE_ON')

    def set_temperature(self):
        # Get user input using a simple dialog box
        temp = askfloat('Set', 'Temperature')
        if temp:
            self.api('CHANGE_CLIMATE_TEMPERATURE_SETTING', driver_temp=temp,
                     passenger_temp=temp)

    def actuate_trunk(self, which_trunk):
        self.api('ACTUATE_TRUNK', which_trunk=which_trunk)

    def remote_start_drive(self):
        self.api('REMOTE_START', password=self.password)

    def set_charge_limit(self):
        limit = askinteger('Set', 'Charge Limit')
        if limit:
            self.api('CHANGE_CHARGE_LIMIT', percent=limit)

    def open_close_charge_port(self):
        if self.vehicle['charge_state']['charge_port_door_open']:
            self.api('CHARGE_PORT_DOOR_CLOSE')
        else:
            self.api('CHARGE_PORT_DOOR_OPEN')

    def start_stop_charge(self):
        if self.vehicle['charge_state']['charging_state'].lower() == 'charging':
            self.api('STOP_CHARGE')
        else:
            self.api('START_CHARGE')

    def seat_heater(self):
        dlg = SeatHeaterDialog(self)
        if dlg.result:
            self.api('REMOTE_SEAT_HEATER_REQUEST', heater=dlg.result[0],
                     level=dlg.result[1])

    def vent_close_sun_roof(self):
        dlg = SunRoofDialog(self)
        if dlg.result:
            self.api('CHANGE_SUNROOF_STATE', state=dlg.result)

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
            # Increase class variable for consecutive errors
            UpdateThread.fail_cnt += 1
            self.exception = e
        else:
            UpdateThread.fail_cnt = 0
            coords = '%s, %s' % (self.vehicle['drive_state']['latitude'],
                                 self.vehicle['drive_state']['longitude'])
            # Have coordinates changed over previous instance?
            if self._coords != coords:
                # Set class variable to new coordinates
                UpdateThread._coords = coords
                # Fallback to coordinates if lookup fails
                self.location = coords
                try:
                    # Lookup address at coordinates
                    osm = Nominatim(user_agent='TeslaPy')
                    self.location = osm.reverse(coords)
                except GeocoderTimedOut:
                    pass
                except GeopyError as e:
                    self.exception = e
                finally:
                    # Save location in class variable
                    UpdateThread.location = self.location

class WakeUpThread(threading.Thread):

    def __init__(self, vehicle):
        threading.Thread.__init__(self)
        self.vehicle = vehicle
        self.exception = None

    def run(self):
        try:
            self.vehicle.sync_wake_up()
        except (teslapy.TimeoutError, teslapy.RequestException) as e:
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

class ApiThread(threading.Thread):

    def __init__(self, vehicle, name, **kwargs):
        threading.Thread.__init__(self)
        self.vehicle = vehicle
        self.name = name
        self.data = kwargs
        self.exception = None

    def run(self):
        try:
            self.vehicle.api(self.name, **self.data)
        except (teslapy.RequestException, ValueError) as e:
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
