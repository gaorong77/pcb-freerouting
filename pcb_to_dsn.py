"""Convert pcb_data.json to Specctra DSN format for Freerouting.

Resolution: mm 1000 (1 unit = 0.001 mm = 1 um)
All raw coordinates are already in this unit (scale_factor=1000).
Layers: F.Cu (TOP), In1.Cu (ART02), In2.Cu (ART03), B.Cu (BOTTOM)
"""

import json
import math
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LINE_W    = 75       # 0.075 mm in units
CLEARANCE = 75       # 0.075 mm in units
VIA_DRILL = 300      # 0.3 mm drill
VIA_PAD   = 600      # 0.6 mm annular pad
VIA_NAME  = "Via_600:300"

ALL_LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]

POUR_NETS = {"D_GND", "AUDIO_GND", "HPH_REF1",
             "USB_VBUS_C1", "SPK1_OUT_N1", "SPK1_OUT_P1"}

ARC_STEP_DEG = 5.0  # arc tessellation step


# ---------------------------------------------------------------------------
# Arc tessellation
# ---------------------------------------------------------------------------
def _arc_points(start, end, center, arc_mid):
    cx, cy = center
    sx, sy = start
    ex, ey = end
    mx, my = arc_mid

    def angle_of(px, py):
        return math.atan2(py - cy, px - cx)

    a_s = angle_of(sx, sy)
    a_m = angle_of(mx, my)
    a_e = angle_of(ex, ey)
    r   = math.hypot(sx - cx, sy - cy)

    def norm_up(a, base):
        while a < base:
            a += 2 * math.pi
        return a

    a_m_ccw = norm_up(a_m, a_s)
    a_e_ccw = norm_up(a_e, a_s)

    step = math.radians(ARC_STEP_DEG)
    pts  = []
    if a_m_ccw <= a_e_ccw:          # CCW
        a = a_s
        while a < a_e_ccw - 1e-9:
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
            a += step
    else:                           # CW
        a_e_cw = norm_up(a_e, a_s - 2 * math.pi + 1e-9)
        a = a_s
        while a > a_e_cw + 1e-9:
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
            a -= step
    pts.append((ex, ey))
    return pts


def segments_to_polygon(segments):
    pts = []
    for seg in segments:
        if seg["type"] == "line":
            if not pts:
                pts.append(tuple(seg["start"]))
            pts.append(tuple(seg["end"]))
        elif seg["type"] == "arc":
            arc_pts = _arc_points(
                seg["start"], seg["end"],
                seg["center"], seg["arc_mid"]
            )
            if pts:
                arc_pts = arc_pts[1:]
            pts.extend(arc_pts)
    return pts


# ---------------------------------------------------------------------------
# Component / padstack helpers
# ---------------------------------------------------------------------------
# Use a single small SMD padstack for all pins.
# The bbox in pcb_data.json is the component COURTYARD, not the actual copper pad.
# Using courtyard as pad would block the entire board; use a small fixed pad instead.
SMALL_PAD = "SmallSMD"
SMALL_PAD_R = 100   # 0.1 mm half-size (100 units = 0.1 mm)


def pad_key(p):
    """All pins share the same small padstack."""
    return SMALL_PAD


def collect_padstacks(components):
    return {SMALL_PAD: SMALL_PAD}


