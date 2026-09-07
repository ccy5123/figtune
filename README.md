# figtune

English · **[한국어](README.ko.md)**

A desktop tool that fine-tunes an already-drawn matplotlib/seaborn figure in a
GUI and leaves the result as **reproducible Python code**.

```bash
pip install "figtune[gui]"
figtune plot_fig3.py
```

---

## What it does

The input is always a **nearly-finished figure**. You already have a working
plotting script; figtune only adjusts how the result looks.

**In scope** — fonts (family, size, weight, color), text content and position,
inserting arbitrary text, figure size, line and marker colors and sizes, spine
visibility and offset, tick direction/length/spacing, grids, legend placement
and style, axis limits and scales, multi-panel spacing, (a)(b)(c) panel labels,
merging several figures into a layout of your choosing, and PNG/PDF/SVG export.

**All at once** — apply a font (`Ctrl+Shift+F`) or a size (`Ctrl+Shift+S`) to
every piece of text in the figure. Sizes can be set to one value or scaled;
scaling keeps the size difference between titles and ticks. You can also select
several elements and edit their shared properties together. However many items
change, undo takes one step.

**Out of scope** — the underlying data, plot types, adding or removing series,
curve fitting, remapping seaborn semantics (`hue`/`style`). Anything that
requires the data or the functions to change is outside the tool.

---

## Core design: your code is never modified

Because the scope is limited to presentation, figtune **neither reads nor
edits** your plotting code. It runs the script as-is to obtain a live `Figure`
and layers overrides on top of it.

```
run plot_fig3.py → Figure → GUI editing → spec → code generation
```

There are two artifacts.

| File | Role |
|---|---|
| `plot_fig3.figtune.yaml` | The spec. Single source of truth. Human-readable and editable |
| `plot_fig3_style.py` | The generated override module |

Only **two lines** are added to your script, and only after you confirm.

```python
from plot_fig3_style import apply_style
apply_style(fig)
```

This structure means arbitrary Python never has to be parsed. The code we read
and write is 100% code we generated, so the round trip is safe by construction.
Plotting code wrapped in loops or helper functions is no problem either — only
the result of running it is inspected.

---

## How data is handled

**figtune does not hold your data.** The script holds it, and figtune re-runs
the script. This is the opposite of Origin's OLE embedding, which stores the
graph and its data sheet inside the target file.

| | Origin (embedded) | figtune |
|---|---|---|
| What goes into the deck/document | Graph + raw data | Image + spec (≈1KB) + source fingerprint |
| File size | Grows with the data | Essentially unchanged |
| Updating data | Manual rework in Origin | Re-run the script |
| Sharing externally | Raw data goes along | Only the image and the styling |

This choice comes with a hole. Since the data is not carried along, **you cannot
tell which data a figure came from.** The March slide and the June slide may
look identical yet come from different numbers.

So instead of the data, a **fingerprint of the data** is recorded. Files the
script reads while running are captured with `sys.addaudithook`, and their path,
size, and SHA-256 go into the spec. This works in both in-process mode and
`--python` subprocess mode.

```bash
figtune refresh deck.pptx --check
# will change  slide 3 / plot_fig3.py  [data modified 1]
```

`--check` touches nothing and only reports what would change.

### There are two anchors

| What | Relative to | Why |
|---|---|---|
| Script path | **The deck (pptx)** | The deck has to point at the script |
| Data the script reads | **The script** | Execution chdirs into the script's directory |
| Recorded data sources | **The script** | So fingerprints survive moving the project |

```
project/
├── slides/deck.pptx          →  script = "../analysis/plot_a.py"
└── analysis/
    ├── plot_a.py             →  pd.read_csv("data.csv")
    └── data.csv              →  recorded as: "data.csv"
```

`Payload.for_deck(script, deck, spec)` computes the deck-relative path
automatically. When a relative path is impossible — a different drive, say — an
absolute path is stored instead.

Moving the whole project folder keeps refresh working. Recording absolute paths
would make the same file register as "gone + added", and a false alarm makes
every warning worthless. When the contents (SHA-256) match and only the path
differs, it is treated as "moved" and not counted as a change.

