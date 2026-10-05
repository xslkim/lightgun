"""Metadata preflight only. Does not load Godot assets or prove playability."""
import argparse
import copy
import json
import math
from pathlib import Path


def validate(spec, manifest, level):
    errors = []

    def check(condition, location, message):
        if not condition:
            errors.append({"location": location, "message": message})

    def integer(value, minimum=0):
        return type(value) is int and value >= minimum

    def vector(value):
        return (isinstance(value, list) and len(value) == 3
                and all(type(x) in (int, float) and math.isfinite(x) for x in value))

    def index(items, location):
        result = {}
        check(isinstance(items, list), location, "must be a list")
        if not isinstance(items, list):
            return result
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                check(False, f"{location}/{i}", "must be an object")
                continue
            key = item.get("id")
            if not isinstance(key, str) or not key:
                check(False, f"{location}/{i}/id", "must be a nonempty string")
                continue
            check(key not in result, f"{location}/{i}/id", f"duplicate id: {key}")
            result[key] = item
        return result

    if not all(isinstance(x, dict) for x in (spec, manifest, level)):
        return [{"location": "root", "message": "all input roots must be objects"}]
    for name, data in (("spec", spec), ("manifest", manifest), ("level", level)):
        check(data.get("schema_version") == "0.1", name, "requires schema_version 0.1")
    check(spec.get("game_id") == level.get("game_id") and bool(spec.get("game_id")),
          "level/game_id", "game id must match spec")
    check(spec.get("input_profile") == "mouse_simulation", "spec/input_profile",
          "this sample requires mouse_simulation")
    weapon = spec.get("weapon", {})
    limits = spec.get("limits", {})
    if not isinstance(weapon, dict) or not isinstance(limits, dict):
        return errors + [{"location": "spec", "message": "weapon and limits must be objects"}]
    for key in ("magazine_size", "reload_ms", "shot_interval_ms"):
        check(integer(weapon.get(key), 1), f"spec/weapon/{key}", "must be a positive integer")
    for key in ("min_settle_ms", "min_reaction_ms", "min_entry_cue_ms", "max_enemies_per_station"):
        check(integer(limits.get(key), 1), f"spec/limits/{key}", "must be a positive integer")
    if any(not integer(limits.get(key), 1) for key in (
            "min_settle_ms", "min_reaction_ms", "min_entry_cue_ms", "max_enemies_per_station")):
        return errors
    assets = index(manifest.get("assets"), "assets")
    stations = index(level.get("stations"), "stations")
    check(bool(stations), "stations", "at least one station required")
    for aid, asset in assets.items():
        check(vector(asset.get("size_m")) and all(x > 0 for x in asset.get("size_m", [])),
              f"assets/{aid}/size_m", "requires positive finite dimensions")
    global_spawns = set()
    for sid, station in stations.items():
        p = f"stations/{sid}"
        environment = assets.get(station.get("environment_asset"))
        check(environment is not None and environment.get("kind") == "environment",
              p + "/environment_asset", "missing environment resource")
        camera = station.get("camera", {})
        if not isinstance(camera, dict):
            camera = {}
        check(vector(camera.get("position_m")), p + "/camera", "invalid camera position")
        check(vector(camera.get("look_at_m")), p + "/camera", "invalid look-at point")
        check(camera.get("position_m") != camera.get("look_at_m"), p + "/camera",
              "camera cannot look at its own position")
        fov = camera.get("fov_deg")
        check(type(fov) in (int, float) and math.isfinite(fov) and 1 < fov < 179,
              p + "/camera/fov_deg", "invalid fov")
        settle = station.get("settle_ms")
        check(integer(settle) and settle >= limits["min_settle_ms"], p + "/settle_ms",
              "settle grace shorter than required")
        anchors = index(station.get("anchors"), p + "/anchors")
        for aid, anchor in anchors.items():
            check(vector(anchor.get("position_m")), p + f"/anchors/{aid}", "invalid position")
        spawns = index(station.get("spawns"), p + "/spawns")
        check(0 < len(spawns) <= limits["max_enemies_per_station"], p + "/spawns",
              "single-wave count outside conservative budget")
        gate = station.get("gate", {})
        if not isinstance(gate, dict):
            gate = {}
        check(gate.get("mode") == "all_resolved", p + "/gate", "unsupported gate mode")
        terminals = gate.get("terminal_states", [])
        check(isinstance(terminals, list) and set(("dead", "escaped", "disarmed")).issubset(
            x for x in terminals if isinstance(x, str)), p + "/gate",
            "must handle dead, escaped, disarmed terminal states")
        timeout = gate.get("timeout_ms")
        check(integer(timeout, 1), p + "/gate/timeout_ms", "positive watchdog required")
        check(gate.get("on_timeout") == "fail", p + "/gate/on_timeout",
              "watchdog must report failure rather than fake completion")
        for spawn_id, spawn in spawns.items():
            q = p + f"/spawns/{spawn_id}"
            check(spawn_id not in global_spawns, q, "spawn id must be globally unique")
            global_spawns.add(spawn_id)
            asset = assets.get(spawn.get("asset"))
            check(asset is not None and asset.get("kind") == "enemy", q + "/asset",
                  "missing enemy resource")
            check(spawn.get("anchor") in anchors, q + "/anchor", "missing anchor")
            if spawn.get("role") == "elite" and asset:
                check("weakpoint" in asset.get("capabilities", []), q, "elite needs weakpoint")
            keys = ("cue_ms", "spawn_ms", "targetable_ms", "telegraph_ms", "attack_ms")
            if not all(integer(spawn.get(k)) for k in keys):
                check(False, q, "timing fields must be nonnegative integer milliseconds")
                continue
            cue, entry, target, telegraph, attack = [spawn[k] for k in keys]
            check(cue <= entry <= target <= telegraph < attack, q, "invalid timing order")
            check(entry - cue >= limits["min_entry_cue_ms"], q, "entry cue too short")
            check(attack - max(target, telegraph) >= limits["min_reaction_ms"], q,
                  "readable reaction window too short")
            check(integer(timeout, 1) and timeout > attack, q, "watchdog precedes attack")
        nxt = station.get("next")
        check("next" in station, p + "/next", "explicit next or null required")
        check(nxt is None or (isinstance(nxt, str) and nxt in stations), p + "/next",
              "missing next station")
    start = level.get("start")
    check(isinstance(start, str) and start in stations, "level/start", "missing start station")
    visited = set()
    current = start
    if isinstance(start, str):
        while current is not None and isinstance(current, str) and current in stations:
            if current in visited:
                check(False, "level/graph", "cycle forbidden in first-version sample")
                break
            visited.add(current)
            current = stations[current].get("next")
    check(visited == set(stations), "level/graph", "unreachable station")
    check(current is None and bool(visited), "level/graph", "no reachable terminal")
    return errors