# ---------------------------------------------------------------------------
# DSN writer
# ---------------------------------------------------------------------------
def write_dsn(data, out_path):
    comps = data["components"]
    keepin_segs = data["route_keepins"][0]["segments"]
    raw_boundary = segments_to_polygon(keepin_segs)
    padstacks = collect_padstacks(comps)

    # Translate ALL coordinates so board origin = (0, 0).
    # This drastically reduces Freerouting internal data structure memory.
    all_x = [p[0] for p in raw_boundary]
    all_y = [p[1] for p in raw_boundary]
    ox = int(min(all_x))
    oy = int(min(all_y))
    boundary_pts = [(x - ox, y - oy) for x, y in raw_boundary]
    print(f"[pcb_to_dsn] Origin offset: dx={ox} dy={oy}")
    print(f"[pcb_to_dsn] Board extent after translation: "
          f"{(max(all_x)-ox)/1000:.1f} x {(max(all_y)-oy)/1000:.1f} mm")

    # Build per-refdes component structure (coordinates translated).
    comp_map = {}
    for c in comps:
        pins = c["pins"]
        if not pins:
            continue
        cx = round(sum(p["x"] for p in pins) / len(pins)) - ox
        cy = round(sum(p["y"] for p in pins) / len(pins)) - oy
        comp_map[c["refdes"]] = {
            "pkg":  c.get("package", "PKG"),
            "cx":   cx,
            "cy":   cy,
            "pins": [
                {
                    "num":   p["number"],
                    "rel_x": p["x"] - cx,
                    "rel_y": p["y"] - cy,
                    "pk":    pad_key(p),
                }
                for p in pins
            ],
        }

    # Each unique (pkg, pin-layout) needs one image in the library.
    # We use refdes as the image name to keep it simple (1 image per refdes).

    # Build route nets
    route_nets = {}
    for c in comps:
        for p in c["pins"]:
            net = p["net"]
            if not net or net in POUR_NETS:
                continue
            route_nets.setdefault(net, []).append((c["refdes"], p["number"]))

    def fmt(v):
        return str(int(round(v)))

    lines = []
    W = lines.append

    # ---- header ----
    W('(pcb board.dsn')
    W('  (parser')
    W('    (string_quote ")')
    W('    (space_in_quoted_tokens on)')
    W('    (host_cad "pcb-freerouting")')
    W('    (host_version "1.0")')
    W('  )')
    W('  (resolution mm 1000)')
    W('  (unit mm)')

    # ---- structure ----
    W('  (structure')
    for i, lyr in enumerate(ALL_LAYERS):
        W(f'    (layer {lyr}')
        W(f'      (type signal)')
        W(f'      (property (index {i}))')
        W(f'    )')
    coords_str = " ".join(f"{fmt(x)} {fmt(y)}" for x, y in boundary_pts)
    W(f'    (boundary (path pcb 0 {coords_str}))')
    W(f'    (via "{VIA_NAME}")')
    W(f'    (rule')
    W(f'      (width {LINE_W})')
    W(f'      (clearance {CLEARANCE})')
    W(f'    )')
    W('  )')

    # ---- library ----
    W('  (library')
    # Padstacks (unquoted names: alphanumeric+underscore are safe)
    for pname in sorted(padstacks.keys()):
        W(f'    (padstack {pname}')
        W(f'      (shape (rect F.Cu {-SMALL_PAD_R} {-SMALL_PAD_R} {SMALL_PAD_R} {SMALL_PAD_R}))')
        W(f'      (attach off)')
        W(f'    )')
    # Via padstack
    W(f'    (padstack {VIA_NAME}')
    for lyr in ALL_LAYERS:
        W(f'      (shape (circle {lyr} {VIA_PAD}))')
    W(f'      (hole {VIA_DRILL})')
    W(f'      (attach off)')
    W(f'    )')
    # Images: one per refdes, all identifiers unquoted
    for refdes, info in sorted(comp_map.items()):
        W(f'    (image {refdes}')
        for pin in info["pins"]:
            W(f'      (pin {SMALL_PAD} {pin["num"]} {fmt(pin["rel_x"])} {fmt(pin["rel_y"])})')
        W(f'    )')
    W('  )')

    # ---- placement ----
    W('  (placement')
    for refdes, info in sorted(comp_map.items()):
        W(f'    (component {refdes}')
        W(f'      (place {refdes} {fmt(info["cx"])} {fmt(info["cy"])} front 0)')
        W(f'    )')
    W('  )')

    # ---- network ----
    # Pin references must be unquoted: REFDES-PINNUM (Freerouting DSN standard)
    W('  (network')
    for net_name, pin_list in sorted(route_nets.items()):
        pin_ids = " ".join(f'{r}-{n}' for r, n in pin_list)
        W(f'    (net "{net_name}"')
        W(f'      (pins {pin_ids})')
        W(f'    )')
    W('  )')

    # ---- wiring (empty) ----
    W('  (wiring')
    W('  )')
    W(')')

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[pcb_to_dsn] Written: {out_path}  ({len(lines)} lines)")
    print(f"[pcb_to_dsn] Components: {len(comp_map)}")
    print(f"[pcb_to_dsn] Nets to route: {len(route_nets)}")
    print(f"[pcb_to_dsn] Padstacks: {len(padstacks)}")
    print(f"[pcb_to_dsn] Boundary pts: {len(boundary_pts)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pcb_data.json")
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("board.dsn")

    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    write_dsn(data, dst)