### Data changes and code changes are told apart

Fingerprint verification was originally there to catch "the source script
changed", but changed data trips the same wire. Folding both into one warning
trains users to ignore warnings, and then the genuinely dangerous case — an
index shifting so the color lands on the wrong line — slips through. So the
source fingerprints separate the cause and the message differs.

- Data only → "The input data changed. A different figure is expected."
- Code changed → "The source script changed. Re-matching is needed."

### What it will not do

Editing, filtering, and fitting data are out of scope. That is the script's job.
Once figtune starts touching data, the premise that "this tool only touches
presentation" collapses — and with it the reason it never has to parse your code.

---

## Normal form

Every piece of figtune state exists only in normal form. Fixing a normal form
makes spec comparison, git diffs, and round-trip verification mechanical.

### Spec normal form

**What is guaranteed** (all verified by tests)

| Property | Meaning |
|---|---|
| Idempotent | `N(N(x)) = N(x)` |
| Deterministic | The same content always serializes to the same bytes |
| Closed | Every operation leaves the result in normal form |
| Round trip | `parse(codegen(N(s))) = N(s)` |

Folding rules: colors to lowercase hex, `solid`→`-`, `dashed`→`--`, empty marker
spellings to `none`, weight `700`→`bold`, integer legend location `2`→`upper
left`, tuple→list, `None` and empty dicts dropped, unresolvable selectors
dropped. Keys are sorted in **application order** — if application order and
sort order diverge, the guarantee that "it re-applies exactly as saved" breaks,
so a single table (`canon.KIND_ORDER`) is shared by apply, codegen, and canon.

**What is not guaranteed.** There is no semantic minimization: "same figure
implies same spec" does not hold. Achieving that would mean comparing against
what the script already drew and deleting redundant overrides, which would make
the spec depend on the script's contents. The moment the script changed, a
setting the user explicitly made would silently vanish — the most dangerous
failure in figtune. So the normal form is **syntactic**.

**It is applied in two stages.** During editing only the override table is
normalized; user-text ids are reassigned only at open/save boundaries. If ids
shifted mid-edit, the selector the GUI is holding (`ax0.text:t002`) would start
pointing at a different piece of text.

### Script normal form

```python
<imports and data preparation>

def plot(ax):
    ...

if __name__ == "__main__":
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=...)
    plot(ax)
```

```bash
figtune normalize plot_a.py --check     # report only
figtune normalize plot_a.py             # writes plot_a_norm.py
figtune merge *.py -o quad.py --normalize
```

The original is never overwritten by default; `--in-place` must be explicit.

**It only works on a recognizable subset.** Converting arbitrary Python to the
normal form is impossible in general. Outside that subset, figtune reports what
tripped it and on which line, then stops — guessing would silently change your
figure.

**Accepted**

- Drawing calls such as `ax.plot(...)`
- Simple assignments such as `im = ax.imshow(...)`, `ax2 = ax.twinx()`
- Follow-up drawing on assigned names (`ax2.plot(...)`, `cb.set_label(...)`).
  The set of drawing targets grows transitively
- `fig.colorbar(...)` → rewritten to `ax.figure.colorbar(...)`. A colorbar
  attaches to the axes it is handed, so it keeps its place in a merged grid
- Layout and output calls such as `plt.show()` and `fig.tight_layout()` are
  dropped (the standalone block and the merge script handle those instead)

**Rejected**

- `subplots()` creating multiple axes, called more than once, or absent
  entirely (seaborn `relplot` and friends)
- Drawing statements inside conditionals or loops
- `fig.suptitle(...)` — it belongs to the whole figure, so merging would let
  panels overwrite each other and only the last would survive
- pyplot state calls such as `plt.title(...)` — there is no way to know which
  axes they mean
- Statements that use a drawing target for **something other than drawing**,
  such as `print(im.get_array().max())`. Moving it would shift execution from
  import time to the `plot()` call
- Module-level use of a name that would move inside the function (prevents
  `NameError`)

The test is the **outermost call of the statement**. `cb.set_label(...)` is
drawing; `print(im.get_array())` has a target call inside it but the statement
itself is output.

