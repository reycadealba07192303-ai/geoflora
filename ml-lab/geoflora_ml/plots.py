"""Static report figures (matplotlib, PNG).

Palette: validated reference palette - categorical slot 1 (blue) / slot 2 (orange) for paired
series, one-hue blue ramp for magnitude (confusion matrix), neutral greys for reference lines.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"
NEUTRAL = "#8a8984"
SERIES_1 = "#2a78d6"  # blue
SERIES_2 = "#eb6834"  # orange
BLUE_RAMP = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SEQ_CMAP = LinearSegmentedColormap.from_list("geoflora_blues", BLUE_RAMP)


def _style(ax, title: str | None = None):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_2, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, color=TEXT, fontsize=11, loc="left")
    ax.xaxis.label.set_color(TEXT_2)
    ax.yaxis.label.set_color(TEXT_2)


def _fig(w, h, ncols=1):
    fig, axes = plt.subplots(1, ncols, figsize=(w, h), facecolor=SURFACE)
    return fig, axes


def _save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def confusion_matrix_plot(cm: np.ndarray, labels: list[str], path: Path, normalize: bool) -> None:
    data = cm.astype(float)
    if normalize:
        rows = data.sum(axis=1, keepdims=True)
        data = np.divide(data, rows, out=np.zeros_like(data), where=rows > 0)
    n = len(labels)
    size = max(4.5, 0.55 * n + 2.5)
    fig, ax = _fig(size + 1, size)
    im = ax.imshow(data, cmap=SEQ_CMAP, vmin=0, vmax=1 if normalize else max(1, data.max()))
    ax.set_xticks(range(n), labels, rotation=45, ha="right", fontsize=8, color=TEXT_2, style="italic")
    ax.set_yticks(range(n), labels, fontsize=8, color=TEXT_2, style="italic")
    ax.set_xlabel("Predicted species", color=TEXT_2)
    ax.set_ylabel("True species", color=TEXT_2)
    ax.set_title("Confusion matrix (row-normalised recall)" if normalize else "Confusion matrix (image counts)",
                 color=TEXT, fontsize=11, loc="left")
    for s in ax.spines.values():
        s.set_visible(False)
    if n <= 20:
        hi = (1 if normalize else data.max()) * 0.55
        for i in range(n):
            for j in range(n):
                txt = f"{data[i, j]:.2f}" if normalize else f"{int(cm[i, j])}"
                ax.text(j, i, txt, ha="center", va="center", fontsize=8, color=SURFACE if data[i, j] > hi else TEXT)
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.outline.set_visible(False)
    cb.ax.tick_params(colors=TEXT_2, labelsize=8)
    _save(fig, path)


def training_curves(history: dict, phases: list[str], path: Path) -> None:
    fig, axes = _fig(10, 3.8, ncols=2)
    epochs = np.arange(1, len(history.get("loss", [])) + 1)
    switch = next((i for i, p in enumerate(phases) if p == "finetune"), None)
    for ax, metric, title in ((axes[0], "loss", "Loss"), (axes[1], "accuracy", "Accuracy")):
        _style(ax, title)
        if metric in history:
            ax.plot(epochs, history[metric], color=SERIES_1, linewidth=2, label="Training")
        if f"val_{metric}" in history:
            ax.plot(epochs, history[f"val_{metric}"], color=SERIES_2, linewidth=2, label="Validation")
        if switch is not None:
            ax.axvline(switch + 0.5, color=NEUTRAL, linewidth=1, linestyle="--")
            ax.text(switch + 0.6, ax.get_ylim()[1], " fine-tuning", va="top", fontsize=8, color=TEXT_2)
        ax.set_xlabel("Epoch")
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.ticklabel_format(axis="y", useOffset=False)
        ax.legend(frameon=False, fontsize=9, labelcolor=TEXT_2)
    _save(fig, path)


def reliability_diagram(bins_raw: list[dict], bins_cal: list[dict], path: Path, temperature: float) -> None:
    fig, axes = _fig(9, 3.8, ncols=2)
    for ax, bins, title in ((axes[0], bins_raw, "Raw softmax"), (axes[1], bins_cal, f"Temperature-scaled (T={temperature:.2f})")):
        _style(ax, title)
        ax.plot([0, 1], [0, 1], color=NEUTRAL, linewidth=1, linestyle="--", label="Perfect calibration")
        if bins:
            mids = [(b["lo"] + b["hi"]) / 2 for b in bins]
            width = (bins[0]["hi"] - bins[0]["lo"]) * 0.9
            ax.bar(mids, [b["accuracy"] for b in bins], width=width, color=SERIES_1, label="Observed accuracy")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_xlabel("Max softmax score")
        ax.set_ylabel("Accuracy")
        ax.legend(frameon=False, fontsize=8, labelcolor=TEXT_2, loc="upper left")
    _save(fig, path)


def score_histogram(known: np.ndarray, unknown: np.ndarray | None, threshold: float, path: Path, score_name: str) -> None:
    fig, ax = _fig(7, 3.8)
    _style(ax, f"Unsupported-species score distribution ({score_name}, test sets)")
    lo = min(known.min(), unknown.min()) if unknown is not None and len(unknown) else known.min()
    bins = np.linspace(lo, max(1.0, known.max()), 30)
    data, colours, labels = [known], [SERIES_1], [f"Supported species (n={len(known)})"]
    if unknown is not None and len(unknown):
        data.append(unknown)
        colours.append(SERIES_2)
        labels.append(f"Unsupported species (n={len(unknown)})")
    ax.hist(data, bins=bins, color=colours, label=labels, rwidth=0.9)  # side-by-side bars, no colour blending
    ax.axvline(threshold, color=TEXT, linewidth=1.5, linestyle="--", label=f"Threshold from validation ({threshold:.3f})")
    ax.set_xlabel(score_name)
    ax.set_ylabel("Images")
    ax.legend(frameon=False, fontsize=8, labelcolor=TEXT_2)
    _save(fig, path)
