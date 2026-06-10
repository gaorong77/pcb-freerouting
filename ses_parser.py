"""Parse Freerouting SES output file and extract routed wire segments.

Returns a dict suitable for JSON export to the viewer.
"""

import json
import re
import sys
from pathlib import Path

LAYER_DISPLAY = {
    "F.Cu":    "TOP",
    "In1.Cu":  "ART02",
    "In2.Cu":  "ART03",
    "B.Cu":    "BOTTOM",
}

SCALE = 1000  # 1 unit = 0.001 mm; divide by SCALE to get mm


def tokenize(text):
    """Tokenize Specctra S-expression into a flat list of tokens."""
    tokens = []
    i = 0
    while i < len(text):
        c = text[i]
        if c in "()":
            tokens.append(c)
            i += 1
        elif c == '"':
            j = text.index('"', i + 1)
            tokens.append(text[i+1:j])
            i = j + 1
        elif c in " \t\n\r":
            i += 1
        else:
            j = i
            while j < len(text) and text[j] not in " \t\n\r()\"":
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def parse_sexp(tokens, pos=0):
    """Recursively parse S-expression tokens into nested lists."""
    if tokens[pos] == "(":
        pos += 1
        result = []
        while tokens[pos] != ")":
            item, pos = parse_sexp(tokens, pos)
            result.append(item)
        pos += 1  # consume ")"
        return result, pos
    else:
        return tokens[pos], pos + 1


def find_all(node, key):
    """Yield all sub-lists whose first element == key."""
    if isinstance(node, list):
        if node and node[0] == key:
            yield node
        for child in node:
            yield from find_all(child, key)


def parse_ses(ses_path):
    """Parse SES file; return routing result dict."""
    text = Path(ses_path).read_text(encoding="utf-8", errors="replace")
    tokens = tokenize(text)
    tree, _ = parse_sexp(tokens)

    wires = []   # {"net": str, "layer": str, "pts": [[x,y],...]}
    vias  = []   # {"x": float, "y": float}

    for wire in find_all(tree, "wire"):
        # (wire (path LAYER WIDTH x1 y1 x2 y2 ...) (net "NETNAME") ...)
        net_name = ""
        for sub in wire[1:]:
            if isinstance(sub, list) and sub and sub[0] == "net":
                net_name = sub[1] if len(sub) > 1 else ""

        for sub in wire[1:]:
            if isinstance(sub, list) and sub and sub[0] == "path":
                # sub = [path, LAYER, WIDTH, x1, y1, x2, y2, ...]
                layer_raw = sub[1] if len(sub) > 1 else "F.Cu"
                layer_disp = LAYER_DISPLAY.get(layer_raw, layer_raw)
                coords = sub[3:]  # skip layer, width
                pts = []
                for k in range(0, len(coords) - 1, 2):
                    try:
                        x = float(coords[k]) / SCALE
                        y = float(coords[k+1]) / SCALE
                        pts.append([x, y])
                    except (ValueError, IndexError):
                        pass
                if len(pts) >= 2:
                    wires.append({
                        "net":   net_name,
                        "layer": layer_disp,
                        "pts":   pts,
                    })

    for via in find_all(tree, "via"):
        # (via "VIA_NAME" x y ...)
        if len(via) >= 4:
            try:
                x = float(via[2]) / SCALE
                y = float(via[3]) / SCALE
                vias.append({"x": x, "y": y})
            except (ValueError, IndexError):
                pass

    # Count per-net routing coverage
    net_wires = {}
    for w in wires:
        net_wires.setdefault(w["net"], 0)
        net_wires[w["net"]] += 1

    return {
        "wires": wires,
        "vias":  vias,
        "net_wire_counts": net_wires,
        "total_wire_segments": len(wires),
        "total_vias": len(vias),
    }


if __name__ == "__main__":
    ses_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("board.ses")
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("routing_result.json")

    if not ses_path.exists():
        print(f"[ses_parser] ERROR: {ses_path} not found")
        sys.exit(1)

    result = parse_ses(ses_path)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[ses_parser] Parsed {result['total_wire_segments']} wire segments, "
          f"{result['total_vias']} vias")
    print(f"[ses_parser] Nets routed: {len(result['net_wire_counts'])}")
    print(f"[ses_parser] Result written: {out_path}")