---

## Merging figures

There are two modes, and **they produce different things.** Knowing which one
you are using matters.

| | Mode A · montage | Mode B · subplot |
|---|---|---|
| Modifies the source | Not needed | Needs `plot(ax)` exposed |
| Output | Composited SVG | **A real Figure + an ordinary Python script** |
| One `ax` object? | No | Yes |
| Unit of editing | Per panel | The whole thing |
| Depends on figtune | Yes | No |

### Merging in the GUI

Open the figures you want to merge **as tabs** with `Ctrl+O`, then press
`Ctrl+M`. Sweep a grid to pick the size, the way you insert a table in
PowerPoint, and a composer screen appears. There you merge or split cells and
drop an open tab into an empty cell with its `+`. **Save and close** and the
result opens as a new tab.

A 3×2 grid can hold two double-width panels and two single ones. Each panel's
code is copied into the result, so **that one file is self-contained** — delete
or move the originals and the figure still draws. The trade-off is that later
edits to a panel are not reflected. You have to merge again.

Almost any script can be merged. If there is no `plot(ax)` it is wrapped
automatically; state-based scripts that only use `plt.plot(...)` work, as do 3D
and polar, as do scripts that are already N panels (those take N cells). The
only thing that cannot be merged is a script that locates paths with `__file__`,
and you are told why at the moment you drop it.

If a panel reads data from a file, **the path is rewritten relative to where the
merged file goes.** Panels whose data lives in different folders still merge.
Paths are not converted to absolute — the folder has to keep working when you
send it to someone else. The original files are never modified.

### Prefer mode B when it is available

Change the panel script like this. Running it standalone still works.

```python
def plot(ax):
    ax.plot(...)
    ax.set_xlabel('Time (h)')

if __name__ == '__main__':
    fig, ax = plt.subplots(); plot(ax)
```

figtune then generates a merge script. The result is an ordinary matplotlib
Figure, so you can open it in figtune and edit it as a whole, and the generated
`*_style.py` runs without figtune. If the conditions are not met, figtune says
what is missing and stops — silently falling back to mode A would leave you
unsure which artifact you are looking at.

The (a)(b)(c) labels the merge script creates are editable too. More broadly,
any annotation your script added with `ax.text()` shows up in the tree as
`ax0.txt0`. They **cannot be deleted**, though — deleting them would only bring
them back on the next run. Use `visible=False` to hide one, and that is recorded
as code as well.

### Why mode A does not move axes

matplotlib does not support moving axes between figures. Neither
`ax.figure = other` nor `ax.set_figure(other)` refreshes the transform chain, so
ticks smear and content clips. This was verified by measurement. Mode A
therefore composites at the SVG level.

**Alignment is based on the axes box.** Naive tiling is not publishable: when
y-label lengths differ, the plot frames land in different places on each panel.
Each panel's axes position is knowable (`ax.get_position()` × figure size), so
left edges are aligned per column and top edges per row.

**Size is matched by re-rendering, not by scaling.** Uniform scaling cannot
match width and height at once for panels of differing aspect ratio, and
non-uniform scaling distorts the text. So the margin taken by axis labels is
kept in inches and only the plot frame is resized to the target, then
re-rendered. It matches exactly at scale 1.

```python
from figtune.core.montage_build import MontageSpec, PanelRef, build

ms = MontageSpec(rows=2, cols=2, panels=[PanelRef(script=f"p{i}.py")
                                         for i in range(4)])
result = build(ms, base_dir="analysis/")     # (a)(b)(c)(d) automatically
```

---

## 3D plots

Selecting a 3D axes brings up elevation, azimuth, roll, and zoom. `view_init`
resets the arguments you omit to their defaults, so they are applied as a batch
— the same trap as legends and title padding.

---

## Safeguards

**Fingerprint verification.** Index-based addresses like `ax0.line1` break
**silently** when the source script changes; the line you meant to recolor
becomes a different line. A fingerprint (point count, first and last
coordinates, label) is stored for each artist and checked on load. A mismatch
warns and proposes label-based re-matching candidates, but **never applies them
without your approval.**

