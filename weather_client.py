"""
Weather Client for CDU Simulation Dashboard
Fetches live weather data from Open-Meteo API (free, no API key required)
"""

import re
import requests
from typing import Tuple, Optional, Dict

# Local city coordinates dictionary (fast lookup for predefined cities)
CITY_COORDINATES: Dict[str, Tuple[float, float]] = {
    "天津": (39.0842, 117.2009),      # Tianjin, CN
    "新加坡": (1.3521, 103.8198),     # Singapore, SG
    "法兰克福": (50.1109, 8.6821),    # Frankfurt, DE
    "阿什本": (39.0438, -77.4874)     # Ashburn, US - Data Center Alley
}

# Default values if API request fails
DEFAULT_TEMPERATURE = 25.0  # °C
DEFAULT_HUMIDITY = 60.0     # %


def _parse_coordinates(coord_str: str) -> Optional[Tuple[float, float]]:
    """
    Parse a string of the form "lat, lon" (with optional spaces) into floats.
    Returns (latitude, longitude) if successful, otherwise None.
    """
    # Match pattern: optional minus, digits, optional dot and digits, comma, optional space, same for longitude
    pattern = r'^[\-\+]?\d+(\.\d+)?\s*,\s*[\-\+]?\d+(\.\d+)?$'
    if not re.match(pattern, coord_str):
        return None
    try:
        lat_str, lon_str = coord_str.split(',')
        lat = float(lat_str.strip())
        lon = float(lon_str.strip())
        # Basic validation: latitude [-90,90], longitude [-180,180]
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
        else:
            return None
    except ValueError:
        return None


def search_city_coordinates(city_name: str) -> Optional[Tuple[float, float]]:
    """
    Search for coordinates of a city name using Open-Meteo Geocoding API with language=zh.
    Args:
        city_name: City name (e.g., "London", "Tokyo", "上海")
    Returns:
        Tuple of (latitude, longitude) if found, otherwise None.
    """
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": city_name,
        "count": 1,
        "language": "zh",   # Prefer Chinese results for better matching of Chinese city names
        "format": "json"
    }

    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        if not results:
            # No results found
            return None

        # Take the first result
        lat = results[0].get("latitude")
        lon = results[0].get("longitude")
        if lat is None or lon is None:
            return None

        return float(lat), float(lon)

    except requests.exceptions.RequestException as e:
        print(f"Warning: Failed to search coordinates for '{city_name}': {e}.")
        return None
    except (KeyError, ValueError, TypeError) as e:
        print(f"Warning: Error parsing geocoding data for '{city_name}': {e}.")
        return None
    except Exception as e:
        print(f"Warning: Unexpected error searching coordinates for '{city_name}': {e}.")
        return None


def get_weather_by_city_name(city_input: str) -> Tuple[float, float]:
    """
    Get live weather for a given city name or coordinate string.
    Supports:
      - Direct coordinate input: "lat, lon" (e.g., "39.9, 116.4")
      - Local dictionary lookup for predefined cities (fast)
      - Open-Meteo geocoding API (with language=zh) for any other place
    Args:
        city_input: City name or coordinate string
    Returns:
        Tuple of (temperature_2m, relative_humidity_2m)
        If any step fails, returns default values.
    """
    # Step 0: Normalize input
    city_input = city_input.strip()
    if not city_input:
        return DEFAULT_TEMPERATURE, DEFAULT_HUMIDITY

    # Step 1: Check if input is coordinates "lat, lon"
    coords = _parse_coordinates(city_input)
    if coords is not None:
        lat, lon = coords
    else:
        # Step 2: Check local dictionary (fast path for predefined cities)
        if city_input in CITY_COORDINATES:
            lat, lon = CITY_COORDINATES[city_input]
        else:
            # Step 3: Use geocoding API with language=zh
            coords = search_city_coordinates(city_input)
            if coords is None:
                print(f"Warning: Could not find coordinates for '{city_input}'. Using default values.")
                return DEFAULT_TEMPERATURE, DEFAULT_HUMIDITY
            lat, lon = coords

    # Step 4: Fetch weather using the obtained latitude and longitude
    url = f"https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m"
    }

    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        current = data.get("current", {})
        temperature = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")

        if temperature is None or humidity is None:
            print(f"Warning: Incomplete weather data for coordinates ({lat}, {lon}). Using default values.")
            return DEFAULT_TEMPERATURE, DEFAULT_HUMIDITY

        return float(temperature), float(humidity)

    except requests.exceptions.RequestException as e:
        print(f"Warning: Failed to fetch weather for coordinates ({lat}, {lon}): {e}. Using default values.")
        return DEFAULT_TEMPERATURE, DEFAULT_HUMIDITY
    except (KeyError, ValueError, TypeError) as e:
        print(f"Warning: Error parsing weather data for coordinates ({lat}, {lon}): {e}. Using default values.")
        return DEFAULT_TEMPERATURE, DEFAULT_HUMIDITY
    except Exception as e:
        print(f"Warning: Unexpected error fetching weather for coordinates ({lat}, {lon}): {e}. Using default values.")
        return DEFAULT_TEMPERATURE, DEFAULT_HUMIDITY


