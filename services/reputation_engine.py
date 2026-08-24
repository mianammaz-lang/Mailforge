from typing import List, Dict, Any

def calculate_reputation_status(provider_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    providers_checked = len(provider_results)
    confirmed_listings = 0
    timeouts = 0
    errors = 0
    listed_providers = []

    for result in provider_results:
        status = result.get("status", "UNKNOWN")
        if status == "LISTED" and result.get("is_confirmed"):
            confirmed_listings += 1
            listed_providers.append(result.get("provider", "Unknown Provider"))
        elif status == "TIMEOUT":
            timeouts += 1
        elif status == "ERROR":
            errors += 1

    if confirmed_listings >= 1:
        final_status = "BLACKLISTED"
    elif timeouts > 0:
        final_status = "CLEAN_WITH_TIMEOUT"
    elif errors == 0:
        final_status = "CLEAN"
    else:
        final_status = "UNVERIFIED"

    return {
        "status": final_status,
        "providers_checked": providers_checked,
        "confirmed_listings": confirmed_listings,
        "timeouts": timeouts,
        "errors": errors,
        "listed_providers": listed_providers,
        "details": provider_results
    }