**null means untouched.** Only keys present in the spec become override code. A
value your script set is not overwritten merely because you once opened the GUI.

**Manual-edit detection.** If logic (if/for/assignment) appears in the generated
style module, figtune gives up parsing and switches to read-only rather than
quietly mangling it.

---

## Layout

```
figtune/
├── core/              # UI-agnostic · pure Python · depends only on matplotlib + pyyaml
│   ├── props.py       # Property registry — single source for GUI, apply, codegen, parse
│   ├── selector.py    # Addressing (ax0.line1, ax0.spine:top, ax0.xtick.major)
│   ├── spec.py        # Schema + YAML serialization
│   ├── fingerprint.py # Fingerprint creation and comparison
│   ├── introspect.py  # Figure → node tree
│   ├── apply.py       # spec → live Figure
│   ├── codegen.py     # spec → style module
│   ├── parse.py       # style module → spec (stdlib ast; no libcst)
│   ├── runner.py      # Run a script and recover the Figure
│   ├── history.py     # undo/redo
│   ├── session.py     # Facade. The only thing a frontend calls
│   ├── hit.py         # Click coordinates → edit target (direct manipulation)
│   ├── drag.py        # Drag → property value
│   ├── snap.py        # Snapping geometry (pure functions)
│   ├── palette.py     # matplotlib's named colors
│   ├── layout.py      # Grow the paper when the axes run off it
│   └── typefaces.py   # Fonts usable in the figure (matplotlib's list)
├── i18n/              # Message catalog. Qt-free, so core uses it too
├── config.py          # User settings (language choice and so on)
├── ui/qt/             # PySide6 adapter
│   ├── direct.py      # Cursor · drag · in-place editing
│   ├── minitoolbar.py # Context toolbar that appears where you select
│   ├── targetdialog.py# Tabbed editor for a single target
│   ├── fontpicker.py  # Font dropdown (preview + install guidance)
│   ├── palette.py     # Color picker (named colors first)
│   ├── widgets.py     # Property kind → widget (shared by three screens)
│   └── fonts.py       # Whether the UI can render Korean
└── cli.py
```

`core` does not import PySide6. That boundary is the only thing making a web or
PowerPoint adapter possible later.

To add a property, edit `props.REGISTRY` and nothing else. The inspector widget,
code generation, and parsing all derive from it.

---

## Execution modes

| Mode | Behavior | When |
|---|---|---|
| In-process (default) | `exec` the script in figtune's own interpreter | figtune is installed in your analysis environment |
| Subprocess (`--python`) | Run in the given interpreter and recover the Figure by pickle | figtune lives in another venv or is a frozen app |

```bash
figtune plot_fig3.py --python .venv/bin/python
```

**Why it is needed.** "This script works" is a fact about *your* environment,
not about figtune's interpreter. If figtune sits in a separate venv or a
PyInstaller bundle, `import seaborn` searches the app's `sys.path` rather than
your site-packages. Running the script in your environment and receiving only
the resulting Figure solves it.

**Limitation.** A Figure pickle is coupled to the matplotlib version. If the two
minor versions differ, figtune refuses and says why — it will not hand you a
quietly broken Figure.

---

## Direct manipulation

Origin's interaction model, carried over. **Where you click is what you edit.**

| Where you click | Target | What opens |
|---|---|---|
| Title · axis label | The text | One click puts a caret there; dragging moves it |
| Tick labels · axis line | The axis | Ticks + minor ticks + axis line + grid + limits (5 at once) |
| Legend | The legend | Drag to move (`best` fixes its place the moment you drag) |
| Line · points | The data | Overlaps let you choose |
| Empty plot area | The layer | Select, then drag a corner to resize |
| Page margin | The page | Figure size · background |

**One target bundles several selectors.** Double-clicking an axis brings ticks,
axis line, grid, and limits onto one screen — the same work as visiting four
different branches of the tree, but matched to the unit you think of as "this
axis". Same structure as Origin's Axis Dialog.

**Editing has three layers.** Selecting pops the three or four most-used
properties right there (mini toolbar), `⋯` or a double-click expands everything
(tabbed dialog), and the right-hand panel is always on. What goes on the toolbar
is decided by `props.PRIMARY` — put everything on it and the toolbar becomes a
dialog, losing its reason to exist.

