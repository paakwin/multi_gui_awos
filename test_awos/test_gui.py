#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import time
from datetime import datetime, timedelta
import random
import logging

class WeatherStationSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("Weather Station Dashboard")
        self.root.attributes('-fullscreen', True)
        
        # Minimal configuration for GUI testing
        self.config = {
            'gui': {
                'update_interval': 1000,
                'background_image': './images/final_blank_resized.png',  # Make sure this exists
                'font': 'Digital-7'
            }
        }
        
        # Initialize with test data
        self.sensor_data = {
            'temperature': 25.0,
            'humidity': 45.0,
            'pressure': 1013.0,
            'uv_index': 5.0,
            'wind_speed': 15.0,
            'wind_direction': 180,
            'rainfall': 0.0,
            'aqi': 50.0,
            'timestamp': datetime.now().isoformat()
        }
        
        # Set custom date range (January 1 to February 28)
        self.custom_date = datetime(datetime.now().year, 1, 1)
        
        self.setup_gui()
        self.create_display_widgets()
        self.update_display()
        self.update_static_elements()
        
        # Bind keys
        self.root.bind('<Escape>', lambda e: self.shutdown())
        self.root.bind('<F5>', lambda e: self.force_update())

    def setup_gui(self):
        """Initialize the graphical user interface"""
        # Background image
        try:
            img = Image.open(self.config['gui']['background_image'])
            img = img.resize((self.root.winfo_screenwidth(), self.root.winfo_screenheight()))
            self.bg_image = ImageTk.PhotoImage(img)
            
            self.bg_canvas = tk.Canvas(
                self.root,
                width=self.root.winfo_screenwidth(),
                height=self.root.winfo_screenheight(),
                highlightthickness=0
            )
            self.bg_canvas.pack(fill='both', expand=True)
            self.bg_canvas.create_image(
                self.root.winfo_screenwidth()//2,
                self.root.winfo_screenheight()//2,
                image=self.bg_image,
                anchor='center'
            )
        except Exception as e:
            print(f"Failed to load background image: {e}")
            # Fallback to blank canvas if image fails
            self.bg_canvas = tk.Canvas(self.root, bg='black')
            self.bg_canvas.pack(fill='both', expand=True)

    def create_display_widgets(self):
        """Create all GUI display widgets with test positions"""
        widget_positions = {
            'temperature_value': (350, 250),
            'humidity_value': (980, 250),
            'humidity_state_value': (980, 350),
            'wind_speed_value': (1600, 250),
            'pressure_value': (350, 595),
            'rain_value': (940, 595),
            'wind_direction_value': (1600, 595),
            'uv_value': (350, 890),
            'uv_state_value': (350, 975),
            'aqi_value': (1600, 890),
            'aqi_state_value': (1600, 975),
            'current_day_value': (950, 55),
            'current_date_value': (330, 55),
            'current_time_value': (1550, 55),
            'sunrise_value': (950, 900),
            'sunset_value': (950, 1013)
        }
        
        font_name = self.config['gui'].get('font', 'Arial')
        for widget_name, pos in widget_positions.items():
            size = 100 if 'value' in widget_name and 'state' not in widget_name else 50
            if widget_name in ['current_day_value', 'current_date_value', 'current_time_value']:
                size = 55
            elif widget_name in ['sunrise_value', 'sunset_value']:
                size = 80
            elif widget_name == 'wind_direction_value':
                size = 60
            elif widget_name == 'rain_value':
                size = 80
                
            setattr(self, widget_name, self.bg_canvas.create_text(
                pos,
                text="--",
                font=(font_name, size, 'bold'),
                fill='#FFFFFF',
                anchor='center'
            ))

    def update_display(self):
        """Update all display elements with test data"""
        try:
            # Read all sensor data
            self.read_all_sensors()
            
            # Update all values with sensor data
            self.bg_canvas.itemconfig(self.temperature_value, text=f"{self.sensor_data['temperature']:.1f}")
            self.bg_canvas.itemconfig(self.humidity_value, text=f"{self.sensor_data['humidity']:.1f}%")
            self.bg_canvas.itemconfig(self.pressure_value, text=f"{self.sensor_data['pressure']:.1f}")
            self.bg_canvas.itemconfig(self.wind_speed_value, text=f"{self.sensor_data['wind_speed']:.1f}")
            self.bg_canvas.itemconfig(self.wind_direction_value, text=f"{self.sensor_data['wind_direction']}°")
            self.bg_canvas.itemconfig(self.rain_value, text=f"{self.sensor_data['rainfall']:.1f}")
            self.bg_canvas.itemconfig(self.uv_value, text=f"{self.sensor_data['uv_index']:.1f}")
            self.bg_canvas.itemconfig(self.aqi_value, text=f"{self.sensor_data['aqi']:.0f}")
            
            # Update states with colors
            self.update_state_displays()
            
        except Exception as e:
            print(f"Display update error: {e}")
        
        # Schedule next update
        self.root.after(self.config['gui']['update_interval'], self.update_display)

    def read_all_sensors(self):
        """Read all sensor data and update sensor_data dictionary"""
        # Read environment sensor
        env_data = self.read_environment_sensor()
        if env_data:
            self.sensor_data.update(env_data)
        
        # Read UV sensor
        uv_data = self.read_uv_sensor()
        if uv_data:
            self.sensor_data['uv_index'] = uv_data['uv_index']
        
        # Read AQI sensor
        aqi_data = self.read_aqi_sensor()
        if aqi_data:
            # Use PM2.5 as AQI indicator
            self.sensor_data['aqi'] = aqi_data['pm2_5'] * 10  # Scale to match AQI range
        
        # Read wind speed
        wind_speed_data = self.read_wind_speed()
        if wind_speed_data:
            self.sensor_data['wind_speed'] = wind_speed_data['wind_speed']
        
        # Read wind direction
        wind_dir_data = self.read_wind_direction()
        if wind_dir_data:
            self.sensor_data['wind_direction'] = wind_dir_data['wind_dir_degrees']
        
        # Read rainfall
        rain_data = self.read_rainfall()
        if rain_data:
            self.sensor_data['rainfall'] = rain_data['rainfall']
        
        # Update timestamp
        self.sensor_data['timestamp'] = datetime.now().isoformat()

    def read_environment_sensor(self):
        """Read temperature, humidity, and pressure with simulated values"""
        try:
            # Get current half-second interval
            interval = int(time.time() / 0.5)
            
            # Temperature (0-100°C) cycles every 120 intervals (60 seconds)
            temp = (interval % 120) / 120 * 100
            
            # Humidity (0-100%) cycles every 90 intervals (45 seconds)
            humidity = (interval % 90) / 90 * 100
            
            # Pressure (1000-1020 hPa) cycles every 60 intervals (30 seconds)
            pressure = 1000 + ((interval % 60) / 60 * 20)  # Fixed range to 20 hPa
            
            return {
                'temperature': round(temp, 1),
                'humidity': round(humidity, 1),
                'pressure': round(pressure, 1)
            }
        except Exception as e:
            self.log(f"Environment sensor error: {e}")
            return None

    def read_uv_sensor(self):
        """Read UV index with simulated values (0-12)"""
        try:
            # UV index cycles 0-12 every 80 intervals (40 seconds)
            uv_index = round((int(time.time() / 0.5) % 80) / 80 * 12, 1)
            return {'uv_index': uv_index}
        except Exception as e:
            self.log(f"UV sensor error: {e}")
            return {'uv_index': 0.0}

    def read_aqi_sensor(self):
        """Generate simulated AQI data (0-300)"""
        try:
            # AQI cycles 0-300 every 100 intervals (50 seconds)
            current_aqi = round((int(time.time() / 0.5) % 100) / 100 * 300, 1)
            
            return {
                'co2': round(400 + current_aqi * 2, 1),
                'pm2_5': round(current_aqi / 10, 1),
                'pm10': round(current_aqi / 8, 1),
                'carbon_monoxide': round(current_aqi / 100, 3),
                'nitrogen_dioxide': round(current_aqi / 15, 1),
                'sulphur_dioxide': round(current_aqi / 30, 1),
                'ozone': round(current_aqi / 20, 1)
            }
        except Exception as e:
            self.log(f"AQI sensor error: {e}")
            return None

    def read_wind_speed(self):
        """Read wind speed with simulated values (0-100 km/h)"""
        try:
            # Wind speed cycles 0-100 every 70 intervals (35 seconds)
            wind_speed = (int(time.time() / 0.5) % 70) / 70 * 100
            return {'wind_speed': round(wind_speed, 1)}
        except Exception as e:
            self.log(f"Wind speed sensor error: {e}")
            return {'wind_speed': 0.0}

    def read_wind_direction(self):
        """Read wind direction with simulated values (0-360°)"""
        try:
            # Wind direction cycles 0-360° every 50 intervals (25 seconds)
            degrees = (int(time.time() / 0.5) % 50) / 50 * 360
            
            if 0 <= degrees <= 360:
                return {
                    'wind_dir_degrees': int(degrees),
                    'wind_dir_cardinal': self._degrees_to_cardinal(degrees)
                }
            return None
        except Exception as e:
            self.log(f"Wind direction sensor error: {e}")
            return None

    def _degrees_to_cardinal(self, degrees):
        """Convert degrees to cardinal direction"""
        directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                      'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
        index = round(degrees / (360. / len(directions))) % len(directions)
        return directions[index]

    def read_rainfall(self):
        """Read rainfall with simulated values (0-100mm) in steps of 2"""
        try:
            # Rainfall cycles 0-100 every 120 intervals (60 seconds)
            rainfall = (int(time.time() / 0.5) % 120) / 120 * 100
            
            # Ensure steps of 2
            rainfall = (int(rainfall) // 2) * 2
            
            # 30% chance of no rain
            if random.random() < 0.3:
                rainfall = 0
                
            return {'rainfall': float(rainfall)}
        except Exception as e:
            self.log(f"Rainfall sensor error: {e}")
            return {'rainfall': 0.0}

    def get_aqi_state(self, aqi):
        """Determine AQI state and color"""
        if aqi is None:
            return "N/A", "#FFFFFF"  # White
        aqi_float = float(aqi)
        if 0.0 <= aqi_float <= 50.0:
            return "GOOD", "#39FF14"  # Neon Green
        elif 50.1 <= aqi_float <= 100.0:
            return "MODERATE", "#FFFF00"  # Yellow
        elif 100.1 <= aqi_float <= 150.0:
            return "UNHEALTHY", "#FF7E00"  # Orange
        elif 150.1 <= aqi_float <= 200.0:
            return "UNHEALTHY", "#FF0000"  # Red
        elif 200.1 <= aqi_float <= 300.0:
            return "VERY UNHEALTHY", "#8F3F97"  # Purple
        else:
            return "HAZARDOUS", "#7E0023"  # Dark Red

    def get_uv_state(self, uv):
        """Determine UV state and color"""
        if uv is None:
            return "N/A", "#FFFFFF"  # White
        uv_float = float(uv)
        if 0.0 <= uv_float <= 2.0:
            return "LOW", "#39FF14"  # Neon Green
        elif 2.1 <= uv_float <= 5.0:
            return "MODERATE", "#FFFF00"  # Yellow
        elif 5.1 <= uv_float <= 7.0:
            return "HIGH", "#FF7E00"  # Orange
        elif 7.1 <= uv_float <= 10.0:
            return "VERY HIGH", "#FF0000"  # Red
        else:
            return "EXTREME", "#8F3F97"  # Purple

    def get_humidity_state(self, humidity):
        """Determine humidity state and color"""
        if humidity is None:
            return "N/A", "#FFFFFF"  # White
        humidity_float = float(humidity)
        if 0.0 <= humidity_float <= 30.0:
            return "LOW", "#3EC1EC"  # Sky Blue
        elif 30.1 <= humidity_float <= 50.0:
            return "NORMAL", "#39FF14"  # Neon Green
        elif 50.1 <= humidity_float <= 60.0:
            return "SLIGHTLY HIGH", "#FFFF00"  # Yellow
        elif 60.1 <= humidity_float <= 70.0:
            return "HIGH", "#FF7E00"  # Orange
        else:
            return "VERY HIGH", "#FF0000"  # Red

    def update_state_displays(self):
        """Update state displays with colors based on sensor values"""
        # Update humidity display and state
        humidity = self.sensor_data['humidity']
        humidity_state, humidity_color = self.get_humidity_state(humidity)
        self.bg_canvas.itemconfig(self.humidity_value, fill=humidity_color)
        self.bg_canvas.itemconfig(self.humidity_state_value, text=humidity_state, fill=humidity_color)
        
        # Update UV index display and state
        uv = self.sensor_data['uv_index']
        uv_state, uv_color = self.get_uv_state(uv)
        self.bg_canvas.itemconfig(self.uv_value, fill=uv_color)
        self.bg_canvas.itemconfig(self.uv_state_value, text=uv_state, fill=uv_color)
        
        # Update AQI display and state
        aqi = self.sensor_data['aqi']
        aqi_state, aqi_color = self.get_aqi_state(aqi)
        self.bg_canvas.itemconfig(self.aqi_value, fill=aqi_color)
        self.bg_canvas.itemconfig(self.aqi_state_value, text=aqi_state, fill=aqi_color)

    def update_static_elements(self):
        """Update date, time with test values - now updates every second"""
        # Increment custom date by 1 day each time this is called
        self.custom_date += timedelta(days=1)
        
        # Reset to January 1 if we reach March 1
        if self.custom_date.month == 3 and self.custom_date.day == 1:
            self.custom_date = datetime(self.custom_date.year, 1, 1)
        
        # Calculate sunrise and sunset times based on date
        sunrise, sunset = self.calculate_sun_times(self.custom_date)
        
        self.bg_canvas.itemconfig(self.current_day_value, text=self.custom_date.strftime('%A').upper())
        self.bg_canvas.itemconfig(self.current_date_value, text=self.custom_date.strftime('%d %b %Y').upper())
        self.bg_canvas.itemconfig(self.current_time_value, text=datetime.now().strftime('%H:%M'))  # Changed from '%H:%M:%S' to '%H:%M'
        self.bg_canvas.itemconfig(self.sunrise_value, text=f"↑{sunrise}")
        self.bg_canvas.itemconfig(self.sunset_value, text=f"↓{sunset}")
        
        # Update every second now instead of every minute
        self.root.after(1000, self.update_static_elements)

    def calculate_sun_times(self, date):
        """Calculate sunrise and sunset times based on date (simplified)"""
        month = date.month
        day = date.day
        
        # Simplified model - in reality this would use location and proper calculations
        if month == 1:  # January
            sunrise = "07:45"
            sunset = "16:30"
        elif month == 2:  # February
            sunrise = "07:15"
            sunset = "17:15"
        else:  # Default (shouldn't happen in our simulation)
            sunrise = "06:00"
            sunset = "18:00"
        
        # Add some minor variation based on day of month
        day_variation = day % 15
        sunrise_min = int(sunrise.split(':')[1]) + day_variation
        sunset_min = int(sunset.split(':')[1]) + day_variation
        
        # Adjust hours if minutes overflow
        sunrise_h = int(sunrise.split(':')[0])
        sunset_h = int(sunset.split(':')[0])
        
        if sunrise_min >= 60:
            sunrise_h += 1
            sunrise_min -= 60
        if sunset_min >= 60:
            sunset_h += 1
            sunset_min -= 60
            
        return (f"{sunrise_h:02d}:{sunrise_min:02d}", f"{sunset_h:02d}:{sunset_min:02d}")

    def log(self, message, level=logging.INFO):
        """Log a message"""
        print(f"[{level}] {message}")

    def force_update(self, event=None):
        """Force immediate update of all display elements"""
        print("Forcing display update")
        self.update_display()
        self.update_static_elements()

    def shutdown(self, event=None):
        """Clean shutdown of the system"""
        print("Shutting down weather station system")
        self.root.quit()

if __name__ == "__main__":
    root = tk.Tk()
    app = WeatherStationSystem(root)
    root.protocol("WM_DELETE_WINDOW", app.shutdown)
    root.mainloop()