def load(directory):
    return tuple(json.loads((directory / filename).read_text(encoding="utf-8")) for filename in
                 ("game_spec.json", "asset_manifest.json", "level_ir.json"))


def self_test(inputs):
    mutations = [
        ("duplicate_station", lambda s, a, l: l["stations"].append(copy.deepcopy(l["stations"][0]))),
        ("missing_asset", lambda s, a, l: l["stations"][0]["spawns"][0].update(asset="absent")),
        ("missing_anchor", lambda s, a, l: l["stations"][0]["spawns"][0].update(anchor="absent")),
        ("short_window", lambda s, a, l: l["stations"][0]["spawns"][0].update(attack_ms=1300)),
        ("short_settle", lambda s, a, l: l["stations"][0].update(settle_ms=10)),
        ("negative_time", lambda s, a, l: l["stations"][0]["spawns"][0].update(cue_ms=-1)),
        ("cycle", lambda s, a, l: l["stations"][-1].update(next="entry")),
        ("unreachable", lambda s, a, l: l["stations"][0].update(next="finale")),
        ("fake_watchdog_pass", lambda s, a, l: l["stations"][0]["gate"].update(on_timeout="pass")),
        ("weakpoint_missing", lambda s, a, l: a["assets"][-1].update(capabilities=["death"])),
        ("invalid_limit", lambda s, a, l: s["limits"].update(min_reaction_ms=True)),
        ("bad_next", lambda s, a, l: l["stations"][0].update(next="absent")),
    ]
    results = [{"case": "valid_sample", "pass": not validate(*inputs)}]
    for name, mutation in mutations:
        trial = copy.deepcopy(inputs)
        mutation(*trial)
        errors = validate(*trial)
        results.append({"case": name, "pass": bool(errors), "detected_errors": len(errors)})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        inputs = load(args.dir)
        if args.self_test:
            cases = self_test(inputs)
            report = {"status": "PASS" if all(x["pass"] for x in cases) else "FAIL", "cases": cases}
        else:
            errors = validate(*inputs)
            report = {"status": "PASS" if not errors else "FAIL", "errors": errors,
                      "scope": "metadata preflight only; no Godot, asset existence, rendering or device checks"}
        result = json.dumps(report, ensure_ascii=False, indent=2)
        if args.report:
            args.report.write_text(result + "\n", encoding="utf-8")
        print(result)
        return 0 if report["status"] == "PASS" else 1
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"status": "ERROR", "message": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
