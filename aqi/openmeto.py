import openmeteo_requests

import pandas as pd
import requests_cache
from retry_requests import retry

# Setup the Open-Meteo API client with cache and retry on error
cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
openmeteo = openmeteo_requests.Client(session = retry_session)

# Make sure all required weather variables are listed here
# The order of variables in hourly or daily is important to assign them correctly below
url = "https://air-quality-api.open-meteo.com/v1/air-quality"
params = {
	"latitude": 24.7848,
	"longitude": 67.1259,
	"hourly": "pm2_5,pm10,carbon_dioxide,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone",
	"domains": "cams_global",
	"start_date": "2024-05-29",
	"end_date": "2024-12-30"
}
responses = openmeteo.weather_api(url, params=params)

# Process first location. Add a for-loop for multiple locations or weather models
response = responses[0]
print(f"Coordinates {response.Latitude()}°N {response.Longitude()}°E")
print(f"Elevation {response.Elevation()} m asl")
print(f"Timezone {response.Timezone()}{response.TimezoneAbbreviation()}")
print(f"Timezone difference to GMT+0 {response.UtcOffsetSeconds()} s")

# Process hourly data. The order of variables needs to be the same as requested.
hourly = response.Hourly()
hourly_pm2_5 = hourly.Variables(0).ValuesAsNumpy()
hourly_pm10 = hourly.Variables(1).ValuesAsNumpy()
hourly_carbon_dioxide = hourly.Variables(2).ValuesAsNumpy()
hourly_carbon_monoxide = hourly.Variables(3).ValuesAsNumpy()
hourly_nitrogen_dioxide = hourly.Variables(4).ValuesAsNumpy()
hourly_sulphur_dioxide = hourly.Variables(5).ValuesAsNumpy()
hourly_ozone = hourly.Variables(6).ValuesAsNumpy()

hourly_data = {"date": pd.date_range(
	start = pd.to_datetime(hourly.Time(), unit = "s", utc = True),
	end = pd.to_datetime(hourly.TimeEnd(), unit = "s", utc = True),
	freq = pd.Timedelta(seconds = hourly.Interval()),
	inclusive = "left"
)}

hourly_data["pm2_5"] = hourly_pm2_5
hourly_data["pm10"] = hourly_pm10
hourly_data["carbon_dioxide"] = hourly_carbon_dioxide
hourly_data["carbon_monoxide"] = hourly_carbon_monoxide
hourly_data["nitrogen_dioxide"] = hourly_nitrogen_dioxide
hourly_data["sulphur_dioxide"] = hourly_sulphur_dioxide
hourly_data["ozone"] = hourly_ozone

hourly_dataframe = pd.DataFrame(data = hourly_data)
print(hourly_dataframe)

# Save to CSV
hourly_dataframe.to_csv("karachi_aqi_data_last_year.csv", index=False)
print("Saved to karachi_aqi_data_last_year.csv")
