from __future__ import print_function
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
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
    """ Display dialog to enter email and password """

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
    """ Display window with label table """

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
    """ Display dialog with comboboxes to select seat heaters """

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

class StatusBar(Frame):
    """ Status bar widget """

    def __init__(self, master, **kwargs):
        Frame.__init__(self, master, **kwargs)
        # Transient text messages on the left
        self.text_value = StringVar()
        self.left_label = Label(self, bd=1, relief=SUNKEN, anchor=W,
                                textvariable=self.text_value)
        self.left_label.pack(fill=X, side=LEFT, expand=1)
        # Permanent status indicator on the right
        self.status_value = StringVar()
        self.right_label = Label(self, bd=1, relief=SUNKEN, anchor=W,
                                textvariable=self.status_value)
        self.right_label.pack(fill=X, side=RIGHT, expand=1)

    def text(self, text):
        self.text_value.set(text)
        self.update_idletasks()

    def status(self, status):
        self.status_value.set(status)
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
        # Climate state
        group = LabelFrame(self, text='Climate State', padx=5, pady=5)
        group.pack(padx=10, pady=5, fill=X)
        Label(group, text='Outside Temperature:').grid(row=0, sticky=E)
        self.outside_temp = LabelVarGrid(group, row=0, column=1, sticky=W)
        Label(group, text='Inside Temperature:').grid(row=0, column=2, sticky=E)
        self.inside_temp = LabelVarGrid(group, row=0, column=3, sticky=W)
        Label(group, text='Driver Temperature Setting:').grid(row=1, sticky=E)
        self.driver_temp = LabelVarGrid(group, row=1, column=1, sticky=W)
        Label(group, text='Passenger Temperature Setting:').grid(row=1, column=2, sticky=E)
        self.passenger_temp = LabelVarGrid(group, row=1, column=3, sticky=W)
        Label(group, text='Is Climate On:').grid(row=2, sticky=E)
        self.is_climate_on = LabelVarGrid(group, row=2, column=1, sticky=W)
        Label(group, text='Fan Speed:').grid(row=2, column=2, sticky=E)
        self.fan_status = LabelVarGrid(group, row=2, column=3, sticky=W)
        Label(group, text='Driver Seat Heater:').grid(row=3, sticky=E)
        self.driver_heater = LabelVarGrid(group, row=3, column=1, sticky=W)
        Label(group, text='Passenger Seat Heater:').grid(row=3, column=2, sticky=E)
        self.passenger_heater = LabelVarGrid(group, row=3, column=3, sticky=W)
        # Vehicle state
        group = LabelFrame(self, text='Vehicle State', padx=5, pady=5)
        group.pack(padx=10, pady=5, fill=X)
        Label(group, text='Vehicle Name:').grid(row=0, sticky=E)
        self.vehicle_name = LabelVarGrid(group, row=0, column=1, sticky=W)
        Label(group, text='Odometer:').grid(row=0, column=2, sticky=E)
        self.odometer = LabelVarGrid(group, row=0, column=3, sticky=W)
        Label(group, text='Car Version:').grid(row=1, sticky=E)
        self.car_version = LabelVarGrid(group, row=1, column=1, sticky=W)
        Label(group, text='Locked:').grid(row=1, column=2, sticky=E)
        self.locked = LabelVarGrid(group, row=1, column=3, sticky=W)
        Label(group, text='Driver Front Door:').grid(row=2, sticky=E)
        self.df = LabelVarGrid(group, row=2, column=1, sticky=W)
        Label(group, text='Passenger Front Door:').grid(row=2, column=2, sticky=E)
        self.pf = LabelVarGrid(group, row=2, column=3, sticky=W)
        Label(group, text='Driver Rear Door:').grid(row=3, sticky=E)
        self.dr = LabelVarGrid(group, row=3, column=1, sticky=W)
        Label(group, text='Passenger Rear Door:').grid(row=3, column=2, sticky=E)
        self.pr = LabelVarGrid(group, row=3, column=3, sticky=W)
        Label(group, text='Front Trunk:').grid(row=4, sticky=E)
        self.ft = LabelVarGrid(group, row=4, column=1, sticky=W)
        Label(group, text='Rear Trunk:').grid(row=4, column=2, sticky=E)
        self.rt = LabelVarGrid(group, row=4, column=3, sticky=W)
        Label(group, text='Center Display State:').grid(row=5, sticky=E)
        self.center_display = LabelVarGrid(group, row=5, column=1, sticky=W)
        Label(group, text='Panaramic Roof State:').grid(row=5, column=2, sticky=E)
        self.sun_roof_state = LabelVarGrid(group, row=5, column=3, sticky=W)
        Label(group, text='Speed Limit Mode:').grid(row=6, sticky=E)
        self.speed_limit = LabelVarGrid(group, row=6, column=1, sticky=W)
        Label(group, text='Current Limit:').grid(row=6, column=2, sticky=E)
        self.current_limit = LabelVarGrid(group, row=6, column=3, sticky=W)
        Label(group, text='Speed Limit Pin Set:').grid(row=7, sticky=E)
        self.speed_limit_pin = LabelVarGrid(group, row=7, column=1, sticky=W)
        Label(group, text='Sentry Mode:').grid(row=7, column=2, sticky=E)
        self.sentry_mode = LabelVarGrid(group, row=7, column=3, sticky=W)
        Label(group, text='Valet Mode:').grid(row=8, sticky=E)
        self.valet_mode = LabelVarGrid(group, row=8, column=1, sticky=W)
        Label(group, text='Valet Pin Set:').grid(row=8, column=2, sticky=E)
        self.valet_pin = LabelVarGrid(group, row=8, column=3, sticky=W)
        Label(group, text='Remote Start Enabled:').grid(row=9, sticky=E)
        self.remote_start_ena = LabelVarGrid(group, row=9, column=1, sticky=W)
        Label(group, text='Remote Start:').grid(row=9, column=2, sticky=E)
        self.remote_start = LabelVarGrid(group, row=9, column=3, sticky=W)
        # Drive state
        group = LabelFrame(self, text='Drive State', padx=5, pady=5)
        group.pack(padx=10, pady=5, fill=X)
        Label(group, text='Power:').grid(row=0, sticky=E)
        self.power = LabelVarGrid(group, row=0, column=1, sticky=W)
        Label(group, text='Speed:').grid(row=0, column=2, sticky=E)
        self.speed = LabelVarGrid(group, row=0, column=3, sticky=W)
        Label(group, text='Shift State:').grid(row=1, sticky=E)
        self.shift_state = LabelVarGrid(group, row=1, column=1, sticky=W)
        Label(group, text='Heading:').grid(row=1, column=2, sticky=E)
        self.heading= LabelVarGrid(group, row=1, column=3, sticky=W)
        Label(group, text='GPS:').grid(row=2, sticky=E)
        self.gps = LabelVarGrid(group, row=2, column=1, columnspan=3, sticky=W)
        # Charging state
        group = LabelFrame(self, text='Charging State', padx=5, pady=5)
        group.pack(padx=10, pady=5, fill=X)
        Label(group, text='Charging State:').grid(row=0, sticky=E)
        self.charging_state = LabelVarGrid(group, row=0, column=1, sticky=W)
        Label(group, text='Time To Full Charge:').grid(row=0, column=2, sticky=E)
        self.time_to_full = LabelVarGrid(group, row=0, column=3, sticky=W)
        Label(group, text='Charger Voltage:').grid(row=1, sticky=E)
        self.charger_voltage = LabelVarGrid(group, row=1, column=1, sticky=W)
        Label(group, text='Charger Actual Current:').grid(row=1, column=2, sticky=E)
        self.charger_current = LabelVarGrid(group, row=1, column=3, sticky=W)
        Label(group, text='Charger Power:').grid(row=2, sticky=E)
        self.charger_power = LabelVarGrid(group, row=2, column=1, sticky=W)
        Label(group, text='Charge Rate:').grid(row=2, column=2, sticky=E)
        self.charge_rate = LabelVarGrid(group, row=2, column=3, sticky=W)
        Label(group, text='Battery Level:').grid(row=3, sticky=E)
        self.battery_level = LabelVarGrid(group, row=3, column=1, sticky=W)
        Label(group, text='Battery Range:').grid(row=3, column=2, sticky=E)
        self.battery_range = LabelVarGrid(group, row=3, column=3, sticky=W)
        Label(group, text='Charge Energy Added:').grid(row=4, sticky=E)
        self.energy_added = LabelVarGrid(group, row=4, column=1, sticky=W)
        Label(group, text='Charge Range Added:').grid(row=4, column=2, sticky=E)
        self.range_added = LabelVarGrid(group, row=4, column=3, sticky=W)
        Label(group, text='Charge Limit SOC:').grid(row=5, sticky=E)
        self.charge_limit_soc = LabelVarGrid(group, row=5, column=1, sticky=W)
        Label(group, text='Estimated Battery Range:').grid(row=5, column=2, sticky=E)
        self.est_battery_range = LabelVarGrid(group, row=5, column=3, sticky=W)
        Label(group, text='Charge Port Door Open:').grid(row=6, sticky=E)
        self.charge_port_door = LabelVarGrid(group, row=6, column=1, sticky=W)
        Label(group, text='Charge Port Latch:').grid(row=6, column=2, sticky=E)
        self.charge_port_latch = LabelVarGrid(group, row=6, column=3, sticky=W)
        # Vehicle config
        group = LabelFrame(self, text='Vehicle Config', padx=5, pady=5)
        group.pack(padx=10, pady=5, fill=X)
        Label(group, text='Car Type:').grid(row=0, sticky=E)
        self.car_type = LabelVarGrid(group, row=0, column=1, sticky=W)
        Label(group, text='Exterior Color:').grid(row=0, column=2, sticky=E)
        self.exterior_color= LabelVarGrid(group, row=0, column=3, sticky=W)
        Label(group, text='Wheel Type:').grid(row=1, sticky=E)
        self.wheel_type = LabelVarGrid(group, row=1, column=1, sticky=W)
        Label(group, text='Spoiler Type:').grid(row=1, column=2, sticky=E)
        self.spoiler_type = LabelVarGrid(group, row=1, column=3, sticky=W)
        Label(group, text='Roof Color:').grid(row=2, sticky=E)
        self.roof_color = LabelVarGrid(group, row=2, column=1, sticky=W)
        Label(group, text='Charge Port Type:').grid(row=2, column=2, sticky=E)
        self.charge_port_type = LabelVarGrid(group, row=2, column=3, sticky=W)
        
    def update_widgets(self, app):
        cl = app.vehicle['climate_state']
        ve = app.vehicle['vehicle_state']
        dr = app.vehicle['drive_state']
        ch = app.vehicle['charge_state']
        co = app.vehicle['vehicle_config']
        # Climate state
        self.outside_temp.text('%.1f C' % cl['outside_temp'])
        self.inside_temp.text('%.1f C' % cl['inside_temp'])
        self.driver_temp.text('%.1f C' % cl['driver_temp_setting'])
        self.passenger_temp.text('%.1f C' % cl['passenger_temp_setting'])
        self.is_climate_on.text(str(cl['is_climate_on']))
        self.fan_status.text(cl['fan_status'])
        self.driver_heater.text(cl['seat_heater_left'])
        self.passenger_heater.text(cl['seat_heater_right'])
        # Vehicle state
        self.vehicle_name.text(ve['vehicle_name'])
        self.odometer.text('%.1f km' % (ve['odometer'] / 0.62137119))
        self.car_version.text(ve['car_version'])
        self.locked.text(str(ve['locked']))
        door = ['Closed', 'Open']
        self.df.text(door[ve['df']])
        self.pf.text(door[ve['pf']])
        self.dr.text(door[ve['dr']])
        self.pr.text(door[ve['pr']])
        self.ft.text(door[ve['ft']])
        self.rt.text(door[ve['rt']])
        self.center_display.text('On' if ve['center_display_state'] else 'Off')
        self.sun_roof_state.text(ve['sun_roof_state'])
        self.speed_limit.text(str(ve['speed_limit_mode']['active']))
        limit = ve['speed_limit_mode']['current_limit_mph'] / 0.62137119
        self.current_limit.text('%.1f km/h' % limit)
        self.speed_limit_pin.text(str(ve['speed_limit_mode']['pin_code_set']))
        self.sentry_mode.text(str(ve['sentry_mode']))
        self.valet_mode.text(str(ve['valet_mode']))
        self.valet_pin.text(str(not 'valet_pin_needed' in ve))
        self.remote_start_ena.text(str(ve['remote_start_enabled']))
        self.remote_start.text(str(ve['remote_start']))
        # Drive state
        self.power.text('%d kW' % dr['power'])
        speed = 0 if dr['speed'] is None else dr['speed'] / 0.62137119
        self.speed.text('%.1f km/h' % speed)
        self.shift_state.text(str(dr['shift_state']))
        self.heading.text(self._heading_to_str(dr['heading']))
        if app.update_thread.location is None:
            self.gps.text('%s, %s' % (dr['latitude'], dr['longitude']))
        else:
            self.gps.text(app.update_thread.location)
        # Charging state
        self.charging_state.text(ch['charging_state'])
        ttfc = divmod(ch['time_to_full_charge'] * 60, 60)
        self.time_to_full.text('{:02.0f}:{:02.0f}'.format(*ttfc))
        self.charger_voltage.text('%d V' % ch['charger_voltage'])
        ph = '3 x ' if ch['charger_phases'] == 2 else ''
        self.charger_current.text('%s%d A' % (ph, ch['charger_actual_current']))
        self.charger_power.text('%d kW' % ch['charger_power'])
        self.charge_rate.text('%.1f km/h' % (ch['charge_rate'] / 0.62137119))
        self.battery_level.text('%d %%' % ch['battery_level'])
        self.battery_range.text('%.1f km' % (ch['battery_range'] / 0.62137119))
        self.energy_added.text('%.1f kWh' % ch['charge_energy_added'])
        self.range_added.text('%.1f km' % (ch['charge_miles_added_ideal']
                                           / 0.62137119))
        self.charge_limit_soc.text('%d %%' % ch['charge_limit_soc'])
        self.est_battery_range.text('%.1f km' % (ch['est_battery_range']
                                                 / 0.62137119))
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
        self.cmd_menu.add_command(label='Charge port open/close', state=DISABLED,
                                  command=self.charge_port_open_close)
        self.cmd_menu.add_command(label='Start/stop charge', state=DISABLED,
                                  command=self.start_stop_charge)
        self.cmd_menu.add_command(label='Seat heater request', state=DISABLED,
                                  command=self.seat_heater)
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
        dlg = LoginDialog(self)
        if dlg.result:
            self.email, self.password = dlg.result
            tesla = teslapy.Tesla(self.email, self.password, CLIENT_ID, CLIENT_SECRET)
            tesla.fetch_token()
            self.status.text('Fetching vehicles...')
            try:
                self.vehicles = tesla.vehicle_list()
            except teslapy.HTTPError as e:
                self.status.text(e.response.reason)
                return
            except ValueError as e:
                self.status.text(e)
                return
            # Remove vehicles from menu
            self.vehicle_menu.delete(2, END)
            # Add to menu and select first vehicle
            self.selected = IntVar(value=0)
            for i, vehicle in enumerate(self.vehicles):
                label = '%s (%s)' % (vehicle['display_name'], vehicle['vin'])
                self.vehicle_menu.add_radiobutton(label=label, value=i,
                                                  variable=self.selected,
                                                  command=self.select)
            if len(self.vehicles):
                # Enable show option codes and wake up command
                self.vehicle_menu.entryconfig(0, state=NORMAL)
                self.cmd_menu.entryconfig(0, state=NORMAL)
                self.select()

    def select(self):
        self.vehicle = self.vehicles[self.selected.get()]
        self.update_dashboard()

    def update_dashboard(self):
        """ Create new thread to get vehicle data """
        self.status.text('%s is %s' % (self.vehicle['display_name'],
                                       self.vehicle['state']))
        if self.vehicle['state'] == 'online':
            # Enable commands
            for i in range(1, self.cmd_menu.index(END) + 1):
                self.cmd_menu.entryconfig(i, state=NORMAL)
            # Create and start update thread
            self.update_thread = UpdateThread(self.vehicle)
            self.update_thread.start()
            # Check thread status after 100 ms
            self.after(100, self.process_update)

    def process_update(self):
        """ Waits for thread to finish and update dashboard """
        if self.update_thread.is_alive():
            # Check again after 100 ms
            self.after(100, self.process_update)
        else:
            # Handle errors
            if isinstance(self.update_thread.exception, teslapy.HTTPError):
                self.status.text(self.update_thread.exception.response.reason)
                self.auto_refresh.set(FALSE)
                return
            elif self.update_thread.exception is not None:
                self.status.text(self.update_thread.exception)
            # Show time stamp
            timestamp_ms = self.vehicle['vehicle_state']['timestamp']
            self.status.status(time.ctime(timestamp_ms / 1000))
            # Run update again afer 1 second if auto refresh is enabled
            if self.auto_refresh.get():
                self.after(1000, self.update_dashboard)
            # Update dashboard with new vehicle data
            self.dashboard.update_widgets(self)

    def wake_up(self):
        """ Creates a new thread to wake up vehicle """
        self.status.text('Please wait...')
        self.wake_up_thread = WakeUpThread(self.vehicle)
        self.wake_up_thread.start()
        self.after(100, self.process_wake_up)

    def process_wake_up(self):
        """ Waits for thread to finish and update dashboard """
        if self.wake_up_thread.is_alive():
            self.after(100, self.process_wake_up)
        elif self.wake_up_thread.exception is None:
            self.update_dashboard()
        elif isinstance(self.wake_up_thread.exception, teslapy.HTTPError):
            self.status.text(self.wake_up_thread.exception.response.reason)
        else:
            self.status.text(self.wake_up_thread.exception)

    def about(self):
        LabelGridDialog(self, 'About',
                        ['Tesla API Python GUI', 'by Tim Dorssers'])

    def option_codes(self):
        codes = self.vehicle.option_code_list()
        LabelGridDialog(self, 'Option codes',
                        [dict(text=opt, sticky=W) for opt in codes])

    def charging_sites(self):
        try:
            sites = self.vehicle.get_nearby_charging_sites()
        except teslapy.HTTPError as e:
            self.status.text(e.response.reason)
            return
        except ValueError as e:
            self.status.text(e)
            return
        table = [dict(text='Destination Charging:', columnspan=2)]
        r = 1
        for site in sites['destination_charging']:
            table.append(dict(text=site['name'], row=r, sticky=W))
            dist = site['distance_miles'] / 0.62137119
            table.append(dict(text='%.1f km' % dist, row=r, column=1, sticky=W))
            r += 1
        table.append(dict(text='Superchargers:', row=r, columnspan=2))
        r += 1
        for site in sites['superchargers']:
            table.append(dict(text=site['name'], row=r, sticky=W))
            dist = site['distance_miles'] / 0.62137119
            table.append(dict(text='%.1f km' % dist, row=r, column=1, sticky=W))
            text = '%d/%d free stalls' % (site['available_stalls'],
                                          site['total_stalls'])
            table.append(dict(text=text, row=r, column=2, sticky=W))
            r += 1
        LabelGridDialog(self, 'Nearby Charging Sites', table)

    def api(self, name, **kwargs):
        """ Wrapper around Vehicle.api() to catch exceptions """
        try:
            return self.vehicle.api(name, **kwargs)
        except teslapy.HTTPError as e:
            self.status.text(e.response.reason)
        except ValueError as e:
            self.status.text(e)

    def lock_unlock(self):
        if self.vehicle['vehicle_state']['locked']:
            self.api('UNLOCK')
        else:
            self.api('LOCK')
        # Update dashboard after 1 second if auto refresh is disabled
        if not self.auto_refresh.get():
            self.after(1000, self.update_dashboard)
                
    def climate_on_off(self):
        if self.vehicle['climate_state']['is_climate_on']:
            self.api('CLIMATE_OFF')
        else:
            self.api('CLIMATE_ON')
        if not self.auto_refresh.get():
            self.after(1000, self.update_dashboard)

    def set_temperature(self):
        # Get user input using a simple dialog box
        temp = askfloat('Set', 'Temperature')
        if temp:
            data = {'driver_temp': temp, 'passenger_temp': temp}
            self.api('CHANGE_CLIMATE_TEMPERATURE_SETTING', data=data)
            if not self.auto_refresh.get():
                self.after(1000, self.update_dashboard)

    def actuate_trunk(self, which_trunk):
        self.api('ACTUATE_TRUNK', data={'which_trunk': which_trunk})
        if not self.auto_refresh.get():
            self.after(1000, self.update_dashboard)

    def remote_start_drive(self):
        self.api('REMOTE_START', data={'password': self.password})
        if not self.auto_refresh.get():
            self.after(1000, self.update_dashboard)

    def set_charge_limit(self):
        limit = askinteger('Set', 'Charge Limit')
        if limit:
            self.api('CHANGE_CHARGE_LIMIT', data={'percent': limit})
            if not self.auto_refresh.get():
                self.after(1000, self.update_dashboard)

    def charge_port_open_close(self):
        if self.vehicle['charge_state']['charge_port_door_open']:
            self.api('CHARGE_PORT_DOOR_CLOSE')
        else:
            self.api('CHARGE_PORT_DOOR_OPEN')
        if not self.auto_refresh.get():
            self.after(1000, self.update_dashboard)

    def start_stop_charge(self):
        if self.vehicle['charge_state']['charging_state'].lower() == 'charging':
            self.api('STOP_CHARGE')
        else:
            self.api('START_CHARGE')
        if not self.auto_refresh.get():
            self.after(1000, self.update_dashboard)

    def seat_heater(self):
        dlg = SeatHeaterDialog(self)
        if dlg.result:
            data = {'heater': dlg.result[0], 'level': dlg.result[1]}
            self.api('REMOTE_SEAT_HEATER_REQUEST', data=data)
            if not self.auto_refresh.get():
                self.after(1000, self.update_dashboard)

class UpdateThread(threading.Thread):

    def __init__(self, vehicle):
        threading.Thread.__init__(self)
        self.vehicle = vehicle
        self.exception = None
        self.location = None

    def run(self):
        try:
            self.vehicle.get_vehicle_data()
        except teslapy.HTTPError as e:
            self.exception = e
        else:
            # Lookup address at coordinates
            coords = '%s, %s' % (self.vehicle['drive_state']['latitude'],
                                 self.vehicle['drive_state']['longitude'])
            try:
                osm = Nominatim(user_agent='test')
                self.location = osm.reverse(coords)
            except GeocoderTimedOut as e:
                self.exception = e

class WakeUpThread(threading.Thread):

    def __init__(self, vehicle):
        threading.Thread.__init__(self)
        self.vehicle = vehicle
        self.exception = None

    def run(self):
        try:
            self.vehicle.sync_wake_up()
        except (teslapy.TimeoutError, teslapy.HTTPError) as e:
            self.exception = e

if __name__ == "__main__":
    app = App()
    app.mainloop()
    app.destroy()