### What separates a click from a drag

One click on a title is a **caret**; dragging **moves** it. At the moment of the
press there is no way to know which, so the distance moved (3px) decides. Just
placing a caret touches nothing in the spec until you type, and Esc reverts.

### The cursor announces what is possible

| Position | Cursor |
|---|---|
| Title · axis label · legend | ✛ can be moved |
| Edge of a selected axes box | ↔ ↕ can be resized |
| Corner | ⤢ ⤡ |

**Resize handles appear only after selection.** Always-on handles would
intercept the click meant for the axis line, making axis editing unreachable.

### Selecting several at once

`Shift` or `Ctrl` click on the canvas selects multiple elements. As in
PowerPoint, both keys behave the same (toggle-add). Range selection is the
tree's job.

With several selected, the inspector shows **only shared properties**. Showing a
property that only one of them has means changing it would apply to only some —
what you see must be what applies to all. Fields whose values differ are left
blank. The selection can also be dragged as a group.

`Delete` removes things — but **only text figtune inserted**. Anything the
script created would come back on the next run, so the menu entry stays greyed
out for those.

### Dragging snaps to other elements (snap)

Edges and centers align, and a guide line shows what you snapped to. Hold `Alt`
while dragging to suppress it. The decision is a pure geometry function
(`core/snap.py`), so it is verified without pixels.

### Colors start from names

Clicking a color field shows matplotlib's **named colors** first. The 8 base
colors and 10 Tableau colors are immediate; the 148 CSS colors expand with `+`
(including find-by-name). With only a color wheel you cannot pick a color
already used in the figure — placing the same blue next to a line drawn in
`tab:blue` would mean matching it by eye.

Values are always stored as hex, since the spec folds colors into hex normal
form; passing a name straight through would make the screen and the file
disagree right after saving. The swatch button prints the name alongside
instead (`tab:blue  #1f77b4`).

### Hover reads a precomputed map

`get_window_extent()` re-lays out the glyphs of every tick label, costing
**12ms** for one hit test on a two-panel figure. Calling it on every mouse move
spends three quarters of a 60fps budget on the cursor. Geometry only changes on
redraw, so it is measured once per draw and afterwards only rectangles are
compared.

```
hover  12.766 ms → 0.0099 ms   (76.4% → 0.06% of the budget)
click                1.308 ms   (mostly artist contains())
```

### The two histories never touch each other

| Action | Owner | How to undo |
|---|---|---|
| Zoom · pan (viewing) | Toolbar history | Toolbar ← / Home |
| Layout · font · color (editing) | figtune history | Ctrl+Z |

matplotlib's navigation stack stores **axes positions** alongside view limits
and restores them together. Left alone, the toolbar's back button would revert
an axes box you moved in figtune on screen only, leaving the spec as it was, so
screen and code would disagree. The toolbar is therefore subclassed to restore
views only.

Conversely, limits changed by zoom and pan **are recorded in the spec.** Without
that, the exported image would contain the zoom while the generated code would
not, breaking the guarantee that screen and code agree. The view the script
produced is used as the baseline and only differences are stored, so an
untouched figure never acquires overrides.

### The paper fits the content

There is one rule: **paper = bounding box of every component + margin (0.1in).**
All four directions behave alike, and it shrinks as well as grows. Raise the
title and the top grows; lower it past where it started and the paper ends up
smaller than it began.

The bounding box is the tight bbox including title, axis labels, ticks, and
legend. Measuring only the axes box means text runs outside and clips even when
the box is inside `[0,1]`.

The arithmetic is done in **inches**. In figure coordinates (0–1) the same 0.5
means a different physical position the moment the paper size changes, so
untouched panels would drift. Changing the paper size makes matplotlib re-lay
out, so it iterates up to three times until it converges (two in practice).

> The first time you drag the layout, the margins your script left are recomputed
> under this rule. To pin the format, set `Size (in)` in the inspector.

---

## Language and fonts

Korean and English are supported. The language is decided in this order.

