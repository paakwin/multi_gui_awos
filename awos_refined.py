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

class WeatherStationSystem:
    # --- Initialization and Configuration ---
    def __init__(self, root: tk.Tk) -> None:
        """Initialize the WeatherStationSystem, set up GUI, logging, config, sensors, and start threads."""
        self.root = root
        self.root.title("Weather Station Dashboard")
        self.root.after(1000, self._keep_focus)  # Add periodic focus check
        
        # Initialize system
        self.load_config()
        self.setup_logging()
        self.init_data_structures()
        self.setup_gui()
        self.init_modbus()
        self.init_sensor_config()
        
        # Start system threads
        self.start_threads()
        
        # Initial updates
        self.update_display()
        self.update_static_elements()
        
        # Bind keys
        self.root.bind('<Escape>', lambda e: self.shutdown())
        self.root.bind('<F12>', self.toggle_mapping_mode)
        self.root.bind('<F5>', lambda e: self.force_update())  # Add F5 refresh
        
        # Schedule periodic log rotation check
        self.root.after(3600000, self.check_log_rotation)  # Check every hour

    def _keep_focus(self) -> None:
        """Periodically bring the window to the front to maintain focus and prevent popups."""
        self.root.lift()
        self.root.after(1000, self._keep_focus)  # Recheck every 1 second

    def load_config(self) -> None:
        """Load configuration from INI file if available, otherwise use default settings."""
        self.config = {
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
                'log_rotate_size': 1000000,  # 1MB
                'log_backup_count': 5
            },
            'gui': {
                'update_interval': 1000,
                'background_image': 'final_blank.png', # Ensure this image exists in the images directory
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
        
        try:
            config = configparser.ConfigParser()
            if os.path.exists('weather_station.ini'):
                config.read('weather_station.ini')
                for section in config.sections():
                    for key in config[section]:
                        if section in self.config and key in self.config[section]:
                            value = config[section][key].strip('"\'')
                            if isinstance(self.config[section][key], int):
                                self.config[section][key] = int(value)
                            elif isinstance(self.config[section][key], float):
                                self.config[section][key] = float(value)
                            else:
                                self.config[section][key] = value
        except Exception as e:
            self.log(f"Config load error: {e}. Using defaults.", level=logging.WARNING)

    def setup_logging(self) -> None:
        """Set up logging with daily rotation, 7-day retention, and optional console output."""
        try:
            # Create logs directory if it doesn't exist
            logs_dir = "logs"
            if not os.path.exists(logs_dir):
                os.makedirs(logs_dir)

            # Set up daily log file
            current_date = datetime.now().strftime('%Y-%m-%d')
            log_file = os.path.join(logs_dir, f"weather_station_{current_date}.log")

            # Configure file handler
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            )

            # Configure logger
            self.logger = logging.getLogger('WeatherStation')
            self.logger.setLevel(logging.INFO)
            self.logger.addHandler(file_handler)

            # Also log to console in debug mode
            if self.config['logging'].get('debug', False):
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.DEBUG)
                self.logger.addHandler(console_handler)

            # Clean up old log files
            self.cleanup_old_logs(logs_dir)

            self.log("Weather Station System Initialized")

        except Exception as e:
            print(f"Error setting up logging: {e}")
            raise

    def cleanup_old_logs(self, logs_dir: str) -> None:
        """Remove log files older than 7 days from the logs directory."""
        try:
            # Get current date
            current_date = datetime.now().date()
            
            # List all log files
            for filename in os.listdir(logs_dir):
                if filename.startswith("weather_station_") and filename.endswith(".log"):
                    try:
                        # Extract date from filename
                        file_date_str = filename.replace("weather_station_", "").replace(".log", "")
                        file_date = datetime.strptime(file_date_str, '%Y-%m-%d').date()
                        
                        # Calculate age in days
                        age = (current_date - file_date).days
                        
                        # Remove if older than 7 days
                        if age > 7:
                            file_path = os.path.join(logs_dir, filename)
                            os.remove(file_path)
                            print(f"Removed old log file: {filename}")
                    
                    except (ValueError, OSError) as e:
                        print(f"Error processing log file {filename}: {e}")
                        continue

        except Exception as e:
            print(f"Error cleaning up old logs: {e}")

    def check_and_rotate_logs(self) -> None:
        """Rotate log files if the date has changed and clean up old logs."""
        try:
            current_date = datetime.now().strftime('%Y-%m-%d')
            current_log_file = os.path.join("logs", f"weather_station_{current_date}.log")
            
            # If the current handler is writing to a different file, update it
            current_handlers = self.logger.handlers
            for handler in current_handlers:
                if isinstance(handler, logging.FileHandler):
                    if handler.baseFilename != current_log_file:
                        # Remove old handler
                        self.logger.removeHandler(handler)
                        handler.close()
                        
                        # Add new handler
                        new_handler = logging.FileHandler(current_log_file)
                        new_handler.setFormatter(
                            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
                        )
                        self.logger.addHandler(new_handler)
                        
                        # Clean up old logs
                        self.cleanup_old_logs("logs")
                    break

        except Exception as e:
            print(f"Error rotating logs: {e}")

    def log(self, message: str, level: int = logging.INFO) -> None:
        """Log a message with a specified logging level."""
        self.logger.log(level, message)

    def init_data_structures(self) -> None:
        """Initialize sensor data storage, queues, and create CSV directory if needed."""
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
        self.log_buffer = deque(maxlen=self.config['logging']['max_log_entries'])
        self.last_rain_value = 0
        self.no_rain_counter = 0
        self.rain_reset_threshold = self.config['gui']['rain_reset_threshold']
        self.rain_reset_time = self.config['gui']['rain_reset_time']

        # Create csv directory if it doesn't exist
        self.csv_dir = "csv_data"
        if not os.path.exists(self.csv_dir):
            os.makedirs(self.csv_dir)

    def cleanup_old_csv(self) -> None:
        """Remove weather data CSV files older than 7 days from the CSV directory."""
        try:
            current_date = datetime.now().date()
            
            for filename in os.listdir(self.csv_dir):
                if filename.startswith("weather_data_") and filename.endswith(".csv"):
                    try:
                        # Extract date from filename
                        file_date_str = filename.replace("weather_data_", "").replace(".csv", "")
                        file_date = datetime.strptime(file_date_str, '%Y-%m-%d').date()
                        
                        # Remove if older than 7 days
                        if (current_date - file_date).days > 7:
                            file_path = os.path.join(self.csv_dir, filename)
                            os.remove(file_path)
                            self.log(f"Removed old CSV file: {filename}")
                
                    except (ValueError, OSError) as e:
                        self.log(f"Error processing CSV file {filename}: {e}", level=logging.ERROR)

        except Exception as e:
            self.log(f"Error cleaning up old CSV files: {e}", level=logging.ERROR)

    # --- GUI Setup and Display ---
    def setup_gui(self) -> None:
        """Set up the main GUI window, background image, and display widgets."""
        self.root.attributes('-fullscreen', True)
        
        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Main frame
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill='both', expand=True)
        
        # Background image
        try:
            # Fix the image path
            image_dir = os.path.join(os.path.dirname(__file__), 'images')
            bg_path = os.path.join(os.path.dirname(__file__), 'images', self.config['gui']['background_image'])
            
            if not os.path.exists(bg_path):
                self.log(f"Background image not found at: {bg_path}", level=logging.ERROR)
                raise FileNotFoundError(f"Background image not found: {bg_path}")
                
            img = Image.open(bg_path)
            
            # Resize image to match screen dimensions
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

        # Create display widgets
        self.create_display_widgets()
        
        # Mapping mode variables
        self.mapping_mode = False
        self.coordinate_text = None

    def create_display_widgets(self) -> None:
        """Create and place all display widgets on the background canvas."""
        self.widget_configs = {
            'temperature_value': {
                'size': 100, 'color': '#FFFFFF', 'position': (350, 250), 'anchor': 'center'  # Changed from 'nw'
            },
            'humidity_value': {
                'size': 100, 'color': '#FFFFFF', 'position': (980, 250), 'anchor': 'center'  # Changed from 'nw'
            },
            'humidity_state_value': {
                'size': 50, 'color': '#FFFFFF', 'position': (980, 350), 'anchor': 'center'  # Changed from 'nw'
            },
            'wind_speed_value': {
                'size': 100, 'color': '#FFFFFF', 'position': (1600, 250), 'anchor': 'center'
            },
            'pressure_value': {
                'size': 100, 'color': '#FFFFFF', 'position': (350, 595), 'anchor': 'center'
            },
            'rain_value': {
                'size': 80, 'color': '#FFFFFF', 'position': (940, 595), 'anchor': 'center'  # Changed from 's'
            },
            'wind_direction_value': {
                'size': 60, 'color': '#FFFFFF', 'position': (1600, 595), 'anchor': 'center'
            },
            'uv_value': {
                'size': 100, 'color': '#FFFFFF', 'position': (350, 890), 'anchor': 'center'
            },
            'uv_state_value': {
                'size': 50, 'color': '#FFFFFF', 'position': (350, 975), 'anchor': 'center'
            },
            'aqi_value': {
                'size': 100, 'color': '#FFFFFF', 'position': (1600, 890), 'anchor': 'center'
            },
            'aqi_state_value': {
                'size': 50, 'color': '#FFFFFF', 'position': (1600, 975), 'anchor': 'center'
            },
            'current_day_value': {
                'size': 55, 
                'color': '#FFFFFF', 
                'position': (950, 55), 
                'anchor': 'center'
            },
            'current_date_value': {
                'size': 55, 
                'color': '#FFFFFF', 
                'position': (330 ,55),  # Single position for complete date
                'anchor': 'center'
            },
            'current_time_value': {
                'size': 55, 
                'color': '#FFFFFF', 
                'position': (1550, 55), 
                'anchor': 'center'
            },
            'sunrise_value': {
                'size': 80, 'color': '#FFFFFF', 'position': (1145, 822), 'anchor': 'ne'
            },
            'sunset_value': {
                'size': 80, 'color': '#FFFFFF', 'position': (1145, 935), 'anchor': 'ne'
            }
        }
        
        # Create all widgets
        font_name = self.config['gui'].get('font', 'Digital-7')
        for widget_name, config in self.widget_configs.items():
            setattr(self, widget_name, self.bg_canvas.create_text(
                config['position'],
                text="--",
                font=(font_name, config['size'], 'bold'),
                fill=config['color'],
                anchor=config['anchor']
            ))

    # --- Modbus and Sensor Configuration ---
    def init_modbus(self) -> None:
        """Initialize the Modbus serial client connection for sensor communication."""
        self.modbus_client = ModbusSerialClient(
            port=self.config['modbus']['port'],
            baudrate=self.config['modbus']['baudrate'],
            parity=self.config['modbus']['parity'],
            stopbits=self.config['modbus']['stopbits'],
            timeout=self.config['modbus']['timeout']
        )
        
        if not self.modbus_client.connect():
            self.log("Modbus connection failed in init_modbus", level=logging.ERROR)


    def init_sensor_config(self) -> None:
        """Set up sensor parsing and display formatting configurations."""
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
                'parser': lambda data: data.get('wind_speed', 0.0) * 3.6 if data.get('wind_speed') is not None else None,  # Convert to km/h
                'display_format': lambda v: f"{v:.1f}" if v is not None else "--",
                'widget': 'wind_speed_value'
            },
            'wind_direction': {
                'parser': lambda data: data.get('wind_dir_degrees'),
                'display_format': lambda v: f"{v}°" if v is not None else "--",
                'widget': 'wind_direction_value'
            },
            'rain': {
                'parser': lambda data: self.process_rainfall(data.get('rainfall')),
                'display_format': lambda v: f"{v:.1f}" if v is not None else "--",
                'widget': 'rain_value'
            },
            'uv': {
                'parser': lambda data: data.get('uv_index'),
                'display_format': lambda v: f"{v:.2f}" if v is not None else "--",
                'widget': 'uv_value'
            },
            'aqi': {
                'parser': lambda data: self.calculate_aqi(data.get('pm2_5')),
                'display_format': lambda v: f"{v:.0f}" if v is not None else "--",
                'widget': 'aqi_value'
            }
        }

    # --- Rainfall and AQI Processing ---
    def store_daily_rainfall(self, total: float) -> None:
        """Store the total daily rainfall in a CSV file in the rainfall_data directory."""
        try:
            os.makedirs("rainfall_data", exist_ok=True)
            file_path = os.path.join("rainfall_data", "daily_rainfall_totals.csv")

            is_new = not os.path.exists(file_path)
            with open(file_path, 'a', newline='') as f:
                writer = csv.writer(f)
                if is_new:
                    writer.writerow(['Date', 'Rainfall (mm)'])
                writer.writerow([datetime.now().strftime('%Y-%m-%d'), f"{total:.1f}"])
        except Exception as e:
            self.log(f"Error storing daily rainfall: {e}", level=logging.ERROR)

    def process_rainfall(self, current_rain: float) -> float | None:
        """Accumulate rainfall for the current day, reset at midnight, and handle sensor resets.

        Args:
            current_rain (float): Current cumulative rainfall reading from the sensor (mm)

        Returns:
            float: Current day's accumulated rainfall
        """
        if current_rain is None:
            return None

        now = datetime.now()

        # Reset if a new day has started
        if not hasattr(self, 'last_rain_reset_day') or now.day != self.last_rain_reset_day:
            if hasattr(self, 'daily_rain_total'):
                self.store_daily_rainfall(self.daily_rain_total)
                self.log(f"Rainfall reset at midnight. Stored: {self.daily_rain_total:.1f} mm")
            self.last_rain_reset_day = now.day
            self.daily_rain_total = 0
            self.last_rain_value = current_rain  # avoid spike on first diff

        # Calculate rain increment since last reading
        rain_increment = current_rain - self.last_rain_value
        if rain_increment >= 0:
            self.daily_rain_total += rain_increment
            self.last_rain_value = current_rain
        else:
            # Sensor reset or overflow – discard negative delta
            self.log(f"Rain sensor reset or error. Current: {current_rain}, Last: {self.last_rain_value}")
            self.last_rain_value = current_rain  # resync without adding

        return self.daily_rain_total
    




    def calculate_aqi(self, pm2_5: float | None) -> float | None:
        """Calculate the Air Quality Index (AQI) from a PM2.5 value."""
        if pm2_5 is None:
            return None
        try:
            pm2_5 = float(pm2_5)
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
        except (TypeError, ValueError):
            return None

    # --- Threading and Sensor Reading ---
    def start_threads(self) -> None:
        """Start background threads for sensor reading and CSV writing."""
        self.running = True
        self.sensor_thread = threading.Thread(target=self.sensor_reader_loop, daemon=True)
        self.csv_thread = threading.Thread(target=self.csv_writer_loop, daemon=True)
        self.sensor_thread.start()
        self.csv_thread.start()

    def sensor_reader_loop(self) -> None:
        """Continuously read sensor data, update shared data, and queue data for CSV writing."""
        last_csv_time = time.time()
        
        while self.running:
            try:
                if not self.modbus_client.connect():
                    self.log("Modbus connection failed sensor reader loop", level=logging.ERROR)
                    time.sleep(5)
                    continue
                
                current_data = {'timestamp': datetime.now().isoformat()}
                
                # Read all sensors
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
                
                # Update shared data
                self.sensor_data = current_data
                
                # Queue data for CSV writing if interval has passed
                now = time.time()
                if now - last_csv_time >= self.config['logging']['csv_interval']:
                    self.data_queue.put(current_data)
                    last_csv_time = now
                
                time.sleep(1)  # Maintain 1Hz update rate
                
            except Exception as e:
                self.log(f"Sensor read error: {e}", level=logging.ERROR)
                time.sleep(1)

    def log_sensor_data(self, sensor_name: str, data: dict) -> None:
        """Log formatted sensor data for debugging and monitoring."""
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

    # --- Sensor Reading Methods ---
    def read_environment_sensor(self) -> dict:
        """Read temperature, humidity, and pressure from the environment sensor via Modbus."""
        try:
            result = self.modbus_client.read_holding_registers(
                address=0x0000,
                count=3,
                slave=self.config['sensors']['environment']
            )
            
            if result.isError():
                return {
                    'temperature': 0.0,
                    'humidity': 0.0,
                    'pressure': 0.0
                }
                
            return {
                'temperature': result.registers[0] / 10.0,
                'humidity': result.registers[1] / 10.0,
                'pressure': result.registers[2] / 10.0
            }
        except Exception as e:
            self.log(f"Environment sensor error: {e}", level=logging.ERROR)
            return {
                'temperature': 0.0,
                'humidity': 0.0,
                'pressure': 0.0
            }

    def read_uv_sensor(self) -> dict:
        """Read the UV index from the UV sensor via Modbus."""
        try:
            result = self.modbus_client.read_holding_registers(
                address=0x0000,
                count=1,
                slave=self.config['sensors']['uv']
            )
            
            if result.isError():
                return {'uv_index': 0.0}  # Return 0.0 instead of None
            
            return {'uv_index': result.registers[0] / 100.0}
        except Exception as e:
            self.log(f"UV sensor error: {e}", level=logging.ERROR)
            return {'uv_index': 0.0}  # Return 0.0 instead of None

    def read_aqi_sensor(self) -> dict:
        """Read AQI-related data from a CSV file and return the closest timestamp row."""
        try:
            # Get current timestamp in local time (tz-naive)
            current_time = datetime.now()
            
            # Read the CSV file
            csv_path = os.path.join(os.path.dirname(__file__), 'aqi', 'karachi_aqi_data_with_pst.csv')
            
            if not os.path.exists(csv_path):
                self.log(f"AQI data file not found: {csv_path}", level=logging.ERROR)
                return {'pm2_5': 0.0}  # Return default value instead of None
                
            try:
                df = pd.read_csv(csv_path)
                
                # Convert date column to datetime and ensure it's tz-naive
                df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
                
                # Get the closest timestamp row
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
                return {'pm2_5': 0.0}  # Return default value instead of None
                
        except Exception as e:
            self.log(f"Error reading AQI data from CSV: {e}", level=logging.ERROR)
            return {'pm2_5': 0.0}  # Return default value instead of None

    def read_wind_speed(self) -> dict:
        """Read wind speed in m/s from the wind speed sensor via Modbus."""
        try:
            result = self.modbus_client.read_holding_registers(
                address=0x0000,
                count=1,
                slave=self.config['sensors']['wind_speed']
            )
            
            if result.isError():
                return {'wind_speed': 0.0}  # Return 0.0 instead of None
            
            return {'wind_speed': result.registers[0] / 10.0}
        except Exception as e:
            self.log(f"Wind speed sensor error: {e}", level=logging.ERROR)
            return {'wind_speed': 0.0}  # Return 0.0 instead of None

    def read_wind_direction(self) -> dict | None:
        """Read wind direction in degrees and cardinal direction from the wind direction sensor."""
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

    def _degrees_to_cardinal(self, degrees: float | None) -> str:
        """Convert wind direction in degrees to a 16-point cardinal direction string."""
        if degrees is None or not (0 <= degrees <= 360):
            return "Unknown"
            
        directions = [
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
        ]
        index = round(degrees / (360. / len(directions))) % len(directions)
        return directions[index]

    def read_rainfall(self) -> dict | None:
        """Read cumulative rainfall in mm from the rainfall sensor via Modbus."""
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

    # --- CSV Writing ---
    def csv_writer_loop(self) -> None:
        """Write queued sensor data to a daily CSV file and clean up old CSV files."""
        while self.running:
            try:
                data = self.data_queue.get(timeout=1)
                
                # Get current date for filename
                current_date = datetime.now().strftime('%Y-%m-%d')
                csv_file = os.path.join(self.csv_dir, f"weather_data_{current_date}.csv")
                
                # Create new CSV file with headers if it doesn't exist
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
                    # Clean up old CSV files when creating new one
                    self.cleanup_old_csv()
                
                # Append data to current day's CSV
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

    # --- Display and State Updates ---
    def get_datetime_info(self) -> dict:
        """Return current day, date, and time as formatted strings for display."""
        now = datetime.now()
        return {
            'day': now.strftime('%A').upper(),  # Convert weekday to uppercase
            'date': now.strftime('%d %b').replace(now.strftime('%b'), now.strftime('%b').upper()) + now.strftime(' %Y'),
            'time': now.strftime('%H:%M')
        }

    def get_aqi_state(self, aqi: float | None) -> tuple[str, str]:
        """Determine AQI state and color based on AQI value."""
        if aqi is None:
            return "N/A", "#FFFFFF"  # White
        aqi_float = float(aqi)
        if 0 <= aqi_float <= 50:
            return "GOOD", "#39FF14"  # Neon Green
        elif 50 <= aqi_float <= 100:
            return "MODERATE", "#FFFF00"  # Yellow
        elif 100 <= aqi_float <= 150:
            return "UNHEALTHY", "#FF7E00"  # Orange
        elif 150 <= aqi_float <= 200:
            return "UNHEALTHY", "#FF0000"  # Red
        elif 200 <= aqi_float <= 300:
            return "VERY UNHEALTHY", "#8F3F97"  # Purple
        else:
            return "HAZARDOUS", "#7E0023"  # Dark Red

    def get_uv_state(self, uv: float | None) -> tuple[str, str]:
        """Determine UV state and color based on UV index value."""
        if uv is None:
            return "N/A", "#FFFFFF"  # White
        uv_float = float(uv)
        if 0 <= uv_float <= 2:
            return "LOW", "#39FF14"  # Neon Green
        elif 2 <= uv_float <= 5:
            return "MODERATE", "#FFFF00"  # Yellow
        elif 5 <= uv_float <= 7:
            return "HIGH", "#FF7E00"  # Orange
        elif 7 <= uv_float <= 10:
            return "VERY HIGH", "#FF0000"  # Red
        else:
            return "EXTREME", "#8F3F97"  # Purple

    def get_humidity_state(self, humidity: float | None) -> tuple[str, str]:
        """Determine humidity state and color based on humidity value."""
        if humidity is None:
            return "N/A", "#FFFFFF"  # White
        humidity_float = float(humidity)
        if 0 <= humidity_float <= 30:
            return "LOW", "#3EC1EC"  # Sky Blue
        elif 30 <= humidity_float <= 50:
            return "NORMAL", "#39FF14"  # Neon Green
        elif 50 <= humidity_float <= 60:
            return "SLIGHTLY HIGH", "#FFFF00"  # Yellow
        elif 60 <= humidity_float <= 70:
            return "HIGH", "#FF7E00"  # Orange
        else:
            return "VERY HIGH", "#FF0000"  # Red

    def update_static_elements(self) -> None:
        """Update static display elements such as date, time, sunrise, and sunset."""
        datetime_info = self.get_datetime_info()
        sun_info = self.get_sun_info()

        self.bg_canvas.itemconfig(self.current_day_value, text=datetime_info['day'])
        self.bg_canvas.itemconfig(self.current_date_value, text=datetime_info['date'])
        self.bg_canvas.itemconfig(self.current_time_value, text=datetime_info['time'])
        
        self.bg_canvas.itemconfig(self.sunrise_value, text=f"↑{sun_info['sunrise']}")
        self.bg_canvas.itemconfig(self.sunset_value, text=f"↓{sun_info['sunset']}")

        self.root.after(60000, self.update_static_elements)

    def update_display(self) -> None:
        """Update all sensor display widgets with the latest sensor data."""
        try:
            # Update sensor values
            for sensor_name, config in self.sensor_configs.items():
                try:
                    value = config['parser'](self.sensor_data)
                    widget = getattr(self, config['widget'])
                    formatted_value = config['display_format'](value)
                    self.bg_canvas.itemconfig(widget, text=formatted_value)
                except Exception as e:
                    self.log(f"Error updating {sensor_name}: {e}", level=logging.ERROR)
                    self.bg_canvas.itemconfig(getattr(self, config['widget']), text="--")
            
            # Update states with colors
            self.update_state_displays()
            
        except Exception as e:
            self.log(f"Display update error: {e}", level=logging.ERROR)
        
        # Schedule next update
        self.root.after(self.config['gui']['update_interval'], self.update_display)

    def update_state_displays(self) -> None:
        """Update state widgets (humidity, UV, AQI) with appropriate text and color."""
        try:
            # Humidity state
            humidity = self.sensor_data.get('humidity')
            # if humidity is not None:
            if humidity is None or not isinstance(humidity, (int, float)):
                hum_state, hum_color = "N/A", "#FFFFFF"
            else:
                hum_state, hum_color = self.get_humidity_state(humidity)
            self.bg_canvas.itemconfig(self.humidity_value, fill=hum_color)
            self.bg_canvas.itemconfig(self.humidity_state_value, text=hum_state, fill=hum_color)
        
            # UV state
            uv = self.sensor_data.get('uv_index')
            if uv is None or not isinstance(uv, (int, float)):
                uv_state, uv_color = "N/A", "#FFFFFF"
            else:
                uv_state, uv_color = self.get_uv_state(uv)
            self.bg_canvas.itemconfig(self.uv_value, fill=uv_color)
            self.bg_canvas.itemconfig(self.uv_state_value, text=uv_state, fill=uv_color)
            
            # AQI state
            pm2_5 = self.sensor_data.get('pm2_5')
            if pm2_5 is None or not isinstance(pm2_5, (int, float)):
                aqi_state, aqi_color = "N/A", "#FFFFFF"
            else:
                aqi = self.calculate_aqi(pm2_5)
                aqi_state, aqi_color = self.get_aqi_state(aqi)
            self.bg_canvas.itemconfig(self.aqi_value, fill=aqi_color)
            self.bg_canvas.itemconfig(self.aqi_state_value, text=aqi_state, fill=aqi_color)
                
        except Exception as e:
            self.log(f"Error updating state displays: {e}", level=logging.ERROR)

    # --- GUI Utility Methods ---
    def toggle_mapping_mode(self, event=None) -> None:
        """Toggle coordinate mapping mode for GUI widget placement."""
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

    def show_coordinates(self, event) -> None:
        """Display the coordinates of a mouse click on the canvas for mapping mode."""
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

    # --- Shutdown and Misc ---
    def shutdown(self) -> None:
        """Perform a clean shutdown of the system, stopping threads and closing Modbus."""
        self.log("Shutting down weather station system")
        self.running = False
        
        if hasattr(self, 'sensor_thread'):
            self.sensor_thread.join(timeout=2)
        if hasattr(self, 'csv_thread'):
            self.csv_thread.join(timeout=2)
        
        if hasattr(self, 'modbus_client') and self.modbus_client.connected:
            self.modbus_client.close()
        
        self.root.quit()

    def get_sun_info(self) -> dict:
        """Get sunrise and sunset times for the current date from the sun data CSV file."""
        try:
            # Get current date in MM-DD format
            current_date = datetime.now().strftime('%m-%d')
            
            # Read sun data from CSV file
            sun_data_file = os.path.join('awos_assit_code', 'karachi_sun_data.csv')
            
            if not os.path.exists(sun_data_file):
                self.log(f"Sun data file not found: {sun_data_file}", level=logging.WARNING)
                return {
                    'sunrise': '06:00',
                    'sunset': '18:00'
                }
            
            with open(sun_data_file, 'r') as file:
                csv_reader = csv.DictReader(file)
                for row in csv_reader:
                    if row['date'] == current_date:
                        return {
                            'sunrise': row['sunrise'],
                            'sunset': row['sunset']
                        }
            
            self.log(f"No sun data found for date: {current_date}", level=logging.WARNING)
            return {
                'sunrise': '06:00',
                'sunset': '18:00'
            }
            
        except Exception as e:
            self.log(f"Error reading sun data: {e}", level=logging.ERROR)
            return {
                'sunrise': '06:00',
                'sunset': '18:00'
            }

    def force_update(self) -> None:
        """Force an immediate update of all display elements and log the refresh."""
        self.update_display()
        self.update_static_elements()
        self.log("Display manually refreshed", level=logging.INFO)

    def check_log_rotation(self) -> None:
        """Periodically check and rotate log files if needed."""
        self.check_and_rotate_logs()
        # Schedule next check
        self.root.after(3600000, self.check_log_rotation)  # Check every hour

if __name__ == "__main__":
    try:
        root = tk.Tk()
        root.wm_attributes("-topmost", True)  # Keep window always on top
        app = WeatherStationSystem(root)
        root.protocol("WM_DELETE_WINDOW", app.shutdown)
        root.mainloop()
    except Exception as e:
        print(f"Critical error: {e}")
        raise