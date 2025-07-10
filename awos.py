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
from typing import Dict, Tuple, Optional, Union

# Disable DecompressionBombWarning
Image.MAX_IMAGE_PIXELS = None
warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)

# Add path for awos_assit_code
sys.path.append(os.path.join(os.path.dirname(__file__), 'awos_assit_code'))

class WeatherStationSystem:
    def __init__(self, root: tk.Tk) -> None:
        """Initialize the WeatherStationSystem with dual GUI support."""
        self.root = root
        self.root.title("Weather Station Dashboard")
        
        # Initialize logger first
        self.logger = logging.getLogger('WeatherStation')
        self.logger.setLevel(logging.INFO)
        
        try:
            # Initialize system in proper order
            self.load_config()
            self.setup_logging()  # Now properly configured logger exists
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
            self.root.bind('<F5>', lambda e: self.force_update())
            self.root.bind('<Tab>', lambda e: self.force_gui_switch())
            self.root.bind('<space>', self.toggle_pause_on_current_gui)  # Add this line
            
            # Schedule periodic tasks
            self.root.after(1000, self._keep_focus)
            self.root.after(3600000, self.check_log_rotation)
            self.toggle_interval = self.config['gui'].get('toggle_interval', 10000)
            self._toggle_timer = None
            self.start_gui_toggle()
            
        except Exception as e:
            print(f"Initialization error: {e}")
            raise

    def load_config(self) -> None:
        """Load configuration with defaults for dual GUI support."""
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
                'log_rotate_size': 1000000,
                'log_backup_count': 5
            },
            'gui': {
                'update_interval': 1000,
                'gui1_image': 'gui1_image.jpg',
                'gui2_image': 'gui2_image.JPG',
                'font': 'Digital-7',
                'rain_reset_threshold': 0.1,
                'rain_reset_time': 12,
                'toggle_interval': 10000
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
                            # Clean up comments in values
                            value = value.split('#')[0].strip()
                            try:
                                if isinstance(self.config[section][key], int):
                                    self.config[section][key] = int(value)
                                elif isinstance(self.config[section][key], float):
                                    self.config[section][key] = float(value)
                                else:
                                    self.config[section][key] = value
                            except ValueError:
                                print(f"Warning: Invalid config value for {section}.{key}: {value}")
                                continue
        except Exception as e:
            print(f"Config load error: {e}. Using defaults.")  # Can't use logger yet

    def setup_logging(self) -> None:
        """Set up logging with daily rotation and retention."""
        try:
            logs_dir = "logs"
            os.makedirs(logs_dir, exist_ok=True)
            current_date = datetime.now().strftime('%Y-%m-%d')
            log_file = os.path.join(logs_dir, f"weather_station_{current_date}.log")

            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(file_handler)

            if self.config['logging'].get('debug', False):
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.DEBUG)
                self.logger.addHandler(console_handler)

            self.cleanup_old_logs(logs_dir)
            self.log("Weather Station System Initialized")
        except Exception as e:
            print(f"Error setting up logging: {e}")
            raise


    def cleanup_old_logs(self, logs_dir: str) -> None:
        """Remove log files older than 7 days."""
        try:
            current_date = datetime.now().date()
            for filename in os.listdir(logs_dir):
                if filename.startswith("weather_station_") and filename.endswith(".log"):
                    try:
                        file_date_str = filename[16:-4]  # Extract date from filename
                        file_date = datetime.strptime(file_date_str, '%Y-%m-%d').date()
                        if (current_date - file_date).days > 7:
                            os.remove(os.path.join(logs_dir, filename))
                    except (ValueError, OSError) as e:
                        print(f"Error processing log file {filename}: {e}")
        except Exception as e:
            print(f"Error cleaning up old logs: {e}")

    def check_and_rotate_logs(self) -> None:
        """Rotate log files if the date has changed."""
        try:
            current_date = datetime.now().strftime('%Y-%m-%d')
            current_log_file = os.path.join("logs", f"weather_station_{current_date}.log")
            
            for handler in self.logger.handlers[:]:
                if isinstance(handler, logging.FileHandler):
                    if handler.baseFilename != current_log_file:
                        self.logger.removeHandler(handler)
                        handler.close()
                        new_handler = logging.FileHandler(current_log_file)
                        new_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
                        self.logger.addHandler(new_handler)
                        self.cleanup_old_logs("logs")
        except Exception as e:
            print(f"Error rotating logs: {e}")

    def log(self, message: str, level: int = logging.INFO) -> None:
        """Log a message with specified level."""
        self.logger.log(level, message)

    def init_data_structures(self) -> None:
        """Initialize data storage structures."""
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

        os.makedirs("csv_data", exist_ok=True)

    def cleanup_old_csv(self) -> None:
        """Remove CSV files older than 7 days."""
        try:
            current_date = datetime.now().date()
            for filename in os.listdir(self.csv_dir):
                if filename.startswith("weather_data_") and filename.endswith(".csv"):
                    try:
                        file_date = datetime.strptime(filename[12:-4], '%Y-%m-%d').date()
                        if (current_date - file_date).days > 7:
                            os.remove(os.path.join(self.csv_dir, filename))
                    except (ValueError, OSError) as e:
                        self.log(f"Error processing CSV {filename}: {e}", logging.ERROR)
        except Exception as e:
            self.log(f"Error cleaning CSV: {e}", logging.ERROR)


    def load_background_images(self, width: int, height: int) -> None:
        """Load and resize background images for both GUIs."""
        try:
            # Get base directory and image paths
            base_dir = os.path.dirname(os.path.abspath(__file__))
            image_dir = os.path.join(base_dir, 'images')
            
            # GUI 1 background
            gui1_path = os.path.join(image_dir, self.config['gui']['gui1_image'])
            gui1_img = Image.open(gui1_path)
            self.gui1_bg = ImageTk.PhotoImage(
                gui1_img.resize((width, height), Image.Resampling.LANCZOS))
            self.gui1_canvas.create_image(0, 0, image=self.gui1_bg, anchor='nw')
            
            # GUI 2 background
            gui2_path = os.path.join(image_dir, self.config['gui']['gui2_image'])
            gui2_img = Image.open(gui2_path)
            self.gui2_bg = ImageTk.PhotoImage(
                gui2_img.resize((width, height), Image.Resampling.LANCZOS))
            self.gui2_canvas.create_image(0, 0, image=self.gui2_bg, anchor='nw')
            
        except FileNotFoundError as e:
            self.log(f"Background image not found: {e}", level=logging.ERROR)
        except Exception as e:
            self.log(f"Error loading background images: {e}", level=logging.ERROR)


    def setup_gui(self) -> None:
        """Set up dual GUI system with two canvases."""
        self.root.attributes('-fullscreen', True)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # Main frame
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill='both', expand=True)

        # Create both canvases
        self.gui1_canvas = tk.Canvas(
            self.main_frame, 
            width=screen_width, 
            height=screen_height, 
            highlightthickness=0,
            bg='black'
        )
        self.gui2_canvas = tk.Canvas(
            self.main_frame, 
            width=screen_width, 
            height=screen_height, 
            highlightthickness=0,
            bg='black'
        )
        
        # Load background images
        self.load_background_images(screen_width, screen_height)

        # Pack canvases - use pack_forget() and pack() for switching
        self.gui1_canvas.pack(fill='both', expand=True)
        self.gui2_canvas.pack_forget()  # Initially hidden
        self.current_gui = 1  # Start with GUI-1 visible

        # Create widgets for both GUIs
        self.create_display_widgets()

    def create_display_widgets(self) -> None:
        """Create and configure all display widgets."""
        # Define all widget configurations in one place
        self.widget_configs = {
            # Common widgets for both GUIs
            'common': {
                'time': {
                    'size': 80,
                    'color': '#FFFFFF',
                    'position': (1530, 80),
                    'anchor': 'center',
                    'placeholder': 'TIME'
                },
                'date': {
                    'size': 80,
                    'color': '#FFFFFF',
                    'position': (330, 80),
                    'anchor': 'center',
                    'placeholder': 'DATE'
                },
                'day': {
                    'size': 80,
                    'color': '#FFFFFF',
                    'position': (980, 80),
                    'anchor': 'center',
                    'placeholder': 'DAY'
                }
            },
            # GUI-1 specific widgets
            'gui1': {
                'temperature': {
                    'size': 100,
                    'color': '#FFFFFF',
                    'position': (350, 250),
                    'anchor': 'center',
                    'placeholder': 'TM'
                },
                'humidity': {
                    'size': 100,
                    'color': '#FFFFFF',
                    'position': (980, 250),
                    'anchor': 'center',
                    'placeholder': 'HM'
                },
                'wind_speed': {
                    'size': 100,
                    'color': '#FFFFFF',
                    'position': (1600, 250),
                    'anchor': 'center',
                    'placeholder': 'WS'
                },
                'wind_direction': {
                    'size': 60,
                    'color': '#FFFFFF',
                    'position': (1600, 595),
                    'anchor': 'center',
                    'placeholder': 'WD'
                }
            },
            # GUI-2 specific widgets
            'gui2': {
                'uv': {
                    'size': 100,
                    'color': '#FFFFFF',
                    'position': (350, 890),
                    'anchor': 'center',
                    'placeholder': 'UV'
                },
                'aqi': {
                    'size': 100,
                    'color': '#FFFFFF',
                    'position': (1600, 890),
                    'anchor': 'center',
                    'placeholder': 'AQI'
                },
                'pressure': {
                    'size': 100,
                    'color': '#FFFFFF',
                    'position': (350, 595),
                    'anchor': 'center',
                    'placeholder': 'PS'
                },
                'rain': {
                    'size': 80,
                    'color': '#FFFFFF',
                    'position': (940, 595),
                    'anchor': 'center',
                    'placeholder': 'RF'
                },
                'sunrise': {
                    'size': 110,
                    'color': '#FFFFFF',
                    'position': (1150, 780),
                    'anchor': 'ne',
                    'placeholder': 'SR'
                },
                'sunset': {
                    'size': 110,
                    'color': '#FFFFFF',
                    'position': (1150, 910),
                    'anchor': 'ne',
                    'placeholder': 'SS'
                }
            }
        }

        # Create widgets based on configurations
        font_name = self.config['gui'].get('font', 'Arial')
        
        # Create common widgets for both GUIs
        self.common_widgets = {}
        for name, config in self.widget_configs['common'].items():
            # Create for GUI 1
            self.common_widgets[f"{name}_gui1"] = self.create_widget(
                self.gui1_canvas,
                config['position'],
                config['size'],
                config['anchor'],
                config['color'],
                config['placeholder']
            )
            # Create for GUI 2
            self.common_widgets[f"{name}_gui2"] = self.create_widget(
                self.gui2_canvas,
                config['position'],
                config['size'],
                config['anchor'],
                config['color'],
                config['placeholder']
            )

        # Create GUI-1 specific widgets
        self.gui1_widgets = {}
        for name, config in self.widget_configs['gui1'].items():
            self.gui1_widgets[name] = self.create_widget(
                self.gui1_canvas,
                config['position'],
                config['size'],
                config['anchor'],
                config['color'],
                config['placeholder']
            )

        # Create GUI-2 specific widgets
        self.gui2_widgets = {}
        for name, config in self.widget_configs['gui2'].items():
            self.gui2_widgets[name] = self.create_widget(
                self.gui2_canvas,
                config['position'],
                config['size'],
                config['anchor'],
                config['color'],
                config['placeholder']
            )
        

    def start_gui_toggle(self) -> None:
        """Start the automatic GUI toggle timer."""
        self._toggle_timer = self.root.after(self.toggle_interval, self.toggle_gui)

    def toggle_gui(self, immediate: bool = False) -> None:
        """Toggle between GUIs with optional immediate switch."""
        if self._toggle_timer:
            self.root.after_cancel(self._toggle_timer)
        
        if immediate or self.current_gui == 1:
            self.gui1_canvas.pack_forget()
            self.gui2_canvas.pack(fill='both', expand=True)
            self.current_gui = 2
        else:
            self.gui2_canvas.pack_forget()
            self.gui1_canvas.pack(fill='both', expand=True)
            self.current_gui = 1
        
        self.log(f"Switched to GUI-{self.current_gui}")
        self._toggle_timer = self.root.after(self.toggle_interval, self.toggle_gui)
        
    
    def create_widget(self, canvas: tk.Canvas, pos: Tuple[int, int], 
                 size: int, anchor: str = 'center',
                 color: str = '#FFFFFF', placeholder: str = '--') -> int:
        """Create a widget with specified configuration."""
        return canvas.create_text(
            pos[0], pos[1],
            text=placeholder,
            font=('Arial', size, 'bold'),  # Changed to Arial font
            # font=(self.config['gui'].get('font', 'Digital-7'), size, 'bold'),
            fill=color,
            anchor=anchor
        )

    def update_display(self) -> None:
        """Update widgets based on current active GUI."""
        try:
            # Update common widgets (time/date)
            datetime_info = self.get_datetime_info()
            for widget, value in zip(['day', 'date', 'time'], 
                                   [datetime_info['day'], datetime_info['date'], datetime_info['time']]):
                self.gui1_canvas.itemconfig(self.common_widgets[widget], text=value)
                self.gui2_canvas.itemconfig(self.common_widgets[widget], text=value)

            if self.current_gui == 1:
                self.update_gui1_widgets()
            else:
                self.update_gui2_widgets()
                
            self.root.after(self.config['gui']['update_interval'], self.update_display)
            
        except Exception as e:
            self.log(f"Error updating display: {e}", level=logging.ERROR)

    def update_gui1_widgets(self) -> None:
        """Update widgets for GUI-1 (basic metrics)."""
        try:
            for sensor_type in ['temperature', 'humidity', 'wind_speed', 'wind_direction']:
                config = self.sensor_configs[sensor_type]
                value = config['parser'](self.sensor_data)
                formatted_value = config['display_format'](value)
                
                self.gui1_canvas.itemconfig(
                    self.gui1_widgets[sensor_type],
                    text=formatted_value
                )
        except Exception as e:
            self.log(f"Error updating GUI-1 widgets: {e}", level=logging.ERROR)

    def update_gui2_widgets(self) -> None:
        """Update widgets for GUI-2 (advanced metrics)."""
        try:
            # Update regular sensors
            for sensor_type in ['uv', 'aqi', 'pressure', 'rain']:
                config = self.sensor_configs[sensor_type]
                value = config['parser'](self.sensor_data)
                formatted_value = config['display_format'](value)
                
                self.gui2_canvas.itemconfig(
                    self.gui2_widgets[sensor_type],
                    text=formatted_value
                )
            
            # Update sun info separately since it's not sensor data
            sun_info = self.get_sun_info()
            self.gui2_canvas.itemconfig(
                self.gui2_widgets['sunrise'],
                text=f"↑{sun_info['sunrise']}"
            )
            self.gui2_canvas.itemconfig(
                self.gui2_widgets['sunset'],
                text=f"↓{sun_info['sunset']}"
            )
        except Exception as e:
            self.log(f"Error updating GUI-2 widgets: {e}", level=logging.ERROR)

    def force_gui_switch(self, event=None) -> None:
        """Manually trigger GUI switch on Tab press."""
        # Cancel existing timer to prevent conflicts
        if self._toggle_timer:
            self.root.after_cancel(self._toggle_timer)
            self._toggle_timer = None

        # Switch to opposite GUI
        if self.current_gui == 1:
            self.gui1_canvas.pack_forget()
            self.gui2_canvas.pack(fill='both', expand=True)
            self.current_gui = 2
        else:
            self.gui2_canvas.pack_forget()
            self.gui1_canvas.pack(fill='both', expand=True)
            self.current_gui = 1

        self.log(f"Manually switched to GUI-{self.current_gui}")
        
        # Restart the toggle timer
        self._toggle_timer = self.root.after(self.toggle_interval, self.toggle_gui)

    def pause_gui_toggle(self) -> None:
        """Temporarily pause GUI toggling."""
        if self._toggle_timer:
            self.root.after_cancel(self._toggle_timer)
            self._toggle_timer = None

    def resume_gui_toggle(self) -> None:
        """Resume GUI toggling."""
        if not self._toggle_timer:
            self._toggle_timer = self.root.after(self.toggle_interval, self.toggle_gui)

    def init_modbus(self) -> None:
        """Initialize Modbus serial client."""
        self.modbus_client = ModbusSerialClient(
            port=self.config['modbus']['port'],
            baudrate=self.config['modbus']['baudrate'],
            parity=self.config['modbus']['parity'],
            stopbits=self.config['modbus']['stopbits'],
            timeout=self.config['modbus']['timeout']
        )
        if not self.modbus_client.connect():
            self.log("Modbus connection failed", logging.ERROR)


    def init_sensor_config(self) -> None:
        """Set up sensor parsing configurations."""
        self.sensor_configs = {
            'temperature': {
                'parser': lambda data: data.get('temperature'),
                'display_format': lambda v: f"{v:.1f}" if v is not None else "37.5",
                'widget': 'temperature_value',
                'size': 100
            },
            'humidity': {
                'parser': lambda data: data.get('humidity'),
                'display_format': lambda v: f"{v:.1f}%" if v is not None else "100",
                'widget': 'humidity_value',
                'size': 100
            },
            'wind_speed': {
                'parser': lambda data: data.get('wind_speed', 0.0) * 3.6 if data.get('wind_speed') is not None else None,
                'display_format': lambda v: f"{v:.1f}" if v is not None else "25.0",
                'widget': 'wind_speed_value',
                'size': 80
            },
            'wind_direction': {
                'parser': lambda data: data.get('wind_dir_degrees'),
                'display_format': lambda v: f"{v}°" if v is not None else "360",
                'widget': 'wind_direction_value',
                'size': 80
            },
            'pressure': {
                'parser': lambda data: data.get('pressure'),
                'display_format': lambda v: f"{v:.1f}" if v is not None else "PS",
                'widget': 'pressure_value',
                'size': 100
            },
            'rain': {
                'parser': lambda data: self.process_rainfall(data.get('rainfall')),
                'display_format': lambda v: f"{v:.1f}" if v is not None else "RF",
                'widget': 'rain_value',
                'size': 80
            },
            'uv': {
                'parser': lambda data: data.get('uv_index'),
                'display_format': lambda v: f"{v:.2f}" if v is not None else "UV",
                'widget': 'uv_value',
                'size': 100
            },
            'aqi': {
                'parser': lambda data: self.calculate_aqi(data.get('pm2_5')),
                'display_format': lambda v: f"{v:.0f}" if v is not None else "AQI",
                'widget': 'aqi_value',
                'size': 100
            }
        }

    def read_environment_sensor(self) -> dict:
        """Read temperature, humidity, and pressure."""
        try:
            result = self.modbus_client.read_holding_registers(
                address=0x0000, count=3, slave=self.config['sensors']['environment'])
            if result.isError():
                return {'temperature': 0.0, 'humidity': 0.0, 'pressure': 0.0}
            return {
                'temperature': result.registers[0] / 10.0,
                'humidity': result.registers[1] / 10.0,
                'pressure': result.registers[2] / 10.0
            }
        except Exception as e:
            self.log(f"Environment sensor error: {e}", logging.ERROR)
            return {'temperature': 0.0, 'humidity': 0.0, 'pressure': 0.0}

    def read_uv_sensor(self) -> dict:
        """Read UV index from sensor."""
        try:
            result = self.modbus_client.read_holding_registers(
                address=0x0000, count=1, slave=self.config['sensors']['uv'])
            return {'uv_index': result.registers[0] / 100.0} if not result.isError() else {'uv_index': 0.0}
        except Exception as e:
            self.log(f"UV sensor error: {e}", logging.ERROR)
            return {'uv_index': 0.0}

    def read_aqi_sensor(self) -> dict:
        """Read AQI data from CSV file."""
        try:
            current_time = datetime.now()
            csv_path = os.path.join(os.path.dirname(__file__), 'aqi', 'karachi_aqi_data_with_pst.csv')
            
            if not os.path.exists(csv_path):
                return {'pm2_5': 0.0}
                
            df = pd.read_csv(csv_path)
            df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
            closest_row = df.iloc[(df['date'] - current_time).abs().argsort()[0]]
            
            return {
                'co2': float(closest_row['carbon_dioxide']),
                'pm2_5': float(closest_row['pm2_5']),
                'pm10': float(closest_row['pm10']),
                'carbon_monoxide': float(closest_row['carbon_monoxide']),
                'nitrogen_dioxide': float(closest_row['nitrogen_dioxide']),
                'sulphur_dioxide': float(closest_row['sulphur_dioxide']),
                'ozone': float(closest_row['ozone'])
            }
        except Exception as e:
            self.log(f"AQI sensor error: {e}", logging.ERROR)
            return {'pm2_5': 0.0}

    def read_wind_speed(self) -> dict:
        """Read wind speed from sensor."""
        try:
            result = self.modbus_client.read_holding_registers(
                address=0x0000, count=1, slave=self.config['sensors']['wind_speed'])
            return {'wind_speed': result.registers[0] / 10.0} if not result.isError() else {'wind_speed': 0.0}
        except Exception as e:
            self.log(f"Wind speed error: {e}", logging.ERROR)
            return {'wind_speed': 0.0}

    def read_wind_direction(self) -> dict:
        """Read wind direction from sensor."""
        try:
            result = self.modbus_client.read_holding_registers(
                address=0x0000, count=3, slave=self.config['sensors']['wind_direction'])
            if result.isError():
                return None
                
            avg_value = (result.registers[0] + result.registers[2]) / 2.0
            wind_dir_degrees = round(avg_value / 10.0)
            
            if 0 <= wind_dir_degrees <= 360:
                return {
                    'wind_dir_degrees': wind_dir_degrees,
                    'wind_dir_cardinal': self._degrees_to_cardinal(wind_dir_degrees)
                }
            return None
        except Exception as e:
            self.log(f"Wind direction error: {e}", logging.ERROR)
            return None

    def _degrees_to_cardinal(self, degrees: float) -> str:
        """Convert degrees to cardinal direction."""
        directions = [
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
        ]
        return directions[round(degrees / (360. / len(directions))) % len(directions)]

    def read_rainfall(self) -> dict:
        """Read rainfall from sensor."""
        try:
            result = self.modbus_client.read_holding_registers(
                address=0, count=1, slave=self.config['sensors']['rainfall'])
            return {'rainfall': result.registers[0] / 10.0} if not result.isError() else None
        except Exception as e:
            self.log(f"Rainfall sensor error: {e}", logging.ERROR)
            return None

    def store_daily_rainfall(self, total: float) -> None:
        """Store daily rainfall totals."""
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
            self.log(f"Error storing rainfall: {e}", logging.ERROR)

    def process_rainfall(self, current_rain: float) -> float:
        """Process rainfall data with daily reset."""
        if current_rain is None:
            return None

        now = datetime.now()
        if not hasattr(self, 'last_rain_reset_day') or now.day != self.last_rain_reset_day:
            if hasattr(self, 'daily_rain_total'):
                self.store_daily_rainfall(self.daily_rain_total)
            self.last_rain_reset_day = now.day
            self.daily_rain_total = 0
            self.last_rain_value = current_rain

        rain_increment = current_rain - self.last_rain_value
        if rain_increment >= 0:
            self.daily_rain_total += rain_increment
            self.last_rain_value = current_rain
        else:
            self.log("Rain sensor reset detected", logging.WARNING)
            self.last_rain_value = current_rain

        return self.daily_rain_total

    def calculate_aqi(self, pm2_5: float) -> float:
        """Calculate AQI from PM2.5 value."""
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

    def start_threads(self) -> None:
        """Start sensor and CSV writer threads."""
        self.running = True
        self.sensor_thread = threading.Thread(target=self.sensor_reader_loop, daemon=True)
        self.csv_thread = threading.Thread(target=self.csv_writer_loop, daemon=True)
        self.sensor_thread.start()
        self.csv_thread.start()

    def sensor_reader_loop(self) -> None:
        """Main sensor reading loop."""
        last_csv_time = time.time()
        while self.running:
            try:
                if not self.modbus_client.connect():
                    time.sleep(5)
                    continue
                
                current_data = {'timestamp': datetime.now().isoformat()}
                
                # Read all sensors
                for sensor_name, reader in [
                    ('environment', self.read_environment_sensor),
                    ('uv', self.read_uv_sensor),
                    ('aqi', self.read_aqi_sensor),
                    ('wind_speed', self.read_wind_speed),
                    ('wind_direction', self.read_wind_direction),
                    ('rainfall', self.read_rainfall)
                ]:
                    try:
                        data = reader()
                        if data:
                            current_data.update(data)
                    except Exception as e:
                        self.log(f"Error reading {sensor_name}: {e}", logging.ERROR)
                
                self.sensor_data = current_data
                
                if time.time() - last_csv_time >= self.config['logging']['csv_interval']:
                    self.data_queue.put(current_data)
                    last_csv_time = time.time()
                    
                time.sleep(1)
            except Exception as e:
                self.log(f"Sensor read error: {e}", logging.ERROR)
                time.sleep(1)

    def csv_writer_loop(self) -> None:
        """Write sensor data to CSV files."""
        while self.running:
            try:
                data = self.data_queue.get(timeout=1)
                current_date = datetime.now().strftime('%Y-%m-%d')
                csv_file = os.path.join(self.csv_dir, f"weather_data_{current_date}.csv")
                
                if not os.path.exists(csv_file):
                    with open(csv_file, 'w') as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            'timestamp', 'temperature', 'humidity', 'pressure', 
                            'uv_index', 'co2', 'pm2_5', 'pm10', 'wind_speed', 
                            'wind_dir_degrees', 'rainfall'
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
                        data.get('pm2_5', ''),
                        data.get('pm10', ''),
                        data.get('wind_speed', ''),
                        data.get('wind_dir_degrees', ''),
                        data.get('rainfall', '')
                    ])
            except queue.Empty:
                continue
            except Exception as e:
                self.log(f"CSV write error: {e}", logging.ERROR)

    def get_datetime_info(self) -> dict:
        """Get formatted date/time information."""
        now = datetime.now()
        return {
            'day': now.strftime('%A').upper(),
            'date': now.strftime('%d %b').replace(now.strftime('%b'), now.strftime('%b').upper()) + now.strftime(' %Y'),
            'time': now.strftime('%H:%M')
        }

    def get_sun_info(self) -> dict:
        """Get sunrise/sunset times from CSV."""
        try:
            current_date = datetime.now().strftime('%m-%d')
            sun_data_file = os.path.join('awos_assit_code', 'karachi_sun_data.csv')
            
            if not os.path.exists(sun_data_file):
                return {'sunrise': '06:00', 'sunset': '18:00'}
                
            with open(sun_data_file, 'r') as file:
                csv_reader = csv.DictReader(file)
                for row in csv_reader:
                    if row['date'] == current_date:
                        return {'sunrise': row['sunrise'], 'sunset': row['sunset']}
                    
            return {'sunrise': '06:00', 'sunset': '18:00'}
        except Exception as e:
            self.log(f"Error reading sun data: {e}", logging.ERROR)
            return {'sunrise': '06:00', 'sunset': '18:00'}

    def update_static_elements(self) -> None:
        """Update static display elements on both GUIs simultaneously."""
        datetime_info = self.get_datetime_info()
        sun_info = self.get_sun_info()

        # Update time/date elements on both GUIs
        self.gui1_canvas.itemconfig(self.common_widgets['day_gui1'], text=datetime_info['day'])
        self.gui1_canvas.itemconfig(self.common_widgets['date_gui1'], text=datetime_info['date'])
        self.gui1_canvas.itemconfig(self.common_widgets['time_gui1'], text=datetime_info['time'])
        
        self.gui2_canvas.itemconfig(self.common_widgets['day_gui2'], text=datetime_info['day'])
        self.gui2_canvas.itemconfig(self.common_widgets['date_gui2'], text=datetime_info['date'])
        self.gui2_canvas.itemconfig(self.common_widgets['time_gui2'], text=datetime_info['time'])

        # Update sun info on GUI 2 without arrows
        self.gui2_canvas.itemconfig(self.gui2_widgets['sunrise'], text=sun_info['sunrise'])
        self.gui2_canvas.itemconfig(self.gui2_widgets['sunset'], text=sun_info['sunset'])

        # Schedule next update in 60 seconds
        self.root.after(60000, self.update_static_elements)

    def toggle_mapping_mode(self, event=None) -> None:
        """Toggle coordinate mapping debug mode."""
        self.mapping_mode = not self.mapping_mode
        if self.mapping_mode:
            self.gui1_canvas.bind('<Button-1>', self.show_coordinates)
            self.gui2_canvas.bind('<Button-1>', self.show_coordinates)
            self.coordinate_text = self.gui1_canvas.create_text(
                10, 10, text="Mapping Mode ON", fill='red', anchor='nw')
        else:
            self.gui1_canvas.unbind('<Button-1>')
            self.gui2_canvas.unbind('<Button-1>')
            if hasattr(self, 'coordinate_text'):
                self.gui1_canvas.delete(self.coordinate_text)

    def show_coordinates(self, event) -> None:
        """Display click coordinates in mapping mode."""
        x, y = event.x, event.y
        marker = event.widget.create_oval(x-2, y-2, x+2, y+2, fill='red')
        text = event.widget.create_text(x+10, y-10, text=f"({x}, {y})", fill='red', anchor='w')
        self.root.after(2000, lambda: [event.widget.delete(marker), event.widget.delete(text)])

    def force_update(self) -> None:
        """Force immediate display update."""
        self.update_display()
        self.update_static_elements()
        self.log("Manual refresh triggered", logging.INFO)

    def check_log_rotation(self) -> None:
        """Periodic log rotation check."""
        self.check_and_rotate_logs()
        self.root.after(3600000, self.check_log_rotation)

    def shutdown(self) -> None:
        """Clean shutdown with proper cleanup."""
        if hasattr(self, '_toggle_timer'):
            self.root.after_cancel(self._toggle_timer)
        
        self.running = False
        
        if hasattr(self, 'sensor_thread'):
            self.sensor_thread.join(timeout=2)
        if hasattr(self, 'csv_thread'):
            self.csv_thread.join(timeout=2)
        
        if hasattr(self, 'modbus_client') and self.modbus_client.connected:
            self.modbus_client.close()
        
        self.root.quit()

    def _keep_focus(self) -> None:
        """Maintain window focus."""
        self.root.lift()
        self.root.after(1000, self._keep_focus)
        
    def toggle_pause_on_current_gui(self, event=None) -> None:
        """Toggle pause/resume on current GUI display."""
        if hasattr(self, '_toggle_timer'):
            if self._toggle_timer:  # If timer exists, we're currently toggling
                self.root.after_cancel(self._toggle_timer)
                self._toggle_timer = None
                self.log(f"Display paused on GUI-{self.current_gui}")
            else:  # If timer is None, we're currently paused
                self._toggle_timer = self.root.after(self.toggle_interval, self.toggle_gui)
                self.log(f"Display toggling resumed from GUI-{self.current_gui}")

        
if __name__ == "__main__":
    try:
        root = tk.Tk()
        root.wm_attributes("-topmost", True)
        app = WeatherStationSystem(root)
        root.protocol("WM_DELETE_WINDOW", app.shutdown)
        root.mainloop()
    except Exception as e:
        print(f"Critical error: {e}")
        raise
