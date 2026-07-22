import os

import httpx
import logging

logger = logging.getLogger(__name__)

class WeatherServiceError(Exception):
    pass


async def get_current_wind(
    latitude: float,
    longitude: float,
) -> dict[str, float | None]:
    api_key = os.getenv("OPENWEATHER_API_KEY")

    if not api_key:
        raise WeatherServiceError("OpenWeather API key is missing")

    parameters = {
        "lat": latitude,
        "lon": longitude,
        "appid": api_key,
        "units": "metric",
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params=parameters,
            )
            response.raise_for_status()

        weather_data = response.json()
        wind_data = weather_data["wind"]

        return {
            "speed_mps": wind_data["speed"],
            "direction_degrees": wind_data.get("deg"),
            "gust_mps": wind_data.get("gust"),
        }
    except httpx.HTTPStatusError as error:
        logger.warning(
            "OpenWeather returned HTTP %s: %s",
            error.response.status_code,
            error.response.text,
        )
        raise WeatherServiceError(
            "Could not retrieve weather data",
        ) from error
    except httpx.RequestError as error:
        logger.warning("Could not connect to OpenWeather: %s", error)
        raise WeatherServiceError(
            "Could not retrieve weather data",
        ) from error
    except (KeyError, TypeError) as error:
        logger.warning("Unexpected OpenWeather response format")
        raise WeatherServiceError(
            "Could not retrieve weather data",
        ) from error