def get_live_weather(city_key: str) -> Tuple[float, float]:
    """
    Fetch live temperature and humidity for a given city key (original function for backward compatibility).
    Args:
        city_key: City name in Chinese (天津, 新加坡, 法兰克福, 阿什本)
    Returns:
        Tuple of (temperature_2m, relative_humidity_2m)
        If request fails, returns default values.
    """
    # Get coordinates for the city
    if city_key not in CITY_COORDINATES:
        print(f"Warning: Unknown city key '{city_key}'. Using default values.")
        return DEFAULT_TEMPERATURE, DEFAULT_HUMIDITY

    lat, lon = CITY_COORDINATES[city_key]

    # Build Open-Meteo API URL
    url = f"https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m"
    }

    try:
        # Make request to Open-Meteo API
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()  # Raise exception for HTTP errors

        data = response.json()

        # Extract current weather data
        current = data.get("current", {})
        temperature = current.get("temperature_2m")
        humidity = current.get("relative_humidity_2m")

        # Validate data
        if temperature is None or humidity is None:
            print(f"Warning: Incomplete weather data for {city_key}. Using default values.")
            return DEFAULT_TEMPERATURE, DEFAULT_HUMIDITY

        return float(temperature), float(humidity)

    except requests.exceptions.RequestException as e:
        print(f"Warning: Failed to fetch weather for {city_key}: {e}. Using default values.")
        return DEFAULT_TEMPERATURE, DEFAULT_HUMIDITY
    except (KeyError, ValueError, TypeError) as e:
        print(f"Warning: Error parsing weather data for {city_key}: {e}. Using default values.")
        return DEFAULT_TEMPERATURE, DEFAULT_HUMIDITY
    except Exception as e:
        print(f"Warning: Unexpected error fetching weather for {city_key}: {e}. Using default values.")
        return DEFAULT_TEMPERATURE, DEFAULT_HUMIDITY


# For testing purposes
if __name__ == "__main__":
    # Test predefined cities with the old function
    print("Testing predefined cities with get_live_weather:")
    for city in CITY_COORDINATES.keys():
        temp, hum = get_live_weather(city)
        print(f"{city}: Temperature={temp}°C, Humidity={hum}%")

    print("\nTesting coordinate input with get_weather_by_city_name:")
    test_coords = ["39.9, 116.4", "51.5074, -0.1278", "35.6895, 139.6917"]
    for coord in test_coords:
        temp, hum = get_weather_by_city_name(coord)
        print(f"Coords {coord}: Temperature={temp}°C, Humidity={hum}%")

    print("\nTesting city name search with get_weather_by_city_name:")
    test_cities = ["London", "Tokyo", "上海", "New York", "InvalidCity123"]
    for city in test_cities:
        temp, hum = get_weather_by_city_name(city)
        print(f"{city}: Temperature={temp}°C, Humidity={hum}%")