import os

import boto3
import pycountry
from boto3.dynamodb.conditions import Key

from base_service import ApiError


class LocationService:
    """Country and state lists from ISO data; city options from managed DynamoDB catalog."""

    def __init__(self, dynamodb=None):
        dynamodb = dynamodb or boto3.resource(
            "dynamodb", region_name=os.environ.get("AWS_REGION", "ap-south-1")
        )
        self.cities = dynamodb.Table(
            os.environ.get("LOCATIONS_TABLE", "CloudMedia-Locations-DEV")
        )

    def countries(self):
        return [{"code": c.alpha_2, "name": c.name}
                for c in sorted(pycountry.countries, key=lambda x: x.name)]

    def states(self, country_code):
        country_code = (country_code or "").upper()
        if not pycountry.countries.get(alpha_2=country_code):
            raise ApiError(400, "Valid countryCode is required")
        subdivisions = [s for s in pycountry.subdivisions if s.country_code == country_code]
        return [{"code": s.code, "name": s.name}
                for s in sorted(subdivisions, key=lambda x: x.name)]

    def cities_for_state(self, country_code, state_code):
        country_code = (country_code or "").upper()
        if not pycountry.countries.get(alpha_2=country_code):
            raise ApiError(400, "Valid countryCode is required")
        if not state_code or not state_code.startswith(country_code + "-"):
            raise ApiError(400, "stateCode must belong to selected country")
        result = self.cities.query(
            KeyConditionExpression=Key("countryState").eq(state_code),
            ProjectionExpression="cityName",
        )
        return sorted([item["cityName"] for item in result.get("Items", [])])

    def validate_selection(self, country_code, state_code, city_name):
        country = pycountry.countries.get(alpha_2=(country_code or "").upper())
        if not country:
            raise ApiError(400, "Select a valid country")
        states = self.states(country.alpha_2)
        state = next((s for s in states if s["code"] == state_code), None)
        if not state:
            raise ApiError(400, "Select a valid state/province for this country")
        cities = self.cities_for_state(country.alpha_2, state_code)
        if city_name not in cities:
            raise ApiError(400, "Select a city available for the selected state")
        return {"countryCode": country.alpha_2, "country": country.name,
                "stateCode": state["code"], "state": state["name"], "city": city_name}
