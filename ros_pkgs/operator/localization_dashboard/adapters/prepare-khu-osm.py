# SPDX-FileCopyrightText: 2026 HYPERNOVA contributors
# SPDX-License-Identifier: Apache-2.0
"""Build the bundled KHU map from OSM map XML, with no external dependencies.

Download a fresh snapshot:
    python3 adapters/prepare-khu-osm.py

Replay a saved XML snapshot with its retrieval timestamp:
    python3 adapters/prepare-khu-osm.py --xml /tmp/khu.osm \
        --timestamp 2026-11-24T05:00:32Z
"""

import argparse
from datetime import datetime, timezone
from itertools import groupby, pairwise
import json
import math
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET


BOUNDS_TEXT = ("127.080", "37.2368", "127.0875", "37.2428")
BOUNDS = tuple(map(float, BOUNDS_TEXT))
SOURCE_URL = "https://api.openstreetmap.org/api/0.6/map?bbox=" + ",".join(BOUNDS_TEXT)
# KHU campus map marker 31, used only as the local projection origin.
ORIGIN = {"lat": 37.2393278832387, "lon": 127.08344685444}
HALL_DEMO_RADIUS_METRES = 150
METRES_PER_DEGREE = math.pi * 6378137 / 180
HALL_LONGITUDE_METRES = METRES_PER_DEGREE * math.cos(math.radians(ORIGIN["lat"]))
CAMPUS_RELATION, CAMPUS_OUTER = "11246784", "326869084"
ATTRIBUTION = "© OpenStreetMap contributors"
LICENSE = "https://opendatacommons.org/licenses/odbl/1-0/"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "public" / "khu-osm.json"

WALKWAYS = {"footway", "pedestrian", "path"}
ROADS = {
    "living_street",
    "residential",
    "road",
    "secondary",
    "secondary_link",
    "service",
    "tertiary",
    "tertiary_link",
    "track",
    "unclassified",
}
RESTRICTED = {
    "agricultural",
    "customers",
    "delivery",
    "emergency",
    "forestry",
    "military",
    "no",
    "permit",
    "private",
    "use_sidepath",
}


def tags(element):
    return {tag.get("k"): tag.get("v") for tag in element.findall("tag")}


def in_bounds(position):
    lat, lon = position
    west, south, east, north = BOUNDS
    return south <= lat <= north and west <= lon <= east


def restricted(attributes):
    return (
        any(attributes.get(key) in RESTRICTED for key in ("access", "foot"))
        or "access:conditional" in attributes
        or "foot:conditional" in attributes
        or attributes.get("indoor", "no") != "no"
        or attributes.get("tunnel") == "building_passage"
    )


def classify(attributes, closed):
    highway = attributes.get("highway")
    if highway in WALKWAYS:
        if (
            restricted(attributes)
            or attributes.get("area") == "yes"
            or attributes.get("informal") == "yes"
            or (
                attributes.get("bicycle") == "designated"
                and attributes.get("foot") not in {"designated", "yes", "permissive"}
            )
        ):
            return None
        return "walkway"
    if highway in ROADS and attributes.get("area") != "yes":
        return "road"
    if closed:
        if attributes.get("building") not in {None, "no", "demolished"}:
            return "building"
        if attributes.get("natural") == "water" or "water" in attributes:
            return "water"
        if (
            attributes.get("landuse") in {"grass", "forest", "meadow", "orchard"}
            or attributes.get("natural") in {"wood", "grassland", "scrub"}
            or attributes.get("leisure") in {"garden", "park", "nature_reserve"}
        ):
            return "green"
    return None


def point_in_ring(position, edges):
    lat, lon = position
    crossings = sum(
        (a[0] > lat) != (b[0] > lat)
        and lon < a[1] + (b[1] - a[1]) * (lat - a[0]) / (b[0] - a[0])
        for a, b in edges
    )
    return crossings % 2 == 1


def intersect(a, b, c, d):
    def side(p, q, r):
        cross = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        if abs(cross) < 1e-14:
            return 0
        return 1 if cross > 0 else -1

    return (
        all(
            max(min(a[axis], b[axis]), min(c[axis], d[axis]))
            <= min(max(a[axis], b[axis]), max(c[axis], d[axis]))
            for axis in (0, 1)
        )
        and side(a, b, c) * side(a, b, d) <= 0
        and side(c, d, a) * side(c, d, b) <= 0
    )


def campus_outline(root, coordinates):
    relation = root.find(f"relation[@id='{CAMPUS_RELATION}']")
    outer = root.find(f"way[@id='{CAMPUS_OUTER}']")
    if relation is None or outer is None or relation.find(
        f"member[@type='way'][@ref='{CAMPUS_OUTER}'][@role='outer']"
    ) is None:
        raise ValueError("KHU Global Campus local outer boundary is unavailable")
    refs = [int(node.get("ref")) for node in outer.findall("nd")]
    if len(refs) < 4 or refs[0] != refs[-1] or any(ref not in coordinates for ref in refs):
        raise ValueError("KHU Global Campus local outer boundary is incomplete")
    ring = [coordinates[ref] for ref in refs]
    edges = list(zip(ring, ring[1:]))
    if not point_in_ring([ORIGIN["lat"], ORIGIN["lon"]], edges):
        raise ValueError("KHU Global Campus boundary does not contain the map origin")
    return ring


def line_parts(refs, coordinates, blocked, boundary=()):
    """Split at unavailable nodes or campus-bounding edges without joining gaps."""
    part = []
    for ref in refs:
        if ref not in coordinates or not in_bounds(coordinates[ref]) or ref in blocked:
            if len(part) > 1:
                yield part
            part = []
            continue
        if part and any(
            intersect(coordinates[part[-1]], coordinates[ref], a, b)
            for a, b in boundary
        ):
            if len(part) > 1:
                yield part
            part = []
        if not part or part[-1] != ref:
            part.append(ref)
    if len(part) > 1:
        yield part


