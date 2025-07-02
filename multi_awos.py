#!/usr/bin/env python3
import csv
import tkinter as tk
from tkinter import ttk
import warnings
from PIL import Image, ImageTk
from pymodbus.client import ModbusSerialClient
import time
from datetime import datetime
import logging
import os
import queue
import threading
from collections import deque
import configparser
import math
import json
from logging.handlers import RotatingFileHandler
import sys
import pandas as pd

# Disable DecompressionBombWarning
Image.MAX_IMAGE_PIXELS = None
warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)

# Add path for awos_assit_code
sys.path.append(os.path.join(os.path.dirname(__file__), 'awos_assit_code'))

class DataManager:
    """Manages sensor data collection and distribution"""
    def __init__(self, config):
        self.config = config
        self.sensor_data = {
            'temperature': None,
            'humidity': None,
            'pressure': None,
            'uv_index': None,
            'wind_speed': None,
            'wind_direction': None,
            'rainfall': None,
            'aqi': None,
            'timestamp': None
        }
        self.data_queue = queue.Queue()
        self.last_rain_value = 0
        self.no_rain_counter = 0
        self.rain_reset_threshold = config['gui']['rain_reset_threshold']
        self.rain_reset_time = config['gui']['rain_reset_time']
        self.running = False
        self.modbus_client = None
        self.logger = None
        self.sensors_connected = False  # Flag to track sensor connection status
        self.csv_dir = "csv_data"
        if not os.path.exists(self.csv_dir):
            os.makedirs(self.csv_dir)
        self.setup_logging()
        self.init_modbus()

    def setup_logging(self):
        """Configure logging system with daily rotation and 7-day retention"""
        try:
            logs_dir = "logs"
            if not os.path.exists(logs_dir):
                os.makedirs(logs_dir)
            current_date = datetime.now().strftime('%Y-%m-%d')
            log_file = os.path.join(logs_dir, f"weather_station_{current_date}.log")
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            )
            self.logger = logging.getLogger('WeatherStation')
            self.logger.setLevel(logging.INFO)
            self.logger.addHandler(file_handler)
            if self.config['logging'].get('debug', False):
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.DEBUG)
                self.logger.addHandler(console_handler)
            self.cleanup_old_logs(logs_dir)
            self.log("Data Manager Initialized")
        except Exception as e:
            print(f"Error setting up logging: {e}")
            raise

    def cleanup_old_logs(self, logs_dir):
        """Remove log files older than 7 days"""
        try:
            current_date = datetime.now().date()
            for filename in os.listdir(logs_dir):
                if filename.startswith("weather_station_") and filename.endswith(".log"):
                    file_date_str = filename.replace("weather_station_", "").replace(".log", "")
                    file_date = datetime.strptime(file_date_str, '%Y-%m-%d').date()
                    if (current_date - file_date).days > 7:
                        file_path = os.path.join(logs_dir, filename)
                        os.remove(file_path)
                        self.log(f"Removed old log file: {filename}")
        except Exception as e:
            self.log(f"Error cleaning up old logs: {e}", level=logging.ERROR)

    def log(self, message, level=logging.INFO):
        """Log message with timestamp"""
        if self.logger:
            self.logger.log(level, message)

    def init_modbus(self):
        """Initialize Modbus client connection"""
        try:
            self.modbus_client = ModbusSerialClient(
                port=self.config['modbus']['port'],
                baudrate=self.config['modbus']['baudrate'],
                parity=self.config['modbus']['parity'],
                stopbits=self.config['modbus']['stopbits'],
                timeout=self.config['modbus']['timeout']
            )
            if self.modbus_client.connect():
                self.sensors_connected = True
                self.log("Modbus connection established")
            else:
                self.sensors_connected = False
                self.log("Failed to connect to Modbus, using placeholder data", level=logging.WARNING)
        except Exception as e:
            self.sensors_connected = False
            self.log(f"Modbus initialization error: {e}, using placeholder data", level=logging.ERROR)

    def cleanup_old_csv(self):
        """Remove CSV files older than 7 days"""
        try:
            current_date = datetime.now().date()
            for filename in os.listdir(self.csv_dir):
                if filename.startswith("weather_data_") and filename.endswith(".csv"):
                    file_date_str = filename.replace("weather_data_", "").replace(".csv", "")
                    file_date = datetime.strptime(file_date_str, '%Y-%m-%d').date()
                    if (current_date - file_date).days > 7:
                        file_path = os.path.join(self.csv_dir, filename)
                        os.remove(file_path)
                        self.log(f"Removed old CSV file: {filename}")
        except Exception as e:
            self.log(f"Error cleaning up old CSV files: {e}", level=logging.ERROR)

    def process_rainfall(self, current_rain):
        """Process rainfall data with reset logic"""
        if current_rain is None:
            return None
        if abs(current_rain - self.last_rain_value) < self.rain_reset_threshold:
            self.no_rain_counter += 1
            if self.no_rain_counter >= self.rain_reset_time:
                current_rain = 0
                self.no_rain_counter = 0
        else:
            self.no_rain_counter = 0
        self.last_rain_value = current_rain
        return current_rain

    def calculate_aqi(self, pm2_5):
        """Calculate AQI from PM2.5 reading"""
        if pm2_5 is None:
            return None
        if pm2_5 <= 12.0:
            return (pm2_5 / 12.0) * 50
        elif pm2_5 <= 35.4:
            return ((pm2_5 - 12.1) / (35.4 - 12.1)) * (100 - 51) + 51
        elif pm2_5 <= 55.4:
            return ((pm2_5 - 35.5) / (55.4 - 35.5)) * (150 - 101) + 101
        elif pm2_5 <= 150.4:
            return ((pm2_5 - 55.5) / (150.4 - 55.5)) * (200 - 151) + 151
        elif pm2_5 <= 250.4:
            return ((pm2_5 - 150.5) / (250.4 - 150.5)) * (300 - 201) + 201
        else:
            return ((pm2_5 - 250.5) / (500.4 - 250.5)) * (500 - 301) + 301

    def sensor_reader_loop(self):
        """Main loop for reading sensor data"""
        last_csv_time = time.time()
        while self.running:
            try:
                current_data = {'timestamp': datetime.now().isoformat()}
                if self.sensors_connected:
                    if not self.modbus_client.is_socket_open():
                        self.modbus_client.connect()
                        if not self.modbus_client.is_socket_open():
                            self.sensors_connected = False
                            self.log("Modbus connection lost, switching to placeholder data", level=logging.WARNING)
                    else:
                        sensors = [
                            ('environment', self.read_environment_sensor),
                            ('uv', self.read_uv_sensor),
                            ('aqi', self.read_aqi_sensor),
                            ('wind_speed', self.read_wind_speed),
                            ('wind_direction', self.read_wind_direction),
                            ('rainfall', self.read_rainfall)
                        ]
                        for sensor_name, reader in sensors:
                            try:
                                data = reader()
                                if data:
                                    current_data.update(data)
                                    self.log_sensor_data(sensor_name, data)
                            except Exception as e:
                                self.log(f"Error reading {sensor_name}: {e}", level=logging.ERROR)
                else:
                    # Use placeholder data when sensors are not connected
                    current_data.update({
                        'temperature': None,
                        'humidity': None,
                        'pressure': None,
                        'uv_index': None,
                        'wind_speed': None,
                        'wind_dir_degrees': None,
                        'wind_dir_cardinal': None,
                        'rainfall': None,
                        'pm2_5': None
                    })
                    try:
                        aqi_data = self.read_aqi_sensor()  # Try to read AQI from CSV
                        if aqi_data:
                            current_data.update(aqi_data)
                    except Exception as e:
                        self.log(f"Error reading AQI data: {e}", level=logging.WARNING)

                self.sensor_data = current_data
                now = time.time()
                if now - last_csv_time >= self.config['logging']['csv_interval']:
                    self.data_queue.put(current_data)
                    last_csv_time = now
                time.sleep(1)
            except Exception as e:
                self.log(f"Sensor read error: {e}", level=logging.ERROR)
                time.sleep(1)

    def csv_writer_loop(self):
        """Background thread for writing CSV data"""
        while self.running:
            try:
                data = self.data_queue.get(timeout=1)
                current_date = datetime.now().strftime('%Y-%m-%d')
                csv_file = os.path.join(self.csv_dir, f"weather_data_{current_date}.csv")
                if not os.path.exists(csv_file):
                    with open(csv_file, 'w') as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            'timestamp', 'temperature', 'humidity', 'pressure', 'uv_index',
                            'co2', 'formaldehyde', 'tvoc', 'pm2_5', 'pm10',
                            'aqi_temperature', 'aqi_humidity',
                            'wind_speed', 'wind_dir_degrees', 'wind_dir_cardinal',
                            'rainfall'
                        ])
                    self.cleanup_old_csv()
                with open(csv_file, 'a') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        data['timestamp'],
                        data.get('temperature', ''),
                        data.get('humidity', ''),
                        data.get('pressure', ''),
                        data.get('uv_index', ''),
                        data.get('co2', ''),
                        data.get('formaldehyde', ''),
                        data.get('tvoc', ''),
                        data.get('pm2_5', ''),
                        data.get('pm10', ''),
                        data.get('aqi_temperature', ''),
                        data.get('aqi_humidity', ''),
                        data.get('wind_speed', ''),
                        data.get('wind_dir_degrees', ''),
                        data.get('wind_dir_cardinal', ''),
                        data.get('rainfall', '')
                    ])
            except queue.Empty:
                continue
            except Exception as e:
                self.log(f"CSV write error: {e}", level=logging.ERROR)

    def log_sensor_data(self, sensor_name, data):
        """Log sensor data in appropriate format"""
        if sensor_name == 'environment':
            self.log(f"Env: {data['temperature']:.1f}°C, {data['humidity']:.1f}%, {data['pressure']:.1f}hPa")
        elif sensor_name == 'uv':
            self.log(f"UV: {data['uv_index']:.2f}")
        elif sensor_name == 'aqi':
            self.log(f"AQI Sensor Data: {data}")
        elif sensor_name == 'wind_speed':
            self.log(f"Wind Speed: {data['wind_speed']:.1f} m/s")
        elif sensor_name == 'wind_direction':
            self.log(f"Wind Direction: {data['wind_dir_degrees']}° ({data['wind_dir_cardinal']})")
        elif sensor_name == 'rainfall':
            self.log(f"Raw Rainfall Reading: {data['rainfall']:.1f} mm")

    def read_environment_sensor(self):
        """Read temperature, humidity, and pressure"""
        try:
            result = self.modbus_client.read_holding_registers(
                address=0x0000,
                count=3,
                slave=self.config['sensors']['environment']
            )
            if result.isError():
                return None
            return {
                'temperature': result.registers[0] / 10.0,
                'humidity': result.registers[1] / 10.0,
                'pressure': result.registers[2] / 10.0
            }
        except Exception as e:
            self.log(f"Environment sensor error: {e}", level=logging.ERROR)
            return None

    def read_uv_sensor(self):
        """Read UV index"""
        try:
            result = self.modbus_client.read_holding_registers(
                address=0x0000,
                count=1,
                slave=self.config['sensors']['uv']
            )
            if result.isError():
                return {'uv_index': 0.0}
            return {'uv_index': result.registers[0] / 100.0}
        except Exception as e:
            self.log(f"UV sensor error: {e}", level=logging.ERROR)
            return {'uv_index': 0.0}

    def read_aqi_sensor(self):
        """Read AQI data from CSV file"""
        try:
            current_time = datetime.now()
            csv_path = os.path.join(os.path.dirname(__file__), 'aqi', 'karachi_aqi_data_with_pst.csv')
            if not os.path.exists(csv_path):
                self.log(f"AQI data file not found: {csv_path}", level=logging.ERROR)
                return None
            try:
                df = pd.read_csv(csv_path)
                df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
                closest_time_row = df.iloc[(df['date'] - current_time).abs().argsort()[0]]
                data = {
                    'co2': float(closest_time_row['carbon_dioxide']),
                    'pm2_5': float(closest_time_row['pm2_5']),
                    'pm10': float(closest_time_row['pm10']),
                    'carbon_monoxide': float(closest_time_row['carbon_monoxide']),
                    'nitrogen_dioxide': float(closest_time_row['nitrogen_dioxide']),
                    'sulphur_dioxide': float(closest_time_row['sulphur_dioxide']),
                    'ozone': float(closest_time_row['ozone'])
                }
                return data
            except pd.errors.EmptyDataError:
                self.log("AQI data file is empty", level=logging.ERROR)
                return None
        except Exception as e:
            self.log(f"Error reading AQI data from CSV: {e}", level=logging.ERROR)
            return None

    def read_wind_speed(self):
        """Read wind speed in m/s"""
        try:
            result = self.modbus_client.read_holding_registers(
                address=0x0000,
                count=1,
                slave=self.config['sensors']['wind_speed']
            )
            if result.isError():
                return {'wind_speed': 0.0}
            return {'wind_speed': result.registers[0] / 10.0}
        except Exception as e:
            self.log(f"Wind speed sensor error: {e}", level=logging.ERROR)
            return {'wind_speed': 0.0}

    def read_wind_direction(self):
        """Read wind direction in degrees and cardinal direction"""
        try:
            result = self.modbus_client.read_holding_registers(
                address=0x0000,
                count=3,
                slave=self.config['sensors']['wind_direction']
            )
            if result.isError():
                return None
            reg_0 = result.registers[0]
            reg_2 = result.registers[2]
            avg_value = (reg_0 + reg_2) / 2.0
            wind_dir_degrees = round(avg_value / 10.0)
            if 0 <= wind_dir_degrees <= 360:
                return {
                    'wind_dir_degrees': wind_dir_degrees,
                    'wind_dir_cardinal': self._degrees_to_cardinal(wind_dir_degrees)
                }
            return None
        except Exception as e:
            self.log(f"Wind direction sensor error: {e}", level=logging.ERROR)
            return None

    def _degrees_to_cardinal(self, degrees):
        """Convert degrees to cardinal direction (16-point compass)"""
        if degrees is None or not (0 <= degrees <= 360):
            return "Unknown"
        directions = [
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
        ]
        index = round(degrees / (360. / len(directions))) % len(directions)
        return directions[index]

    def read_rainfall(self):
        """Read rainfall in mm"""
        try:
            result = self.modbus_client.read_holding_registers(
                address=0,
                count=1,
                slave=self.config['sensors']['rainfall']
            )
            if result.isError():
                return None
            return {'rainfall': result.registers[0] / 10.0}
        except Exception as e:
            self.log(f"Rainfall sensor error: {e}", level=logging.ERROR)
            return None

    def get_sun_info(self):
        """Get sunrise and sunset times for Karachi"""
        try:
            current_date = datetime.now().strftime('%m-%d')
            sun_data_file = os.path.join('awos_assit_code', 'karachi_sun_data.csv')
            if not os.path.exists(sun_data_file):
                self.log(f"Sun data file not found: {sun_data_file}", level=logging.WARNING)
                return {'sunrise': '06:00', 'sunset': '18:00'}
            with open(sun_data_file, 'r') as file:
                csv_reader = csv.DictReader(file)
                for row in csv_reader:
                    if row['date'] == current_date:
                        return {'sunrise': row['sunrise'], 'sunset': row['sunset']}
            self.log(f"No sun data found for date: {current_date}", level=logging.WARNING)
            return {'sunrise': '06:00', 'sunset': '18:00'}
        except Exception as e:
            self.log(f"Error reading sun data: {e}", level=logging.ERROR)
            return {'sunrise': '06:00', 'sunset': '18:00'}

    def start(self):
        """Start data collection threads"""
        self.running = True
        self.sensor_thread = threading.Thread(target=self.sensor_reader_loop, daemon=True)
        self.csv_thread = threading.Thread(target=self.csv_writer_loop, daemon=True)
        self.sensor_thread.start()
        self.csv_thread.start()

    def stop(self):
        """Stop data collection threads"""
        self.running = False
        self.sensor_thread.join(timeout=2)
        self.csv_thread.join(timeout=2)
        if self.modbus_client and self.modbus_client.is_socket_open():
            self.modbus_client.close()

