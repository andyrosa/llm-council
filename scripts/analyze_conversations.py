"""Aggregate model stats from saved conversations and plot them.

Computes per-model average percentile rank (0 = best, 100 = worst, computed as
(rank-1)/(n-1)*100), normalized delay (elapsed_time / fastest model per
question), and average cost from stage 1 responses. By default it also writes a
PNG showing delay vs. percentile rank and cost vs. percentile rank in cents
(use ``--no-plot`` to skip).
"""

import argparse
import base64
import io
import json
import os
import shutil
import subprocess
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from backend.config import DATA_DIR


def _percentile(rank: float, total: int) -> float:
    if total <= 1:
        return 0.0
    return ((rank - 1) / (total - 1)) * 100.0


def _ensure_matplotlib():
    try:
        import matplotlib.pyplot as plt  # type: ignore
        return plt
    except ImportError:
        pass

    uv_path = shutil.which("uv")
    if not uv_path:
        print("matplotlib not installed and uv not found; skip plotting")
        return None

    print("matplotlib not installed; attempting to install with uv...")
    try:
        subprocess.run([uv_path, "pip", "install", "matplotlib"], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"matplotlib install failed via uv: {exc}; skip plotting")
        return None

    try:
        import matplotlib.pyplot as plt  # type: ignore
        return plt
    except ImportError:
        print("matplotlib still unavailable after installation; skip plotting")
        return None


