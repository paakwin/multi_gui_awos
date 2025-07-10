# Unified Creek AWOS

A comprehensive weather station and dashboard system implemented in Python using Tkinter, Modbus RTU, and multi-threading. Displays real-time environmental data and logs it reliably.

## 🌞 Features

### Main Components

- **Full-screen Dashboard** built with Tkinter
- Displays Temperature, Humidity, Pressure, UV Index, AQI, Wind Speed/Direction, and Rainfall
- Supports background images and precise widget positioning

### Sensor Integration

- Uses Modbus RTU for sensor communication (Environment, UV, AQI, Wind, Rain)

### Data Management

- Real-time data collection and display
- CSV logging with daily file rotation and 7-day retention
- State indicators with color coding

### Special Features

- Offline sunrise/sunset times from a CSV file
- Coordinate mapping mode for layout debugging
- Automatic rain gauge reset logic after 12 hours of no significant activity

### Technical Details

- Modbus RTU protocol for sensor connectivity
- Threading for concurrent sensor reading and CSV writing
- INI-based configuration for easy customization
- Keyboard shortcuts:
  - `F5`: Force display refresh
  - `F12`: Toggle coordinate mapping mode
  - `Escape`: Shutdown

## 🚀 Getting Started

1. Clone the repository:
   ```bash
   git clone https://github.com/paakwin/unified_creek_awos.git
   ```
2. Install dependencies with uv:
   ```bash
   uv sync
   ```
3. Run the program:
   ```bash
   uv run python main.py
   ```
4. Ensure Arial font is installed on your Linux system. If it's not installed, you can install it using:
   ```bash
   sudo apt-get install ttf-mscorefonts-installer
   ```

## ⚡️ Key Innovations

- Offline sun data for consistent performance
- Color-coded status indicators for quick status assessment
- Thread-safe data handling for reliability
- Automated error recovery and logging

## 🛠️ Contributing

Contributions are welcome! Feel free to open issues or pull requests for improvements.

## 📄 License

MIT License. See `LICENSE` for details.

**Developed by **[**paakwin**](https://github.com/paakwin)

