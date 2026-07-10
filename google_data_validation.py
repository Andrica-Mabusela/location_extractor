import os
import csv
import json
import time
import logging

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

API_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"

# Tune these to your dedup / precision needs
VALID_THRESHOLD = 0.75
REVIEW_THRESHOLD = 0.4

GRANULARITY_PENALTY = {
    "PREMISE": 0.0,
    "SUB_PREMISE": 0.0,
    "PREMISE_PROXIMITY": 0.05,
    "BLOCK": 0.15,
    "ROUTE": 0.25,
    "OTHER": 0.35,
}


def get_api_key(api_key: str | None = None) -> str:
    """Resolve API key from argument or GOOGLE_MAPS_API_KEY env var."""
    key = api_key or os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        raise ValueError(
            "No API key provided. Set GOOGLE_MAPS_API_KEY env var or pass api_key=."
        )
    return key


def compute_confidence(address_complete: bool, has_unconfirmed: bool,
                        has_inferred: bool, has_replaced: bool,
                        granularity: str) -> float:
    """Simple weighted confidence score in [0, 1]. Tune weights to taste."""
    score = 1.0
    if not address_complete:
        score -= 0.4
    if has_unconfirmed:
        score -= 0.35
    if has_inferred:
        score -= 0.10
    if has_replaced:
        score -= 0.10

    score -= GRANULARITY_PENALTY.get(granularity, 0.35)

    return max(0.0, round(score, 3))


def classify_status(confidence: float, address_complete: bool, has_unconfirmed: bool,
                     valid_threshold: float = VALID_THRESHOLD,
                     review_threshold: float = REVIEW_THRESHOLD) -> str:
    """Bucket a confidence score into VALID / NEEDS_REVIEW / INVALID."""
    if confidence >= valid_threshold and address_complete and not has_unconfirmed:
        return "VALID"
    elif confidence >= review_threshold:
        return "NEEDS_REVIEW"
    else:
        return "INVALID"


def empty_result(input_address: str, status: str = "INVALID", error: str | None = None) -> dict:
    """Default/error-shaped result dict, keeps CSV columns consistent."""
    return {
        "input_address": input_address,
        "formatted_address": None,
        "status": status,
        "verdict": None,
        "latitude": None,
        "longitude": None,
        "place_id": None,
        "has_unconfirmed_components": False,
        "has_inferred_components": False,
        "has_replaced_components": False,
        "address_complete": False,
        "confidence_score": 0.0,
        "error": error,
        "raw_response": {},
    }


def parse_validation_response(input_address: str, data: dict) -> dict:
    """Turn a raw Address Validation API response into a flat result dict."""
    result = data.get("result", {})
    verdict = result.get("verdict", {})
    address = result.get("address", {})
    geocode = result.get("geocode", {})
    location = geocode.get("location", {})

    has_unconfirmed = verdict.get("hasUnconfirmedComponents", False)
    has_inferred = verdict.get("hasInferredComponents", False)
    has_replaced = verdict.get("hasReplacedComponents", False)
    address_complete = verdict.get("addressComplete", False)
    granularity = verdict.get("validationGranularity", "OTHER")

    confidence = compute_confidence(
        address_complete, has_unconfirmed, has_inferred, has_replaced, granularity
    )
    status = classify_status(confidence, address_complete, has_unconfirmed)

    return {
        "input_address": input_address,
        "formatted_address": address.get("formattedAddress"),
        "status": status,
        "verdict": granularity,
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "place_id": geocode.get("placeId"),
        "has_unconfirmed_components": has_unconfirmed,
        "has_inferred_components": has_inferred,
        "has_replaced_components": has_replaced,
        "address_complete": address_complete,
        "confidence_score": confidence,
        "error": None,
        "raw_response": data,
    }


