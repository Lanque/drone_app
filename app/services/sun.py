import httpx


class SunServiceError(Exception):
    pass


async def get_sun_conditions(
    latitude: float,
    longitude: float,
) -> dict:
    parameters = {
        "lat": latitude,
        "lng": longitude,
        "date": "today",
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://api.sunrise-sunset.org/v2",
                params=parameters,
            )
            response.raise_for_status()

        data = response.json()

        return {
            "sunrise": data["sunrise"],
            "sunset": data["sunset"],
            "timezone": data["tzid"],
            "golden_hour_morning": data["golden_hour"]["morning"],
            "golden_hour_evening": data["golden_hour"]["evening"],
            "blue_hour_morning": data["blue_hour"]["morning"],
            "blue_hour_evening": data["blue_hour"]["evening"],
        }
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        raise SunServiceError(
            "Could not retrieve sun data",
        ) from error