def near_hall(start, end):
    """Return whether the road segment intersects the building's demo area."""
    ay = (start[0] - ORIGIN["lat"]) * METRES_PER_DEGREE
    ax = (start[1] - ORIGIN["lon"]) * HALL_LONGITUDE_METRES
    dy = (end[0] - start[0]) * METRES_PER_DEGREE
    dx = (end[1] - start[1]) * HALL_LONGITUDE_METRES
    length_squared = dx * dx + dy * dy
    nearest = (
        max(0, min(1, -(ax * dx + ay * dy) / length_squared))
        if length_squared else 0
    )
    return math.hypot(ax + nearest * dx, ay + nearest * dy) <= HALL_DEMO_RADIUS_METRES


def demo_road_parts(nodes, coordinates, unroutable, boundary):
    """Keep OSM nodes and split each road into mapped and demo-routable parts."""

    def route_kind(edge):
        a, b = edge
        if a in unroutable or b in unroutable:
            return "road"
        start, end = coordinates[a], coordinates[b]
        if near_hall(start, end) and not any(
            intersect(start, end, c, d) for c, d in boundary
        ):
            return "walkway"
        return "road"

    for kind, edges in groupby(pairwise(nodes), route_kind):
        start, end = next(edges)
        yield kind, [start, end, *(end for _, end in edges)]


def make_extract(root, timestamp):
    bounds = root.find("bounds")
    if root.tag != "osm" or bounds is None or tuple(
        float(bounds.get(key)) for key in ("minlon", "minlat", "maxlon", "maxlat")
    ) != BOUNDS:
        raise ValueError("Expected OSM map XML for the KHU extract bounding box")

    coordinates, blocked, places = {}, set(), []
    for node in root.findall("node"):
        node_id = int(node.get("id"))
        position = [float(node.get("lat")), float(node.get("lon"))]
        coordinates[node_id] = position
        attributes = tags(node)
        if (
            restricted(attributes)
            or attributes.get("barrier", "no") != "no"
            or attributes.get("locked") == "yes"
            or attributes.get("highway") == "steps"
        ):
            blocked.add(node_id)
        name = attributes.get("name:ko") or attributes.get("name")
        if (
            name
            and attributes.get("amenity") in {"college", "university"}
            and in_bounds(position)
        ):
            places.append({"position": position, "name": name})

    outline = campus_outline(root, coordinates)
    edges = list(zip(outline, outline[1:]))
    off_campus = {
        ref for ref, position in coordinates.items() if not point_in_ring(position, edges)
    }
    unroutable = blocked | off_campus
    features, used = [], set()
    for way in root.findall("way"):
        attributes = tags(way)
        refs = [int(node.get("ref")) for node in way.findall("nd")]
        closed = len(refs) >= 4 and refs[0] == refs[-1]
        kind = classify(attributes, closed)
        name = attributes.get("name:ko") or attributes.get("name")
        complete = all(ref in coordinates for ref in refs)
        if closed and complete and name and attributes.get("place") == "square":
            vertices = [coordinates[ref] for ref in refs[:-1]]
            position = [round(sum(axis) / len(vertices), 7) for axis in zip(*vertices)]
            if in_bounds(position):
                places.append({"position": position, "name": name})
        if kind is None:
            continue
        if kind == "walkway":
            parts = line_parts(refs, coordinates, unroutable, edges)
        elif kind == "road":
            parts = line_parts(refs, coordinates, set())
        elif complete and any(in_bounds(coordinates[ref]) for ref in refs):
            parts = [refs]
        else:
            continue
        if kind == "road" and not restricted(attributes):
            classified_parts = (
                part
                for nodes in parts
                for part in demo_road_parts(nodes, coordinates, unroutable, edges)
            )
        else:
            classified_parts = ((kind, nodes) for nodes in parts)
        for part_kind, refs_part in classified_parts:
            feature = {"id": int(way.get("id")), "nodes": refs_part, "kind": part_kind}
            if name:
                feature["name"] = name
            features.append(feature)
            used.update(refs_part)

    return {
        "source": {
            "url": SOURCE_URL,
            "timestamp": timestamp,
            "attribution": ATTRIBUTION,
            "license": LICENSE,
        },
        "origin": ORIGIN,
        "campusOutline": outline,
        "nodes": {str(node_id): coordinates[node_id] for node_id in sorted(used)},
        "features": features,
        "places": places,
    }


def utc_timestamp(time):
    if time.tzinfo is None:
        raise ValueError("Snapshot timestamp needs a UTC offset")
    return time.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xml", type=Path)
    parser.add_argument("--timestamp", help="ISO 8601 retrieval time for --xml")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    options = parser.parse_args()
    if bool(options.xml) != bool(options.timestamp):
        parser.error("--xml and --timestamp must be used together")
    try:
        if options.xml:
            root = ET.parse(options.xml).getroot()
            captured = datetime.fromisoformat(options.timestamp)
        else:
            request = urllib.request.Request(
                SOURCE_URL,
                headers={
                    "User-Agent": "HyperNovaCampusDemo/1.0 "
                    "(+https://github.com/HyperNova26/hypernova-robot)",
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                root = ET.parse(response).getroot()
            captured = datetime.now(timezone.utc)
        data = make_extract(root, utc_timestamp(captured))
        options.output.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    except (OSError, ET.ParseError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(f"{options.output}: {len(data['nodes'])} nodes, {len(data['features'])} features")


if __name__ == "__main__":
    main()
