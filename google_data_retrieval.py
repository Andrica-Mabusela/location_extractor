from itertools import product
import requests
from dotenv import load_dotenv
import os
import csv
import json


# Load Environment Variables
load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# Google API Endpoints
google_places_api = "https://places.googleapis.com/v1/places:searchText"
google_details_api = "https://places.googleapis.com/v1/places/{place_id}"


master_sector_values = {
    "Mining and Quarrying": ["Mining", "Quarrying", "mines", "jewellery", "Head Office", "Office"],
    "Real Estate": ["Real estate", "housing", "Head Office", "Office", "Complex", "building"]
}

# Get locations from the google places API Call
def locations_google_places(search_terms: list[dict]) -> list[dict]:
    retrieved_locations: list[dict] = []
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.priceLevel"
    }
    # print(f"Search Terms Are: {search_terms}")
    for search_term in search_terms:
        # print("Search data")
        # print(search_term)
        # print("__________END Search Term _________________________")
        payload = {
            "textQuery": f"{search_term['customer_name']} {search_term['sub_sector']}",
            "regionCode": search_term["country_of_operation"]
        }
        
        response = requests.post(google_places_api, headers=headers, json=payload)
        response.raise_for_status()
        json_response = response.json()
        retrieved_locations.extend(json_response.get('places'))
    print(retrieved_locations)
    
    return retrieved_locations
    

# Return different search terms
def get_different_search_terms(
    customer_name: str,
    final_master_sector: str,
    countries_of_operation: list[str],
) -> list[dict]:
    results = []

    for country, sub_sector in product(countries_of_operation, master_sector_values[final_master_sector]):
        results.append({
            "customer_name": customer_name,
            "country_of_operation": country,
            "sub_sector": sub_sector
        })

    return results


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


search_terms = get_different_search_terms("PARETO LIMITED", "Real Estate", ["ZA"])
retrieved_locations_from_search_terms = locations_google_places(search_terms)

print(len(retrieved_locations_from_search_terms))
print(len(deduplicate_places(retrieved_locations_from_search_terms)))
with open("result.json", "a", encoding="utf-8") as f:
        f.write(json.dumps(deduplicate_places(retrieved_locations_from_search_terms)))