```
--lang  >  FIGTUNE_LANG  >  config file  >  system locale  >  Korean
```

```bash
figtune --lang en plot_fig3.py
FIGTUNE_LANG=en figtune plot_fig3.py
```

The GUI switches from the `Language` menu with no restart, and the choice is
kept in `~/.config/figtune/config.json`. Language names in the menu are always
written in that language (한국어 / English) — it has to be the way out when you
are stuck in a language you cannot read.

### Without fonts it falls back to English

Base WSL images and slim containers have no CJK fonts. Qt raises no exception
when it cannot draw a glyph; it quietly prints a box (□), so the whole screen
can break with no way for the user to know why.

So it is measured once at startup. If Korean cannot be drawn, the UI drops to
English and the install command is shown, chosen by distribution.

```
This environment has no Korean font, so Korean text appears as boxes.
The interface has been switched to English.

  sudo apt install -y fonts-noto-cjk fonts-nanum && fc-cache -f
```

If you pick Korean from the menu without the fonts, figtune **refuses and says
why.** Switching anyway would turn the menu itself into boxes, closing off the
way back.

The check uses `QFontMetrics.inFont()`, which accounts for Qt's font fallback
and therefore measures "does this actually draw". Looking only at
`QFontDatabase.families()` misses the case where the default font renders Korean
through a fallback.

> Korean **inside the matplotlib canvas** is a separate matter. To use Korean in
> the figure, set `plt.rcParams["font.family"]` in your script. figtune only
> touches presentation, so that choice belongs to the script.

### Fonts inside the figure

The font list is **matplotlib's**. matplotlib is what draws the text in the
figure, so showing Qt's list would mean your choice is quietly substituted.

The dropdown draws each font **in itself**. Fonts that can render Korean carry
an `AaBbCc 123 가나다` sample, so you need not guess from the name. The `+`
button shows recommended fonts you do not have yet, along with **install
commands** — figtune does not download fonts. A tool that quietly reaches out to
the network behaves unpredictably on an intranet or offline, and brings license
responsibility with it.

Setting a `default font` rides along in the spec's `rcparams` and reaches the
generated code, so someone else running that code gets the same font.

**matplotlib caches its font list and does not refresh it when you install
fonts.** On the machine this project was built on, installing 42 Nanum fonts
still left matplotlib reporting no Korean fonts at all — the cache was two
months old. So the cache is compared against the actual disk on every open and
quietly rebuilt when they disagree (12ms to check, 148ms to rebuild).

### Math

matplotlib mathtext, unchanged. The delimiter is a **single `$`**.

```
$\frac{dC}{dt} = k(C_\infty - C)$
Concentration $C_{\mathrm{max}}$ (mg L$^{-1}$)
```

`$$...$$` is a parse error. Type it directly into the in-place editor.

### Artifacts are language-independent

The generated `*_style.py` and merge scripts are **always English**. If file
bytes varied with the user's language, the determinism the normal form
guarantees would break and the same spec would produce different diffs for
different people. A regression test pins this down.

---

## Known limitations

- **Arbitrary code execution.** In-process mode `exec`s your script in an
  isolated namespace. It is required for live preview, but only open files you
  trust. Subprocess mode is safer in this respect, being a separate process.
- **Screen dpi and output dpi are separate.** The spec's `dpi` is used for
  export only; the screen draws at a display scale fitted to the viewport. Tying
  them together makes the figure overflow the canvas and clip.
- **rcParams do not apply retroactively.** They do not reach artists that
  already exist, so per-element overrides are used instead.
- Manual positioning can conflict with `constrained_layout` when it is enabled.
- seaborn artist ordering is undocumented. Fingerprint verification compensates.
- **The z-label and z-ticks of a 3D axes are not in the tree.** So "everywhere"
  font and size changes skip the z-axis text of a 3D figure.
- Merging copies each panel's code in, so editing a panel means merging again.
- The first layout drag resets the margins your script left to `layout.MARGIN`
  (0.1in). That is the price of keeping "paper = content bounds + margin" as a
  single rule.

---

## Tests

```bash
python -m pytest tests/ -q
```

Four things are pinned down above all.

