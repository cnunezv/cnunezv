"""
Genera un SVG animado de la gráfica de contribuciones de GitHub
modelada como la ecuación del calor con disipación:

    du/dt = alpha * Laplaciano(u) - lambda * u

Cada día con contribuciones es una fuente de calor (intensidad = nivel 1..4).
Se resuelve con diferencias finitas explícitas sobre la malla 53 x 7.
Solo usa la biblioteca estándar de Python.

Uso:  python scripts/heat.py <usuario> <carpeta_salida>
"""

import datetime as dt
import os
import re
import sys
import urllib.request

# ---------------------------------------------------------------- parámetros
ALPHA = 0.22          # difusividad (estable si alpha <= 0.25)
LAMBDA = 0.15          # disipación
SUBSTEPS = 1          # pasos numéricos por fotograma
FRAMES_HOLD = 8       # fotogramas mostrando la gráfica original
FRAMES_DIFFUSE = 34   # fotogramas de difusión
FRAMES_STEADY = 10    # fotogramas en estado casi estacionario
FRAMES_BACK = 10      # fotogramas de regreso a la gráfica
FRAME_SEC = 0.28      # duración de cada fotograma
LEVELS = 16           # niveles de color cuantizados

CELL, GAP = 11, 3
LEFT, TOP = 34, 44
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
         "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
DIAS = {1: "Lun", 3: "Mié", 5: "Vie"}

THEMES = {
    "dark": {
        "bg": "#0d1117", "text": "#8b949e", "title": "#e6edf3", "accent": "#58a6ff",
        "ramp": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353", "#9be9a8"],
    },
    "light": {
        "bg": "#ffffff", "text": "#57606a", "title": "#1f2328", "accent": "#0969da",
        "ramp": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39", "#0f3d20"],
    },
}