class WeatherStationSystem:
    def __init__(self, root, data_manager, display_config):
        self.root = root
        self.data_manager = data_manager
        self.display_config = display_config
        self.root.title(f"Weather Station Dashboard - {display_config.get('id', 'Night')}")
        self.root.after(1000, self._keep_focus)
        self.config = data_manager.config
        self.log = data_manager.log
        self.setup_gui()
        self.init_sensor_config()
        self.update_display()
        self.update_static_elements()
        self.root.bind('<Escape>', lambda e: self.shutdown())
        self.root.bind('<F12>', self.toggle_mapping_mode)
        self.root.bind('<F5>', lambda e: self.force_update())
        self.root.after(3600000, self.check_log_rotation)

    def _keep_focus(self):
        """Periodically bring window to front to fight popups"""
        self.root.lift()
        self.root.after(1000, self._keep_focus)

    def setup_gui(self):
        """Initialize the graphical user interface"""
        self.root.attributes('-fullscreen', True)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill='both', expand=True)
        try:
            image_dir = os.path.join(os.path.dirname(__file__), 'images')
            bg_path = os.path.join(image_dir, self.display_config.get('background_image', self.config['gui']['background_image']))
            if not os.path.exists(bg_path):
                self.log(f"Background image not found at: {bg_path}", level=logging.ERROR)
                raise FileNotFoundError(f"Background image not found: {bg_path}")
            img = Image.open(bg_path)
            img = img.resize((screen_width, screen_height), Image.Resampling.LANCZOS)
            self.bg_image = ImageTk.PhotoImage(img)
            self.bg_canvas = tk.Canvas(
                self.main_frame,
                width=screen_width,
                height=screen_height,
                highlightthickness=0
            )
            self.bg_canvas.pack(fill='both', expand=True)
            self.bg_canvas.create_image(
                screen_width//2,
                screen_height//2,
                image=self.bg_image,
                anchor='center'
            )
        except Exception as e:
            self.log(f"Failed to load background image: {e}", level=logging.ERROR)
            raise
        self.create_display_widgets()
        self.mapping_mode = False
        self.coordinate_text = None

    def create_display_widgets(self):
        """Create all GUI display widgets"""
        default_widget_configs = {
            'temperature_value': {'size': 100, 'color': '#FFFFFF', 'position': (350, 250), 'anchor': 'center'},
            'humidity_value': {'size': 100, 'color': '#FFFFFF', 'position': (980, 250), 'anchor': 'center'},
            'humidity_state_value': {'size': 50, 'color': '#FFFFFF', 'position': (980, 350), 'anchor': 'center'},
            'wind_speed_value': {'size': 100, 'color': '#FFFFFF', 'position': (1600, 250), 'anchor': 'center'},
            'pressure_value': {'size': 100, 'color': '#FFFFFF', 'position': (350, 595), 'anchor': 'center'},
            'rain_value': {'size': 80, 'color': '#FFFFFF', 'position': (940, 595), 'anchor': 'center'},
            'wind_direction_value': {'size': 60, 'color': '#FFFFFF', 'position': (1600, 595), 'anchor': 'center'},
            'uv_value': {'size': 100, 'color': '#FFFFFF', 'position': (350, 890), 'anchor': 'center'},
            'uv_state_value': {'size': 50, 'color': '#FFFFFF', 'position': (350, 975), 'anchor': 'center'},
            'aqi_value': {'size': 100, 'color': '#FFFFFF', 'position': (1600, 890), 'anchor': 'center'},
            'aqi_state_value': {'size': 50, 'color': '#FFFFFF', 'position': (1600, 975), 'anchor': 'center'},
            'current_day_value': {'size': 55, 'color': '#FFFFFF', 'position': (950, 55), 'anchor': 'center'},
            'current_date_value': {'size': 55, 'color': '#FFFFFF', 'position': (330, 55), 'anchor': 'center'},
            'current_time_value': {'size': 55, 'color': '#FFFFFF', 'position': (1550, 55), 'anchor': 'center'},
            'sunrise_value': {'size': 80, 'color': '#FFFFFF', 'position': (1145, 822), 'anchor': 'ne'},
            'sunset_value': {'size': 80, 'color': '#FFFFFF', 'position': (1145, 935), 'anchor': 'ne'}
        }
        widget_configs = self.display_config.get('widget_configs', default_widget_configs)
        font_name = self.display_config.get('font', self.config['gui'].get('font', 'Digital-7'))
        for widget_name, config in widget_configs.items():
            setattr(self, widget_name, self.bg_canvas.create_text(
                config['position'],
                text="--",
                font=(font_name, config['size'], 'bold'),
                fill=config['color'],
                anchor=config['anchor']
            ))

    def init_sensor_config(self):
        """Initialize sensor parsing configurations"""
        self.sensor_configs = {
            'temperature': {
                'parser': lambda data: data.get('temperature'),
                'display_format': lambda v: f"{v:.1f}" if v is not None else "--",
                'widget': 'temperature_value'
            },
            'humidity': {
                'parser': lambda data: data.get('humidity'),
                'display_format': lambda v: f"{v:.1f}%" if v is not None else "--",
                'widget': 'humidity_value'
            },
            'pressure': {
                'parser': lambda data: data.get('pressure'),
                'display_format': lambda v: f"{v:.1f}" if v is not None else "--",
                'widget': 'pressure_value'
            },
            'wind_speed': {
                'parser': lambda data: data.get('wind_speed', 0.0) * 3.6,
                'display_format': lambda v: f"{v:.1f}" if v is not None else "--",
                'widget': 'wind_speed_value'
            },
            'wind_direction': {
                'parser': lambda data: data.get('wind_dir_degrees'),
                'display_format': lambda v: f"{v}°" if v is not None else "--",
                'widget': 'wind_direction_value'
            },
            'rain': {
                'parser': lambda data: self.data_manager.process_rainfall(data.get('rainfall')),
                'display_format': lambda v: f"{v:.1f}" if v is not None else "--",
                'widget': 'rain_value'
            },
            'uv': {
                'parser': lambda data: data.get('uv_index'),
                'display_format': lambda v: f"{v:.2f}" if v is not None else "--",
                'widget': 'uv_value'
            },
            'aqi': {
                'parser': lambda data: self.data_manager.calculate_aqi(data.get('pm2_5')),
                'display_format': lambda v: f"{v:.0f}" if v is not None else "--",
                'widget': 'aqi_value'
            }
        }

    def get_aqi_state(self, aqi):
        """Determine AQI state and color"""
        if aqi is None:
            return "N/A", "#FFFFFF"
        aqi_float = float(aqi)
        if 0.0 <= aqi_float <= 50.0:
            return "GOOD", "#39FF14"
        elif 50.1 <= aqi_float <= 100.0:
            return "MODERATE", "#FFFF00"
        elif 100.1 <= aqi_float <= 150.0:
            return "UNHEALTHY", "#FF7E00"
        elif 150.1 <= aqi_float <= 200.0:
            return "UNHEALTHY", "#FF0000"
        elif 200.1 <= aqi_float <= 300.0:
            return "VERY UNHEALTHY", "#8F3F97"
        else:
            return "HAZARDOUS", "#7E0023"

    def get_uv_state(self, uv):
        """Determine UV state and color"""
        if uv is None:
            return "N/A", "#FFFFFF"
        uv_float = float(uv)
        if 0.0 <= uv_float <= 2.0:
            return "LOW", "#39FF14"
        elif 2.1 <= uv_float <= 5.0:
            return "MODERATE", "#FFFF00"
        elif 5.1 <= uv_float <= 7.0:
            return "HIGH", "#FF7E00"
        elif 7.1 <= uv_float <= 10.0:
            return "VERY HIGH", "#FF0000"
        else:
            return "EXTREME", "#8F3F97"

    def get_humidity_state(self, humidity):
        """Determine humidity state and color"""
        if humidity is None:
            return "N/A", "#FFFFFF"
        humidity_float = float(humidity)
        if 0.0 <= humidity_float <= 30.0:
            return "LOW", "#3EC1EC"
        elif 30.1 <= humidity_float <= 50.0:
            return "NORMAL", "#39FF14"
        elif 50.1 <= humidity_float <= 60.0:
            return "SLIGHTLY HIGH", "#FFFF00"
        elif 60.1 <= humidity_float <= 70.0:
            return "HIGH", "#FF7E00"
        else:
            return "VERY HIGH", "#FF0000"

    def update_static_elements(self):
        """Update date, time and sun information"""
        datetime_info = self.get_datetime_info()
        sun_info = self.data_manager.get_sun_info()
        self.bg_canvas.itemconfig(self.current_day_value, text=datetime_info['day'])
        self.bg_canvas.itemconfig(self.current_date_value, text=datetime_info['date'])
        self.bg_canvas.itemconfig(self.current_time_value, text=datetime_info['time'])
        self.bg_canvas.itemconfig(self.sunrise_value, text=f"↑{sun_info['sunrise']}")
        self.bg_canvas.itemconfig(self.sunset_value, text=f"↓{sun_info['sunset']}")
        self.root.after(60000, self.update_static_elements)

    def update_display(self):
        """Update all display elements with current sensor data"""
        try:
            for sensor_name, config in self.sensor_configs.items():
                value = config['parser'](self.data_manager.sensor_data)
                widget = getattr(self, config['widget'])
                formatted_value = config['display_format'](value)
                self.bg_canvas.itemconfig(widget, text=formatted_value)
            self.update_state_displays()
        except Exception as e:
            self.log(f"Display update error: {e}", level=logging.ERROR)
        self.root.after(self.config['gui']['update_interval'], self.update_display)

    def update_state_displays(self):
        """Update state displays with appropriate colors"""
        try:
            humidity = self.data_manager.sensor_data.get('humidity')
            if humidity is not None:
                hum_state, hum_color = self.get_humidity_state(humidity)
                self.bg_canvas.itemconfig(self.humidity_value, fill=hum_color)
                self.bg_canvas.itemconfig(self.humidity_state_value, text=hum_state, fill=hum_color)
            else:
                self.bg_canvas.itemconfig(self.humidity_state_value, text="N/A", fill="#FFFFFF")
            uv = self.data_manager.sensor_data.get('uv_index')
            if uv is not None:
                uv_state, uv_color = self.get_uv_state(uv)
                self.bg_canvas.itemconfig(self.uv_value, fill=uv_color)
                self.bg_canvas.itemconfig(self.uv_state_value, text=uv_state, fill=uv_color)
            else:
                self.bg_canvas.itemconfig(self.uv_state_value, text="N/A", fill="#FFFFFF")
            pm2_5 = self.data_manager.sensor_data.get('pm2_5')
            if pm2_5 is not None:
                aqi = self.data_manager.calculate_aqi(pm2_5)
                aqi_state, aqi_color = self.get_aqi_state(aqi)
                self.bg_canvas.itemconfig(self.aqi_value, fill=aqi_color)
                self.bg_canvas.itemconfig(self.aqi_state_value, text=aqi_state, fill=aqi_color)
            else:
                self.bg_canvas.itemconfig(self.aqi_state_value, text="N/A", fill="#FFFFFF")
        except Exception as e:
            self.log(f"Error updating state displays: {e}", level=logging.ERROR)

    def toggle_mapping_mode(self, event=None):
        """Toggle coordinate mapping mode"""
        self.mapping_mode = not self.mapping_mode
        if self.mapping_mode:
            self.bg_canvas.bind('<Button-1>', self.show_coordinates)
            if self.coordinate_text:
                self.bg_canvas.delete(self.coordinate_text)
            self.coordinate_text = self.bg_canvas.create_text(
                10, 10,
                text="Mapping Mode ON (Click to see coordinates)",
                fill='red',
                anchor='nw'
            )
        else:
            self.bg_canvas.unbind('<Button-1>')
            if self.coordinate_text:
                self.bg_canvas.delete(self.coordinate_text)

    def show_coordinates(self, event):
        """Display coordinates where user clicked"""
        x, y = event.x, event.y
        print(f"Coordinates: x={x}, y={y}")
        marker = self.bg_canvas.create_oval(
            x-2, y-2, x+2, y+2,
            fill='red'
        )
        text = self.bg_canvas.create_text(
            x+10, y-10,
            text=f"({x}, {y})",
            fill='red',
            anchor='w'
        )
        self.root.after(2000, lambda: self.bg_canvas.delete(marker, text))

    def shutdown(self):
        """Clean shutdown of the system"""
        self.log(f"Shutting down display {self.display_config.get('id', 'Night')}")
        self.root.destroy()

    def get_datetime_info(self):
        """Get current date and time information"""
        now = datetime.now()
        return {
            'day': now.strftime('%A').upper(),
            'date': now.strftime('%d %b').replace(now.strftime('%b'), now.strftime('%b').upper()) + now.strftime(' %Y'),
            'time': now.strftime('%H:%M')
        }

    def force_update(self):
        """Force immediate update of all display elements"""
        self.update_display()
        self.update_static_elements()
        self.log("Display manually refreshed", level=logging.INFO)

    def check_log_rotation(self):
        """Periodic check for log rotation"""
        self.data_manager.check_and_rotate_logs()
        self.root.after(3600000, self.check_log_rotation)

