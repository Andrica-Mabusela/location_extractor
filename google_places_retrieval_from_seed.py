from itertools import product
import requests
from dotenv import load_dotenv
import os
import csv
import json
import argparse
import sys
import re
import pandas as pd
from colorama import init, Fore, Style


init(autoreset=True)
# Load Environment Variables
load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# Google API Endpoints
google_places_api = "https://places.googleapis.com/v1/places:searchText"
google_details_api = "https://places.googleapis.com/v1/places/{place_id}"


parser = argparse.ArgumentParser()
parser.add_argument("--customer_name", required=True)
args = parser.parse_args()

print(f"customer name: {args.customer_name}")  # Website Url



master_sector_values = {
    "Mining and Quarrying": ["Mining", "Quarrying", "mines", "jewellery", "Head Office", "Office"],
    "Real Estate": ["Real estate", "housing", "Head Office", "Office", "Complex", "building"]
}

# Get locations from the google places API Call
def retrieve_google_places_addresses(customer_name: str, location: str, country: str) -> list[dict]:
    retrieved_locations: list[dict] = []
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.addressComponents,places.location"
    }


    payload = {
        "textQuery": f"{location}, {country}",
        "regionCode": "ZA"
    }
        
    response = requests.post(google_places_api, headers=headers, json=payload)
    response.raise_for_status()
    json_response = response.json()
    retrieved_locations.extend(json_response.get('places'))
    # print(retrieved_locations)
    
    return retrieved_locations
    

# De-Duplicate the results from locations_google_places()
def deduplicate_places(places: list[dict]) -> list[dict]:
    seen_ids = set()
    deduplicated = []

    for place in places:
        place_id = place.get("id")
        if place_id not in seen_ids:
            seen_ids.add(place_id)
            deduplicated.append(place)

    return deduplicated


# Replace spaces with _
def replace_spaces(text):
    return re.sub(r"\s+", "_", text)


if __name__ == "__main__":
    retrieved_all_locations_for_customer: list[dict] = []
    # Standardize the customer name
    customer_name = replace_spaces(args.customer_name)
    customer_locations_folder = r"C:\Users\User\Downloads\files\customer_locations"
    
    file_path = f"./customer_locations/{customer_name}_locations.csv"
    
    print(Fore.GREEN + file_path)
    # Read the csv file
    df = pd.read_csv(file_path, sep="|")

    for index, row in df.iterrows():
        location = row["location"]
        if location == "UNKNOWN" or pd.isna(location):
            continue  # skip rows without a real URL
    
        retrieved_locations = retrieve_google_places_addresses(row['customer_name'], row['location'], row['country'])
        de_duplicated_addresses = deduplicate_places(retrieved_locations)
        retrieved_all_locations_for_customer.extend(de_duplicated_addresses)

    print("ALL LOCATIONS FOR CUSTOMER:", retrieved_all_locations_for_customer)
    with open(f"{customer_name},json", "a", encoding="utf-8") as f:
        f.write(json.dumps(deduplicate_places(retrieved_all_locations_for_customer)))
    