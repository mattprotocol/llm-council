#!/usr/bin/env python3
"""Weather MCP server for retrieving current weather and forecast using Open-Meteo API."""

import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from datetime import datetime


# Weather code mappings from WMO
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail"
}


def get_weather_description(code: int) -> str:
    """Convert WMO weather code to description."""
    return WEATHER_CODES.get(code, f"Unknown weather (code {code})")


def get_coordinates_from_ip() -> Optional[Dict[str, float]]:
    """Get coordinates from IP geolocation."""
    try:
        req = urllib.request.Request(
            "https://ipinfo.io/json",
            headers={'User-Agent': 'Mozilla/5.0 (compatible; LLMCouncil/1.0)'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        loc = data.get('loc', '')
        if loc:
            lat, lon = loc.split(',')
            return {
                'latitude': float(lat),
                'longitude': float(lon),
                'city': data.get('city', 'Unknown'),
                'region': data.get('region', ''),
                'country': data.get('country', '')
            }
    except Exception:
        pass
    return None


def get_current_weather(latitude: Optional[float] = None, longitude: Optional[float] = None) -> Dict[str, Any]:
    """Get current weather for location.
    
    If lat/lon not provided, uses IP geolocation.
    Uses Open-Meteo API (free, no auth required).
    """
    try:
        location_info = {}
        
        # Get coordinates
        if latitude is None or longitude is None:
            geo = get_coordinates_from_ip()
            if not geo:
                return {"success": False, "error": "Could not determine location"}
            latitude = geo['latitude']
            longitude = geo['longitude']
            location_info = {
                'city': geo.get('city'),
                'region': geo.get('region'),
                'country': geo.get('country')
            }
        
        # Build API URL for current weather
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={latitude}&longitude={longitude}"
            f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
            f"precipitation,rain,weather_code,wind_speed_10m,wind_gusts_10m"
            f"&hourly=temperature_2m,precipitation_probability,weather_code"
            f"&forecast_days=1"
            f"&temperature_unit=fahrenheit"
            f"&wind_speed_unit=mph"
            f"&precipitation_unit=inch"
            f"&timezone=auto"
        )
        
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; LLMCouncil/1.0)'}
        )
        
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        current = data.get('current', {})
        hourly = data.get('hourly', {})
        
        # Get weather description
        weather_code = current.get('weather_code', 0)
        weather_desc = get_weather_description(weather_code)
        
        # Current conditions
        temp = current.get('temperature_2m')
        feels_like = current.get('apparent_temperature')
        humidity = current.get('relative_humidity_2m')
        wind_speed = current.get('wind_speed_10m')
        wind_gusts = current.get('wind_gusts_10m')
        precipitation = current.get('precipitation', 0)
        rain = current.get('rain', 0)
        
        # Determine upcoming conditions (next few hours)
        upcoming_rain = False
        rain_stops_soon = False
        if hourly:
            times = hourly.get('time', [])
            precip_probs = hourly.get('precipitation_probability', [])
            current_hour = datetime.now().hour
            
            # Check next 3 hours
            for i, time_str in enumerate(times[:current_hour + 4]):
                if i > current_hour:
                    prob = precip_probs[i] if i < len(precip_probs) else 0
                    if prob and prob > 50:
                        upcoming_rain = True
                        break
            
            # Check if currently raining but will stop
            if rain > 0 or precipitation > 0:
                for i, time_str in enumerate(times[current_hour:current_hour + 3]):
                    idx = current_hour + i
                    if idx < len(precip_probs):
                        if precip_probs[idx] < 30:
                            rain_stops_soon = True
                            break
        
        # Build human-friendly summary
        summary_parts = []
        
        # Location
        if location_info.get('city'):
            loc_str = location_info['city']
            if location_info.get('region'):
                loc_str += f", {location_info['region']}"
            summary_parts.append(f"Location: {loc_str}")
        
        # Current conditions
        summary_parts.append(f"Conditions: {weather_desc}")
        summary_parts.append(f"Temperature: {temp}°F (feels like {feels_like}°F)")
        summary_parts.append(f"Humidity: {humidity}%")
        summary_parts.append(f"Wind: {wind_speed} mph" + (f" (gusts up to {wind_gusts} mph)" if wind_gusts and wind_gusts > wind_speed + 5 else ""))
        
        # Precipitation status
        if rain > 0:
            summary_parts.append(f"Currently raining ({rain} inches)")
            if rain_stops_soon:
                summary_parts.append("Rain expected to stop soon")
        elif upcoming_rain:
            summary_parts.append("Rain expected in the next few hours")
        
        # Comfort/warnings
        warnings = []
        if temp is not None:
            if temp <= 32:
                warnings.append("Freezing temperatures - bundle up!")
            elif temp <= 45:
                warnings.append("Cold - dress warmly")
            elif temp >= 95:
                warnings.append("Extreme heat - stay hydrated")
            elif temp >= 85:
                warnings.append("Hot - stay cool")
        
        if wind_gusts and wind_gusts > 30:
            warnings.append("Strong winds - be careful")
        
        if warnings:
            summary_parts.append("Advisory: " + "; ".join(warnings))
        
        return {
            "success": True,
            "summary": "\n".join(summary_parts),
            "data": {
                "location": location_info,
                "conditions": weather_desc,
                "weather_code": weather_code,
                "temperature": temp,
                "feels_like": feels_like,
                "humidity": humidity,
                "wind_speed": wind_speed,
                "wind_gusts": wind_gusts,
                "precipitation": precipitation,
                "rain": rain,
                "upcoming_rain": upcoming_rain,
                "rain_stops_soon": rain_stops_soon,
                "warnings": warnings
            }
        }
        
    except urllib.error.URLError as e:
        return {"success": False, "error": f"Network error: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Failed to parse response: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_weather_for_date(
    date: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    hour: Optional[int] = None
) -> Dict[str, Any]:
    """Get weather for a specific date (historical or forecast).
    
    Args:
        date: Date in YYYY-MM-DD format
        latitude: Optional latitude (uses IP location if not provided)
        longitude: Optional longitude (uses IP location if not provided)
        hour: Optional hour (0-23) for specific time, otherwise returns daily summary
    
    Uses Open-Meteo API for historical data and forecasts.
    Historical data available from 1940 to present.
    Forecast available up to 16 days ahead.
    """
    try:
        location_info = {}
        
        # Get coordinates
        if latitude is None or longitude is None:
            geo = get_coordinates_from_ip()
            if not geo:
                return {"success": False, "error": "Could not determine location"}
            latitude = geo['latitude']
            longitude = geo['longitude']
            location_info = {
                'city': geo.get('city'),
                'region': geo.get('region'),
                'country': geo.get('country')
            }
        
        # Validate date format
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return {"success": False, "error": f"Invalid date format. Use YYYY-MM-DD (got: {date})"}
        
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        days_diff = (target_date - today).days
        
        # Determine if historical or forecast
        is_historical = days_diff < 0
        
        if is_historical:
            # Use Open-Meteo Historical API
            url = (
                f"https://archive-api.open-meteo.com/v1/archive?"
                f"latitude={latitude}&longitude={longitude}"
                f"&start_date={date}&end_date={date}"
                f"&hourly=temperature_2m,relative_humidity_2m,apparent_temperature,"
                f"precipitation,rain,weather_code,wind_speed_10m"
                f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
                f"weather_code,wind_speed_10m_max"
                f"&temperature_unit=fahrenheit"
                f"&wind_speed_unit=mph"
                f"&precipitation_unit=inch"
                f"&timezone=auto"
            )
        else:
            # Use Open-Meteo Forecast API
            if days_diff > 16:
                return {"success": False, "error": f"Forecast only available up to 16 days ahead (requested {days_diff} days)"}
            
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={latitude}&longitude={longitude}"
                f"&start_date={date}&end_date={date}"
                f"&hourly=temperature_2m,relative_humidity_2m,apparent_temperature,"
                f"precipitation_probability,precipitation,rain,weather_code,wind_speed_10m"
                f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
                f"precipitation_probability_max,weather_code,wind_speed_10m_max"
                f"&temperature_unit=fahrenheit"
                f"&wind_speed_unit=mph"
                f"&precipitation_unit=inch"
                f"&timezone=auto"
            )
        
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (compatible; LLMCouncil/1.0)'}
        )
        
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        hourly = data.get('hourly', {})
        daily = data.get('daily', {})
        
        # Build result
        result_data = {
            "date": date,
            "location": location_info,
            "is_historical": is_historical,
            "data_type": "historical" if is_historical else "forecast"
        }
        
        # Daily summary
        if daily:
            temp_max = daily.get('temperature_2m_max', [None])[0]
            temp_min = daily.get('temperature_2m_min', [None])[0]
            precip = daily.get('precipitation_sum', [0])[0]
            weather_code = daily.get('weather_code', [0])[0]
            wind_max = daily.get('wind_speed_10m_max', [None])[0]
            
            result_data["daily"] = {
                "high": temp_max,
                "low": temp_min,
                "conditions": get_weather_description(weather_code or 0),
                "precipitation": precip,
                "wind_max": wind_max
            }
        
        # Specific hour if requested
        if hour is not None and hourly:
            times = hourly.get('time', [])
            hour_idx = None
            for i, t in enumerate(times):
                if f"T{hour:02d}:" in t:
                    hour_idx = i
                    break
            
            if hour_idx is not None:
                result_data["hourly"] = {
                    "hour": hour,
                    "time": times[hour_idx],
                    "temperature": hourly.get('temperature_2m', [])[hour_idx] if hour_idx < len(hourly.get('temperature_2m', [])) else None,
                    "feels_like": hourly.get('apparent_temperature', [])[hour_idx] if hour_idx < len(hourly.get('apparent_temperature', [])) else None,
                    "humidity": hourly.get('relative_humidity_2m', [])[hour_idx] if hour_idx < len(hourly.get('relative_humidity_2m', [])) else None,
                    "conditions": get_weather_description(hourly.get('weather_code', [])[hour_idx] if hour_idx < len(hourly.get('weather_code', [])) else 0),
                    "precipitation": hourly.get('precipitation', [])[hour_idx] if hour_idx < len(hourly.get('precipitation', [])) else None,
                    "wind_speed": hourly.get('wind_speed_10m', [])[hour_idx] if hour_idx < len(hourly.get('wind_speed_10m', [])) else None
                }
        
        # Build human-friendly summary
        summary_parts = []
        
        # Location
        if location_info.get('city'):
            loc_str = location_info['city']
            if location_info.get('region'):
                loc_str += f", {location_info['region']}"
            summary_parts.append(f"Weather for {date} in {loc_str}")
        else:
            summary_parts.append(f"Weather for {date}")
        
        summary_parts.append(f"Data type: {'Historical' if is_historical else 'Forecast'}")
        
        if result_data.get("daily"):
            d = result_data["daily"]
            summary_parts.append(f"Conditions: {d.get('conditions', 'Unknown')}")
            summary_parts.append(f"High: {d.get('high')}°F, Low: {d.get('low')}°F")
            if d.get('precipitation', 0) > 0:
                summary_parts.append(f"Precipitation: {d.get('precipitation')} inches")
            if d.get('wind_max'):
                summary_parts.append(f"Max wind: {d.get('wind_max')} mph")
        
        if result_data.get("hourly"):
            h = result_data["hourly"]
            summary_parts.append(f"At {hour}:00: {h.get('temperature')}°F, {h.get('conditions')}")
        
        return {
            "success": True,
            "summary": "\n".join(summary_parts),
            "data": result_data
        }
        
    except urllib.error.URLError as e:
        return {"success": False, "error": f"Network error: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Failed to parse response: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# Tool definitions
TOOLS = [
    {
        "name": "get-current-weather",
        "description": "Get current weather conditions including temperature, humidity, wind, precipitation, and forecast. Uses IP geolocation if coordinates not provided.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "latitude": {
                    "type": "number",
                    "description": "Latitude (optional - uses IP location if not provided)"
                },
                "longitude": {
                    "type": "number",
                    "description": "Longitude (optional - uses IP location if not provided)"
                }
            },
            "required": []
        }
    },
    {
        "name": "get-weather-for-date",
        "description": "Get weather for a specific date. Supports historical data (past dates back to 1940) and forecasts (up to 16 days ahead). Returns daily summary or specific hour if requested.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format (e.g., 2025-12-12 for yesterday, 2025-12-14 for tomorrow)"
                },
                "latitude": {
                    "type": "number",
                    "description": "Latitude (optional - uses IP location if not provided)"
                },
                "longitude": {
                    "type": "number",
                    "description": "Longitude (optional - uses IP location if not provided)"
                },
                "hour": {
                    "type": "integer",
                    "description": "Hour of day (0-23) for specific time weather (optional - returns daily summary if not provided)"
                }
            },
            "required": ["date"]
        }
    }
]


def handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle a JSON-RPC request."""
    method = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id")
    
    response = {"jsonrpc": "2.0", "id": request_id}
    
    try:
        if method == "initialize":
            response["result"] = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "weather",
                    "version": "1.0.0"
                }
            }
        
        elif method == "notifications/initialized":
            return None
        
        elif method == "tools/list":
            response["result"] = {"tools": TOOLS}
        
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if tool_name == "get-current-weather":
                result = get_current_weather(
                    latitude=arguments.get("latitude"),
                    longitude=arguments.get("longitude")
                )
            elif tool_name == "get-weather-for-date":
                result = get_weather_for_date(
                    date=arguments.get("date"),
                    latitude=arguments.get("latitude"),
                    longitude=arguments.get("longitude"),
                    hour=arguments.get("hour")
                )
            else:
                response["error"] = {
                    "code": -32601,
                    "message": f"Unknown tool: {tool_name}"
                }
                return response
            
            response["result"] = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2)
                    }
                ]
            }
        
        else:
            response["error"] = {
                "code": -32601,
                "message": f"Unknown method: {method}"
            }
    
    except Exception as e:
        response["error"] = {
            "code": -32000,
            "message": str(e)
        }
    
    return response


def main():
    """Main entry point for the MCP server."""
    from mcp_servers.http_wrapper import stdio_main
    stdio_main(handle_request, "Weather MCP")


if __name__ == "__main__":
    main()
