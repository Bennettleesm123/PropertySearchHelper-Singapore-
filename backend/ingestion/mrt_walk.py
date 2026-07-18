"""
backend/ingestion/mrt_walk.py

Finds all exits for an MRT station, routes from a project to each exit,
and returns the shortest walk. This replaces hand-typed 'approx' station
coordinates - which were wrong by ~1.1km on the first attempt.

NOTE: this discovers exits via OneMap search, which is a bootstrap, not a
guarantee. The LTA MRT Station Exit dataset is the authoritative source and
should replace find_station_exits() before this metric is trusted at scale.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
from onemap_client import get_onemap_token, search_address
from onemap_routing import get_walking_route, haversine_m

load_dotenv()


def find_station_exits(station_name: str, token: str) -> list[dict]:
    """
    Returns every exit OneMap knows about for a station.

    Falls back to the station body itself if no exits are found - but flags it,
    because a station-body coordinate is a worse endpoint than a real exit.
    """
    data = search_address(station_name, token)
    results = data.get("results", [])

    if not results:
        raise ValueError(f"No OneMap results for {station_name!r}")

    exits = []
    station_body = None

    for r in results:
        name = (r.get("SEARCHVAL") or "").upper()
        point = {
            "name": r.get("SEARCHVAL"),
            "lat": float(r["LATITUDE"]),
            "lng": float(r["LONGITUDE"]),
        }
        if "EXIT" in name:
            exits.append(point)
        elif "MRT STATION" in name and station_body is None:
            station_body = point

    if not exits:
        if station_body is None:
            raise ValueError(f"No exits AND no station body found for {station_name!r}")
        print(f"  WARNING: no exits found for {station_name!r} - falling back to "
              f"station body. Endpoint quality is degraded.")
        return [station_body]

    return exits


def walk_to_nearest_exit(project_lat: float, project_lng: float,
                         station_name: str, token: str,
                         verbose: bool = True) -> dict:
    """
    Routes from a project to every exit of a station, returns the shortest.

    Returns a dict with the winning exit, its distance/time, the ratio vs
    straight-line, and how many exits were evaluated.
    """
    exits = find_station_exits(station_name, token)

    candidates = []
    for ex in exits:
        try:
            route = get_walking_route(project_lat, project_lng,
                                      ex["lat"], ex["lng"], token)
            summary = route.get("route_summary", {})
            distance_m = summary.get("total_distance")
            time_s = summary.get("total_time")

            if distance_m is None:
                print(f"  WARNING: no route_summary for {ex['name']} - skipping")
                continue

            straight = haversine_m(project_lat, project_lng, ex["lat"], ex["lng"])
            ratio = distance_m / straight if straight else float("inf")

            candidates.append({
                "exit_name": ex["name"],
                "exit_lat": ex["lat"],
                "exit_lng": ex["lng"],
                "distance_m": distance_m,
                "time_s": time_s,
                "straight_m": round(straight, 1),
                "ratio": round(ratio, 2),
            })

            if verbose:
                print(f"  {ex['name']:<40} {distance_m:>5}m  "
                      f"{time_s / 60:>4.1f}min  ratio {ratio:.2f}")

        except Exception as e:
            print(f"  WARNING: routing to {ex['name']} failed: {e}")

    if not candidates:
        raise ValueError(f"No valid routes to any exit of {station_name!r}")

    best = min(candidates, key=lambda c: c["distance_m"])
    best["exits_evaluated"] = len(candidates)
    best["station_query"] = station_name

    # the sanity check, applied to the winner
    if best["ratio"] < 1.05:
        print("  WARNING: ratio ~1.0 - router may have fallen back to a straight line")
    elif best["ratio"] > 2.0:
        print("  WARNING: ratio >2.0 - verify this route by hand on onemap.gov.sg")

    return best

def walk_to_nearest_station(project_lat: float, project_lng: float,
                            station_names: list[str], token: str) -> dict:
    """
    Routes to every exit of every listed station. Returns the best overall,
    plus per-station results so the scoring layer can reason about line
    diversity rather than just 'nearest'.

    station_names is hand-picked per project in the mapping table - do NOT
    auto-discover nearby stations.
    """
    per_station = []

    for name in station_names:
        print(f"\n{name}:")
        try:
            result = walk_to_nearest_exit(project_lat, project_lng, name, token)
            per_station.append(result)
        except Exception as e:
            print(f"  WARNING: {name} failed entirely: {e}")

    if not per_station:
        raise ValueError("No routable stations")

    per_station.sort(key=lambda s: s["time_s"])
    best = per_station[0]

    return {
        "best_station": best["station_query"],
        "best_exit": best["exit_name"],
        "distance_m": best["distance_m"],
        "time_s": best["time_s"],
        "stations_evaluated": len(per_station),
        "all_stations": per_station,   # keep everything - Phase 5 needs it
    }


if __name__ == "__main__":
    email = os.environ.get("ONEMAP_EMAIL")
    password = os.environ.get("ONEMAP_PASSWORD")

    if not email or not password:
        raise EnvironmentError("ONEMAP_EMAIL and ONEMAP_PASSWORD must be set in .env")

    token = get_onemap_token(email, password)
    print("Token retrieved.\n")

    # d'Leedon (Blk 7 area)
    project_lat, project_lng = 1.31442165521267, 103.803912974494

    # hand-picked per project, from the mapping table - not auto-discovered
    stations = ["Farrer Road MRT Station", "Holland Village MRT Station"]

    result = walk_to_nearest_station(project_lat, project_lng, stations, token)

    print(f"\n{'=' * 50}")
    print(f"Best: {result['best_station']} via {result['best_exit']}")
    print(f"  {result['distance_m']}m, {result['time_s'] / 60:.1f} min")
    print(f"\nAll stations by walk time:")
    for s in result["all_stations"]:
        print(f"  {s['station_query']:<35} {s['time_s'] / 60:>5.1f} min  ({s['exit_name']})")