# ---------------------------------------------------------------- datos
def fetch_levels(user):
    url = f"https://github.com/users/{user}/contributions"
    req = urllib.request.Request(url, headers={"User-Agent": "heat-contrib"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    return parse_levels(html)


def parse_levels(html):
    cells = {}
    for tag in re.findall(r"<td[^>]*ContributionCalendar-day[^>]*>", html):
        d = re.search(r'data-date="(\d{4}-\d{2}-\d{2})"', tag)
        lv = re.search(r'data-level="(\d)"', tag)
        if d and lv:
            cells[dt.date.fromisoformat(d.group(1))] = int(lv.group(1))
    if not cells:
        raise SystemExit("No se encontraron días en la gráfica de contribuciones.")
    first = min(cells)
    start = first - dt.timedelta(days=(first.weekday() + 1) % 7)  # domingo
    cols = (max(cells) - start).days // 7 + 1
    grid = [[None] * cols for _ in range(7)]
    for day, lv in cells.items():
        off = (day - start).days
        grid[off % 7][off // 7] = lv
    return grid, start


# ---------------------------------------------------------------- simulación
def simulate(grid):
    rows, cols = len(grid), len(grid[0])
    src = [[(v or 0) / 4 for v in row] for row in grid]
    u = [row[:] for row in src]

    def step(u):
        new = [[0.0] * cols for _ in range(rows)]
        for r in range(rows):
            for c in range(cols):
                if grid[r][c] is None:
                    continue
                s, n = 0.0, 0
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < rows and 0 <= cc < cols and grid[rr][cc] is not None:
                        s += u[rr][cc]
                        n += 1
                lap = s - n * u[r][c]          # frontera aislada (Neumann)
                v = u[r][c] + ALPHA * lap - LAMBDA * u[r][c]
                new[r][c] = max(v, src[r][c])  # las fuentes se mantienen
        return new

    frames = [src] * FRAMES_HOLD
    for _ in range(FRAMES_DIFFUSE):
        for _ in range(SUBSTEPS):
            u = step(u)
        frames.append(u)
    frames += [u] * FRAMES_STEADY
    for k in range(1, FRAMES_BACK + 1):
        t = k / FRAMES_BACK
        frames.append([[a * (1 - t) + b * t for a, b in zip(ra, rb)]
                       for ra, rb in zip(u, src)])
    return frames


# ---------------------------------------------------------------- color
def hex2rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def palette(ramp):
    stops = [hex2rgb(h) for h in ramp]
    out = []
    for i in range(LEVELS):
        x = i / (LEVELS - 1) * (len(stops) - 1)
        j = min(int(x), len(stops) - 2)
        t = x - j
        rgb = [round(a + (b - a) * t) for a, b in zip(stops[j], stops[j + 1])]
        out.append("#%02x%02x%02x" % tuple(rgb))
    return out


def level(v):
    if v <= 0.03:
        return 0
    v = min(v, 1.0) ** 0.7          # realza el halo tenue
    return max(1, min(LEVELS - 1, round(v * (LEVELS - 1))))


# ---------------------------------------------------------------- SVG
def render(grid, start, frames, theme):
    th = THEMES[theme]
    pal = palette(th["ramp"])
    rows, cols = len(grid), len(grid[0])
    width = LEFT + cols * (CELL + GAP) + 16
    height = TOP + rows * (CELL + GAP) + 52
    total = len(frames) * FRAME_SEC
    n = len(frames)
    key_times = ";".join(f"{i / n:.4f}" for i in range(n))

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" '
        f'aria-label="Contribuciones de GitHub como difusión de calor">',
        f'<rect width="100%" height="100%" rx="8" fill="{th["bg"]}"/>',
        '<style>text{font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,'
        'Menlo,Consolas,monospace}</style>',
        f'<text x="{LEFT}" y="20" font-size="12" fill="{th["title"]}">'
        f'<tspan fill="{th["accent"]}">∂u/∂t</tspan> = α∇²u − λu</text>',
        f'<text x="{width - 16}" y="20" font-size="10" fill="{th["text"]}" '
        f'text-anchor="end">ecuación del calor con disipación</text>',
    ]

    # etiquetas de meses
    last = None
    for c in range(cols):
        d = start + dt.timedelta(weeks=c)
        if d.month != last and c < cols - 2:
            if last is not None or d.day <= 7:
                out.append(f'<text x="{LEFT + c * (CELL + GAP)}" y="{TOP - 6}" '
                           f'font-size="9" fill="{th["text"]}">{MESES[d.month - 1]}</text>')
            last = d.month
    for r, name in DIAS.items():
        out.append(f'<text x="{LEFT - 6}" y="{TOP + r * (CELL + GAP) + 9}" font-size="9" '
                   f'fill="{th["text"]}" text-anchor="end">{name}</text>')

    # celdas
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] is None:
                continue
            x, y = LEFT + c * (CELL + GAP), TOP + r * (CELL + GAP)
            seq = [pal[level(f[r][c])] for f in frames]
            rect = f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{seq[0]}"'
            if len(set(seq)) == 1:
                out.append(rect + "/>")
            else:
                out.append(rect + f'><animate attributeName="fill" dur="{total:.2f}s" '
                           f'repeatCount="indefinite" calcMode="discrete" '
                           f'keyTimes="{key_times}" values="{";".join(seq)}"/></rect>')

    # pie: leyenda + barra de progreso del tiempo
    fy = TOP + rows * (CELL + GAP) + 14
    out.append(f'<text x="{LEFT}" y="{fy + 10}" font-size="10" fill="{th["text"]}">'
               f'Cada contribución es una fuente de calor · diferencias finitas, '
               f'α={ALPHA}, λ={LAMBDA}</text>')
    lx = width - 16 - 5 * (CELL + 2) - 64
    out.append(f'<text x="{lx}" y="{fy + 10}" font-size="9" fill="{th["text"]}">frío</text>')
    for i, k in enumerate((0, 4, 8, 12, 15)):
        out.append(f'<rect x="{lx + 26 + i * (CELL + 2)}" y="{fy + 1}" width="{CELL}" '
                   f'height="{CELL}" rx="2" fill="{pal[k]}"/>')
    out.append(f'<text x="{lx + 26 + 5 * (CELL + 2) + 4}" y="{fy + 10}" font-size="9" '
               f'fill="{th["text"]}">calor</text>')
    by = fy + 24
    bw = cols * (CELL + GAP) - GAP
    out.append(f'<rect x="{LEFT}" y="{by}" width="{bw}" height="2" rx="1" '
               f'fill="{th["ramp"][0]}"/>')
    out.append(f'<rect x="{LEFT}" y="{by}" width="0" height="2" rx="1" fill="{th["accent"]}">'
               f'<animate attributeName="width" from="0" to="{bw}" dur="{total:.2f}s" '
               f'repeatCount="indefinite"/></rect>')
    out.append("</svg>")
    return "\n".join(out)


def main():
    user = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GITHUB_USER", "cnunezv")
    outdir = sys.argv[2] if len(sys.argv) > 2 else "dist"
    if os.environ.get("CONTRIB_HTML"):
        grid, start = parse_levels(open(os.environ["CONTRIB_HTML"], encoding="utf-8").read())
    else:
        grid, start = fetch_levels(user)
    frames = simulate(grid)
    os.makedirs(outdir, exist_ok=True)
    for theme in THEMES:
        path = os.path.join(outdir, f"heat-{theme}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(render(grid, start, frames, theme))
        print(path, os.path.getsize(path), "bytes")


if __name__ == "__main__":
    main()
