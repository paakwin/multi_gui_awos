from datetime import datetime, timedelta
from astral import LocationInfo
from astral.sun import sun
import csv

def generate_sun_data():
    # Karachi coordinates
    city = LocationInfo("Karachi", "Pakistan", "Asia/Karachi", 24.8607, 67.0011)
    
    # Output CSV
    with open("karachi_sun_data.csv", mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["date", "sunrise", "sunset"])
        
        # Start from Jan 1
        current_date = datetime(2025, 1, 1)
        end_date = datetime(2025, 12, 31)

        while current_date <= end_date:
            s = sun(city.observer, date=current_date, tzinfo=city.timezone)
            sunrise = s["sunrise"].strftime("%H:%M")
            sunset = s["sunset"].strftime("%H:%M")
            date_str = current_date.strftime("%m-%d")
            writer.writerow([date_str, sunrise, sunset])
            current_date += timedelta(days=1)

generate_sun_data()
