# ECHO Adventure

A terminal-based scheduling strategy game set in a fictional advanced manufacturing yard.

The player acts as a manual scheduler trying to complete a 15-piece project in 15 in-game days. A hidden automated scheduling engine runs the same scenario and disruption timeline in parallel, then appears only in the final report as an operational benchmark.

## Run

```bash
python -m echo_adventure
```

or:

```bash
python main.py
```

Optional flags:

```bash
python -m echo_adventure --seed 12345
python -m echo_adventure --no-color
python -m echo_adventure --debug
```

## Visual UI

Run the local browser dashboard:

```bash
python -m echo_adventure --ui
```

With a fixed seed:

```bash
python -m echo_adventure --ui --seed 4242
```

Then open:

```text
http://127.0.0.1:8765
```

`rich` is declared as the terminal rendering dependency. If it is unavailable, the game falls back to a plain terminal renderer so local play still works.