class GUIManager:
    def __init__(self, data_manager, display_configs):
        self.data_manager = data_manager
        self.display_configs = display_configs
        self.current_display = None
        self.root = tk.Tk()
        self.root.withdraw()  # Hide main root window
        self.apps = {}
        self.day_display_index = 0
        self.toggle_time_start = time.time()
        self.running = True
        self.check_display_time()

    def check_display_time(self):
        """Check current time and update display accordingly"""
        try:
            sun_info = self.data_manager.get_sun_info()
            sunrise = datetime.strptime(sun_info['sunrise'], '%H:%M').time()
            sunset = datetime.strptime(sun_info['sunset'], '%H:%M').time()
            current_time = datetime.now().time()
            is_daytime = sunrise <= current_time < sunset

            if is_daytime:
                self.handle_day_display()
            else:
                self.handle_night_display()

            self.root.after(5000, self.check_display_time)  # Check every 5 seconds
        except Exception as e:
            self.data_manager.log(f"Error checking display time: {e}", level=logging.ERROR)
            self.root.after(5000, self.check_display_time)

    def handle_night_display(self):
        """Show night display (GUI 1)"""
        if self.current_display != 'night':
            self.data_manager.log(f"Switching to Night display")
            self.destroy_current_display()
            self.current_display = 'night'
            self.create_display('night')

    def handle_day_display(self):
        """Toggle between day displays (GUI 2 and GUI 3)"""
        day_displays = ['day1', 'day2']
        toggle_durations = [
            self.display_configs['day1']['display_duration'],
            self.display_configs['day2']['display_duration']
        ]
        elapsed = time.time() - self.toggle_time_start
        total_cycle = sum(toggle_durations)
        cycle_position = elapsed % total_cycle
        current_index = 0
        cumulative_duration = 0
        for i, duration in enumerate(toggle_durations):
            cumulative_duration += duration
            if cycle_position < cumulative_duration:
                current_index = i
                break
        if self.current_display != day_displays[current_index]:
            self.data_manager.log(f"Switching to {day_displays[current_index]} display")
            self.destroy_current_display()
            self.current_display = day_displays[current_index]
            self.create_display(day_displays[current_index])

    def create_display(self, display_id):
        """Create a new display instance"""
        if display_id in self.apps and self.apps[display_id].root.winfo_exists():
            self.apps[display_id].root.deiconify()
        else:
            root = tk.Toplevel(self.root)
            root.wm_attributes("-topmost", True)
            app = WeatherStationSystem(root, self.data_manager, self.display_configs[display_id])
            self.apps[display_id] = app
            root.protocol("WM_DELETE_WINDOW", self.shutdown)

    def destroy_current_display(self):
        """Destroy or hide the current display"""
        if self.current_display and self.current_display in self.apps:
            if self.apps[self.current_display].root.winfo_exists():
                self.apps[self.current_display].root.withdraw()

    def shutdown(self):
        """Shutdown all displays and system"""
        self.data_manager.log("Shutting down all displays")
        self.running = False
        self.destroy_current_display()
        for app in self.apps.values():
            if app.root.winfo_exists():
                app.shutdown()
        self.data_manager.stop()
        self.root.destroy()