1. **Lossless round trip** — not one value disappears in spec → code → spec.
2. **The generated code actually runs** — running the hooked script in a
   separate process produces output byte-identical to the GUI render. Code that
   merely parses but behaves differently would make the whole tool a lie.
3. **Edit order does not matter** — `ax.set_title(text, pad=)` internally resets
   font properties to the rcParams defaults, so editing "bold, then padding"
   used to lose the bold silently. That is a bug where the screen and a re-run
   diverge, so it is nailed down by a regression test.
4. **Language independence of artifacts** — the same spec produces the same
   bytes regardless of UI language. Translations rot quietly, so the suite also
   checks for missing catalog entries, surplus keys, lost placeholders, and
   Korean left outside `_t()`.

---

## PowerPoint integration

The structure follows IguanaTeX: alongside the image, **the source that made it
is embedded in the shape**, and selecting the shape reopens it for editing. The
source is compressed into the shape's alt text (usually under 1KB), so it
travels with the presentation. A computer without figtune can still present;
only editing requires figtune.

The most useful feature is **refreshing a whole deck.** When the data or the
model changes, instead of regenerating and re-pasting each embedded figure, one
line does it.

```bash
figtune refresh deck.pptx
```

Each figure's source script is re-run and regenerated, then swapped in **with
position, size, rotation, and z-order preserved.** If regeneration cost the
presenter the placement they arranged by hand, there would be no reason to use
the tool. Figures whose script cannot be found are skipped with a reason.

It works with python-pptx alone, without PowerPoint.

```python
from figtune.office import pptx_link as PL

PL.insert(slide, "fig.png",
          PL.Payload(script="plot_fig3.py", spec=spec, dpi=300),
          left=Inches(1), top=Inches(1), width=Inches(6))
```

### Safe to share

**A real image goes into the slide.** The spec rides along as alt-text metadata
only, and the image is embedded in the pptx, not linked externally. So a
computer without figtune simply sees a picture and presents it. Same property as
IguanaTeX, and locked down by a test — it fails if this ever becomes an external
link.

### Vector output (optional, rendering unverified)

With `vector=True` an SVG is embedded **together with a PNG fallback**. OOXML
carries this as:

```xml
<a:blip r:embed="rIdPng">              <!-- what older viewers see -->
  <a:extLst>
    <a:ext uri="{96DAC541-7B7A-43D3-8B79-37D633B846F1}">
      <asvg:svgBlip r:embed="rIdSvg"/> <!-- what PowerPoint 365 draws -->
    </a:ext>
  </a:extLst>
</a:blip>
```

A viewer that does not know SVG sees the PNG, so sharing stays safe. The package
structure (parts, relationships, content types, extension GUID) is verified by
tests, but **whether PowerPoint actually renders it as vector has not been
confirmed** — there is no PowerPoint in a Linux container. The default is PNG;
vector must be turned on explicitly.

The SVG and the PNG are always taken from the same Session. Rendering them
separately would let the two files disagree for scripts that depend on random
numbers or the clock.

### Add-in (unverified)

`figtune/office/FigTune.bas` is the `.ppam` VBA add-in source. It offers insert,
edit, and refresh from the ribbon. **This VBA has never been run in
PowerPoint** — it was written on Linux. The Python side (the `edit`/`render`/
`refresh` subcommands and `vba_bridge`) passes its tests, so the VBA needs to be
exercised on Windows and polished. Check the `Shell` wait handling and path
quoting in particular.

VBA has no zlib. Reimplementing the payload encoding in VBA would risk drifting
from the Python side, so it delegates to `figtune.office.vba_bridge` and the
add-in only passes files around.

---

## Roadmap

- **v1** — Linux release. Batch layout of several figures is already here (see
  "Merging figures"). Saving and reapplying style profiles was dropped from
  scope: spec keys are positional (`ax0.line0`), so laying one figure's spec on
  another puts formatting on the wrong series. Capturing only the portable part
  would need a separate pattern language, which was judged not worth it.
- **v2** — seaborn semantic layer, web frontend adapter
- **v3** — VBA add-in verified for real, Mac support, EMF vector output (via
  Inkscape)

MIT
