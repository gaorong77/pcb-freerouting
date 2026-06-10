# pcb-freerouting

Autorouting pipeline for USB Audio Board using Freerouting (open-source shape-based autorouter).

## Pipeline

```
pcb_data.json  -->  pcb_to_dsn.py  -->  board.dsn
                                            |
                                      freerouting.jar
                                            |
                                        board.ses
                                            |
                                       ses_parser.py
                                            |
                                    routing_result.json
                                            |
                                        viewer.html
```

## Requirements

- Python 3.10+
- Java 11+ (for Freerouting)

## Setup

```bash
# Install Python deps
pip install uv
uv venv && uv pip install shapely

# Download Freerouting
wget https://github.com/freerouting/freerouting/releases/latest/download/freerouting.jar
```

## Usage

```bash
# Full pipeline
bash run_freerouting.sh freerouting.jar

# Or step-by-step
python pcb_to_dsn.py pcb_data.json board.dsn
java -jar freerouting.jar -de board.dsn -do board.ses -mp 100
python ses_parser.py board.ses routing_result.json
# Open viewer.html in browser
```

## Board Info

- Size: 18.1 x 35.4 mm, 4 layers (TOP / ART02 / ART03 / BOTTOM)
- Components: 58, Pins: 165 (all on TOP)
- Nets to route: 26 (6 covered by copper pours)
- DRC: line width 0.075 mm, clearance 0.075 mm

## File Reference

| File | Description |
|---|---|
| `pcb_data.json` | Input PCB data (Allegro export, scale_factor=1000) |
| `pcb_to_dsn.py` | Convert pcb_data.json to Specctra DSN |
| `ses_parser.py` | Parse SES output to routing_result.json |
| `run_freerouting.sh` | Full pipeline shell script |
| `viewer.html` | Interactive routing result viewer |
| `board.dsn` | Generated DSN (Freerouting input) |
| `board.ses` | Freerouting output |
| `routing_result.json` | Parsed routing data for viewer |
