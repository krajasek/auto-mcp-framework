"""Mock weather API demonstrating async function support.

This module simulates a weather API to show how auto-mcp handles
async functions. In a real implementation, these would make actual
HTTP requests to a weather service.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Literal


@dataclass
class WeatherData:
    """Weather data for a location."""

    location: str
    temperature_celsius: float
    humidity_percent: int
    conditions: str
    wind_speed_kmh: float


# Simulated weather conditions
CONDITIONS = ["Sunny", "Partly Cloudy", "Cloudy", "Rainy", "Stormy", "Snowy", "Foggy"]


async def get_current_weather(city: str, country: str = "US") -> dict:
    """Get the current weather for a city.

    Args:
        city: Name of the city
        country: Country code (default: US)

    Returns:
        Dictionary containing current weather data
    """
    # Simulate API latency
    await asyncio.sleep(0.1)

    # Generate mock weather data
    return {
        "location": f"{city}, {country}",
        "temperature_celsius": round(random.uniform(-10, 35), 1),
        "humidity_percent": random.randint(30, 90),
        "conditions": random.choice(CONDITIONS),
        "wind_speed_kmh": round(random.uniform(0, 50), 1),
    }


async def get_forecast(
    city: str,
    days: int = 5,
    country: str = "US",
) -> list[dict]:
    """Get a weather forecast for the coming days.

    Args:
        city: Name of the city
        days: Number of days to forecast (1-7)
        country: Country code (default: US)

    Returns:
        List of daily forecast data
    """
    if days < 1 or days > 7:
        raise ValueError("Days must be between 1 and 7")

    # Simulate API latency
    await asyncio.sleep(0.1)

    forecasts = []
    base_temp = random.uniform(10, 25)

    for day in range(days):
        forecasts.append({
            "day": day + 1,
            "location": f"{city}, {country}",
            "high_celsius": round(base_temp + random.uniform(5, 10), 1),
            "low_celsius": round(base_temp - random.uniform(5, 10), 1),
            "conditions": random.choice(CONDITIONS),
            "precipitation_chance": random.randint(0, 100),
        })

    return forecasts


async def get_temperature(city: str, unit: Literal["celsius", "fahrenheit"] = "celsius") -> float:
    """Get just the current temperature for a city.

    Args:
        city: Name of the city
        unit: Temperature unit (celsius or fahrenheit)

    Returns:
        Current temperature in the specified unit
    """
    await asyncio.sleep(0.05)

    temp_celsius = random.uniform(-10, 35)

    if unit == "fahrenheit":
        return round(temp_celsius * 9 / 5 + 32, 1)
    return round(temp_celsius, 1)


async def compare_weather(city1: str, city2: str) -> dict:
    """Compare current weather between two cities.

    Args:
        city1: First city name
        city2: Second city name

    Returns:
        Comparison data for both cities
    """
    # Fetch both concurrently
    weather1, weather2 = await asyncio.gather(
        get_current_weather(city1),
        get_current_weather(city2),
    )

    temp_diff = weather1["temperature_celsius"] - weather2["temperature_celsius"]

    return {
        "city1": weather1,
        "city2": weather2,
        "temperature_difference_celsius": round(temp_diff, 1),
        "warmer_city": city1 if temp_diff > 0 else city2,
    }


async def search_cities(query: str, limit: int = 5) -> list[dict]:
    """Search for cities by name.

    Args:
        query: Search query (partial city name)
        limit: Maximum results to return (1-20)

    Returns:
        List of matching cities with country codes
    """
    if limit < 1 or limit > 20:
        raise ValueError("Limit must be between 1 and 20")

    await asyncio.sleep(0.05)

    # Mock city database
    cities = [
        {"name": "New York", "country": "US", "population": 8336817},
        {"name": "Los Angeles", "country": "US", "population": 3979576},
        {"name": "London", "country": "GB", "population": 8982000},
        {"name": "Paris", "country": "FR", "population": 2161000},
        {"name": "Tokyo", "country": "JP", "population": 13960000},
        {"name": "Sydney", "country": "AU", "population": 5312000},
        {"name": "Berlin", "country": "DE", "population": 3645000},
        {"name": "New Delhi", "country": "IN", "population": 32941000},
        {"name": "Newark", "country": "US", "population": 282011},
        {"name": "Newcastle", "country": "GB", "population": 302820},
    ]

    query_lower = query.lower()
    matches = [c for c in cities if query_lower in c["name"].lower()]

    return matches[:limit]