if __name__ == "__main__":
    try:
        # Load configuration
        config = {
            'modbus': {
                'port': '/dev/ttyUSB0',
                'baudrate': 9600,
                'parity': 'N',
                'stopbits': 1,
                'timeout': 2,
                'retries': 3
            },
            'sensors': {
                'environment': 1,
                'uv': 2,
                'aqi': 3,
                'wind_speed': 4,
                'wind_direction': 5,
                'rainfall': 6
            },
            'logging': {
                'log_file': 'weather_station.log',
                'max_log_entries': 1000,
                'csv_file': 'weather_data.csv',
                'csv_interval': 30,
                'log_rotate_size': 1000000,
                'log_backup_count': 5
            },
            'gui': {
                'update_interval': 1000,
                'background_image': 'night_blank.png',
                'font': 'Digital-7',
                'rain_reset_threshold': 0.1,
                'rain_reset_time': 12
            },
            'location': {
                'sun_data_file': 'karachi_sun_data.csv',
                'default_sunrise': '06:00',
                'default_sunset': '18:00'
            }
        }

        display_configs = {
            'night': {
                'id': 'night',
                'background_image': 'night_blank.png',
                'font': 'Digital-7'
            },
            'day1': {
                'id': 'day1',
                'background_image': 'day1_blank.png',
                'font': 'Arial',
                'display_duration': 300  # 5 minutes in seconds
            },
            'day2': {
                'id': 'day2',
                'background_image': 'day2_blank.png',
                'font': 'Arial',
                'display_duration': 300  # 5 minutes in seconds
            }
        }

        try:
            config_parser = configparser.ConfigParser()
            if os.path.exists('weather_station.ini'):
                config_parser.read('weather_station.ini')
                for section in config_parser.sections():
                    if section in config:
                        for key in config_parser[section]:
                            if key in config[section]:
                                value = config_parser[section][key].strip('"\'')
                                if isinstance(config[section][key], int):
                                    config[section][key] = int(value)
                                elif isinstance(config[section][key], float):
                                    config[section][key] = float(value)
                                else:
                                    config[section][key] = value
                    elif section.startswith('display_'):
                        display_id = section.replace('display_', '')
                        if display_id in display_configs:
                            for key in config_parser[section]:
                                value = config_parser[section][key].strip('"\'')
                                if key == 'display_duration':
                                    display_configs[display_id][key] = float(value)
                                else:
                                    display_configs[display_id][key] = value
        except Exception as e:
            print(f"Config load error: {e}. Using defaults.")

        data_manager = DataManager(config)
        data_manager.start()

        gui_manager = GUIManager(data_manager, display_configs)
        gui_manager.root.mainloop()

    except Exception as e:
        print(f"Critical error: {e}")
        raise