def _load_conversations(data_dir: str) -> List[Dict]:
    conversations: List[Dict] = []
    if not os.path.isdir(data_dir):
        return conversations
    for name in os.listdir(data_dir):
        if not name.endswith(".json"):
            continue
        path = os.path.join(data_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                conversations.append(json.load(handle))
        except (OSError, json.JSONDecodeError):
            continue
    return conversations


def _copy_image_to_clipboard(fig) -> bool:
    """Copy the figure image to the Windows clipboard without writing a file."""

    try:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        ps_script = r"""
$ErrorActionPreference = 'Stop'
$data = [Console]::In.ReadToEnd()
$bytes = [Convert]::FromBase64String($data)
$ms = New-Object System.IO.MemoryStream(,$bytes)
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$img = [System.Drawing.Image]::FromStream($ms)
[System.Windows.Forms.Clipboard]::SetImage($img)
"""

        proc = subprocess.run(
            [
                "powershell",
                "-NoLogo",
                "-NoProfile",
                "-STA",
                "-Command",
                ps_script,
            ],
            input=b64.encode("ascii"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if proc.returncode == 0:
            return True
        print(f"Clipboard copy failed: {proc.stderr.decode(errors='ignore').strip()}")
        return False
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Clipboard copy failed: {exc}")
        return False


def _get_cost(entry: Dict) -> Optional[float]:
    usage = entry.get("usage") or {}
    for key in ("cost", "upstream_inference_cost"):
        val = usage.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    val = entry.get("cost")
    if isinstance(val, (int, float)):
        return float(val)
    return None


def _collect_stage1_times(stage1: List[Dict]) -> Tuple[Optional[float], Dict[str, float]]:
    per_model: Dict[str, float] = {}
    times: List[float] = []
    for item in stage1:
        model = item.get("model")
        elapsed = item.get("elapsed_time")
        if not model or not isinstance(elapsed, (int, float)):
            continue
        per_model[model] = float(elapsed)
        times.append(float(elapsed))
    if not times:
        return None, per_model
    return min(times), per_model


def _collect_percentiles(message: Dict) -> Dict[str, Tuple[float, int]]:
    meta = message.get("metadata") or {}
    label_map: Dict[str, str] = meta.get("label_to_model") or {}
    total_models = len(label_map) if label_map else None

    aggregate = meta.get("aggregate_rankings")
    if isinstance(aggregate, list) and aggregate:
        percentiles: Dict[str, Tuple[float, int]] = {}
        n = total_models or len(aggregate)
        for entry in aggregate:
            model = entry.get("model")
            avg = entry.get("average_rank")
            count = entry.get("rankings_count") or 0
            if model and isinstance(avg, (int, float)):
                pct = _percentile(float(avg), n)
                cnt = int(count or 1)
                percentiles[model] = (pct * cnt, cnt)
        return percentiles

    stage2 = message.get("stage2") or []
    percentiles: Dict[str, Tuple[float, int]] = defaultdict(lambda: (0.0, 0))
    for ranking in stage2:
        parsed = ranking.get("parsed_ranking") or []
        n = total_models or len(parsed)
        for idx, label in enumerate(parsed):
            model = label_map.get(label)
            if not model:
                continue
            pct = _percentile(idx + 1, n)
            sum_so_far, count_so_far = percentiles[model]
            percentiles[model] = (sum_so_far + pct, count_so_far + 1)
    return percentiles


def compute_stats() -> Tuple[Dict[str, Dict[str, float]], int]:
    conversations = _load_conversations(DATA_DIR)
    accum: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {
            "pct_sum": 0.0,
            "pct_count": 0.0,
            "delay_sum": 0.0,
            "delay_count": 0.0,
            "cost_sum": 0.0,
            "cost_count": 0.0,
        }
    )

    for convo in conversations:
        for message in convo.get("messages", []):
            if message.get("role") != "assistant":
                continue
            stage1 = message.get("stage1") or []
            if not stage1:
                continue

            min_time, times = _collect_stage1_times(stage1)
            percentiles = _collect_percentiles(message)

            for entry in stage1:
                model = entry.get("model")
                if not model:
                    continue
                stats = accum[model]

                cost = _get_cost(entry)
                if cost is not None:
                    stats["cost_sum"] += cost
                    stats["cost_count"] += 1

                elapsed = times.get(model)
                if (
                    min_time is not None
                    and min_time > 0
                    and isinstance(elapsed, (int, float))
                ):
                    stats["delay_sum"] += float(elapsed) / min_time
                    stats["delay_count"] += 1

            for model, (pct_sum, pct_count) in percentiles.items():
                if pct_count:
                    stats = accum[model]
                    stats["pct_sum"] += pct_sum
                    stats["pct_count"] += pct_count

    return accum, len(conversations)


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    formatted = f"{value:.2g}"
    # Ensure at least one decimal place for whole numbers for cosmetic consistency
    if "e" not in formatted.lower() and "." not in formatted:
        formatted = f"{value:.1f}"
    return formatted


def build_rows(stats: Dict[str, Dict[str, float]]):
    rows = []
    for model, data in stats.items():
        avg_pct = data["pct_sum"] / data["pct_count"] if data["pct_count"] else None
        avg_delay = data["delay_sum"] / data["delay_count"] if data["delay_count"] else None
        avg_cost = data["cost_sum"] / data["cost_count"] if data["cost_count"] else None
        rows.append((model, avg_pct, avg_delay, avg_cost))

    rows.sort(key=lambda r: (r[1] if r[1] is not None else float("inf"), r[0]))
    return rows


def print_table(rows) -> None:
    header = f"{'Model':<35} {'AvgPct':>8} {'NormDelay':>10} {'AvgCost(cents)':>15}"
    print(header)
    print("-" * len(header))
    for model, avg_pct, avg_delay, avg_cost in rows:
        cost_cents = avg_cost * 100 if avg_cost is not None else None
        print(
            f"{model:<35} {_fmt(avg_pct):>8} {_fmt(avg_delay):>10} {_fmt(cost_cents):>15}"
        )


def plot_rows(rows, output_path: str, show: bool = False, convo_count: Optional[int] = None) -> None:
    plt = _ensure_matplotlib()
    if plt is None:  # pragma: no cover - optional dependency
        return
    from matplotlib.widgets import Button  # type: ignore

    pct_delay = [(r[1], r[2], r[0]) for r in rows if r[1] is not None and r[2] is not None]
    pct_cost = [
        (r[1], r[3] * 100.0, r[0]) for r in rows if r[1] is not None and r[3] is not None
    ]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    try:
        fig.canvas.manager.set_window_title("Conversation stats")  # type: ignore[attr-defined]
    except Exception:
        pass

    if convo_count is not None:
        fig.suptitle(f"Conversations analyzed: {convo_count}", fontsize=12, y=0.995)

    if pct_delay:
        x, y, labels = zip(*pct_delay)
        axes[0].scatter(x, y, alpha=0.7)
        for xi, yi, label in zip(x, y, labels):
            axes[0].text(xi, yi, label, fontsize=8, ha="left", va="bottom")
        axes[0].set_xlabel("Average Percentile (lower is better)")
        axes[0].set_ylabel("Normalized Delay")
        axes[0].set_title("Delay vs. Percentile", pad=18)
        axes[0].grid(True, alpha=0.2)
    else:
        axes[0].set_title("No delay data")

    if pct_cost:
        x, y, labels = zip(*pct_cost)
        axes[1].scatter(x, y, alpha=0.7)
        for xi, yi, label in zip(x, y, labels):
            axes[1].text(xi, yi, label, fontsize=8, ha="left", va="bottom")
        axes[1].set_xlabel("Average Percentile (lower is better)")
        axes[1].set_ylabel("Average Cost (cents)")
        axes[1].set_title("Cost vs. Percentile (cents)", pad=18)
        axes[1].grid(True, alpha=0.2)
    else:
        axes[1].set_title("No cost data")

    # Add copy-to-clipboard button (copies image) on the title line, top-right
    button_ax = fig.add_axes([0.875, 0.92, 0.075, 0.06])
    copy_button = Button(button_ax, "Copy image")

    def _on_copy(_event):
        try:
            copy_button.label.set_text("")
            fig.canvas.draw_idle()
            _copy_image_to_clipboard(fig)
        finally:
            copy_button.label.set_text("Copy image")
            fig.canvas.draw_idle()

    copy_button.on_clicked(_on_copy)

    # Only save automatically if a path was explicitly provided
    if output_path:
        plt.savefig(output_path, dpi=150)
        print(f"Saved plot to {output_path}")

    if show:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate conversation stats")
    parser.add_argument("--no-plot", action="store_true", help="Skip saving delay/cost plot")
    parser.add_argument("--show", action="store_true", help="Show plot window via matplotlib")
    parser.add_argument(
        "--output", default="", help="Plot output path (leave empty to skip saving)"
    )
    args = parser.parse_args()

    stats, convo_count = compute_stats()
    rows = build_rows(stats)

    print_table(rows)

    if not args.no_plot:
        plot_rows(rows, args.output, show=args.show, convo_count=convo_count)


if __name__ == "__main__":
    main()