def validate_address(address_lines: list[str], api_key: str | None = None,
                      region_code: str = "US", locality: str | None = None,
                      postal_code: str | None = None, enable_usps_cass: bool = False,
                      request_delay: float = 0.05) -> dict:
    """
    Validate a single address against the Google Address Validation API.

    Args:
        address_lines: List of address lines, e.g.
            ["1600 Amphitheatre Parkway", "Mountain View, CA"]
        api_key: Google Maps API key. Falls back to GOOGLE_MAPS_API_KEY env var.
        region_code: ISO 3166-1 alpha-2 region code hint (e.g. 'US', 'ZA').
        locality: Optional city/locality hint.
        postal_code: Optional postal code hint.
        enable_usps_cass: Enable USPS CASS processing (US only, requires enrollment).
        request_delay: Seconds to sleep after the request (basic rate limiting).

    Returns:
        A result dict — see `empty_result` / `parse_validation_response` for shape.
    """
    key = get_api_key(api_key)
    input_address_str = ", ".join(address_lines)

    payload = {
        "address": {
            "regionCode": region_code,
            "addressLines": address_lines,
        }
    }
    if locality:
        payload["address"]["locality"] = locality
    if postal_code:
        payload["address"]["postalCode"] = postal_code
    if enable_usps_cass:
        payload["enableUspsCass"] = True

    try:
        resp = requests.post(
            API_URL,
            params={"key": key},
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.HTTPError as e:
        body = e.response.text if e.response is not None else str(e)
        logger.error("HTTP error validating %r: %s", input_address_str, body)
        return empty_result(input_address_str, status="ERROR", error=body)
    except requests.exceptions.RequestException as e:
        logger.error("Request failed for %r: %s", input_address_str, e)
        return empty_result(input_address_str, status="ERROR", error=str(e))
    finally:
        if request_delay:
            time.sleep(request_delay)

    return parse_validation_response(input_address_str, data)


def write_results_csv(results: list[dict], output_csv: str) -> None:
    """Write a list of result dicts to CSV (drops the raw_response blob)."""
    fieldnames = [
        "input_address", "formatted_address", "status", "verdict",
        "latitude", "longitude", "place_id", "has_unconfirmed_components",
        "has_inferred_components", "has_replaced_components",
        "address_complete", "confidence_score", "error",
    ]
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            row = {k: r.get(k) for k in fieldnames}
            writer.writerow(row)


def validate_batch_from_csv(input_csv: str, output_csv: str, api_key: str | None = None,
                             address_column: str = "address", region_code: str = "US",
                             region_code_column: str | None = None,
                             request_delay: float = 0.05) -> list[dict]:
    """
    Reads addresses from a CSV (one column with a full address string,
    comma-separated internally is fine, e.g. "123 Main St, Springfield"),
    validates each, and writes results to output_csv.
    """
    key = get_api_key(api_key)

    with open(input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    logger.info("Validating %d addresses from %s", len(rows), input_csv)

    results = []
    for i, row in enumerate(rows, 1):
        raw_address = row.get(address_column, "").strip()
        if not raw_address:
            logger.warning("Row %d: empty address, skipping", i)
            continue

        row_region = row.get(region_code_column, region_code) if region_code_column else region_code
        address_lines = [line.strip() for line in raw_address.split(",") if line.strip()]

        result = validate_address(
            address_lines, api_key=key, region_code=row_region, request_delay=request_delay
        )
        results.append(result)
        logger.info("[%d/%d] %s -> %s (confidence=%.2f)",
                    i, len(rows), raw_address, result["status"], result["confidence_score"])

    write_results_csv(results, output_csv)
    logger.info("Wrote %d results to %s", len(results), output_csv)
    return results


def main():
    """Example usage — single address and batch CSV modes."""
    # --- Single address example ---
    result = validate_address(
        address_lines=["1600 Amphitheatre Parkway", "Mountain View, CA"],
        region_code="US",
    )
    print(json.dumps(result, indent=2, default=str))

    # --- Batch CSV example (uncomment to use) ---
    # validate_batch_from_csv(
    #     input_csv="addresses_in.csv",
    #     output_csv="addresses_validated.csv",
    #     address_column="address",
    # )


if __name__ == "__main__":
    main()