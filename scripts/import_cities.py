import csv
import os
import sys

import boto3

TABLE = os.environ.get("LOCATIONS_TABLE", "CloudMedia-Locations-DEV")
REGION = os.environ.get("AWS_REGION", "ap-south-1")


def main(path):
    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    count = 0
    with open(path, newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not {"countryState", "cityName"}.issubset(reader.fieldnames or []):
            raise SystemExit("CSV must contain countryState,cityName columns")
        with table.batch_writer() as batch:
            for row in reader:
                state = row["countryState"].strip()
                city = row["cityName"].strip()
                if state and city:
                    batch.put_item(Item={"countryState": state, "cityName": city})
                    count += 1
    print(f"Imported {count} city rows into {TABLE}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/import_cities.py infrastructure/cities-seed-example.csv")
    main(sys.argv[1])
