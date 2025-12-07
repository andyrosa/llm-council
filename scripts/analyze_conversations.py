"""Aggregate model stats from saved conversations and plot them.

Computes per-model average rank (weighted by judge counts), normalized delay
(elapsed_time / fastest model per question), and average cost from stage 1
responses. By default it also writes a PNG showing delay vs. rank and cost vs.
rank in cents (use ``--no-plot`` to skip).
"""

import argparse
import json
import os
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from backend.config import DATA_DIR


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


def _collect_ranks(message: Dict) -> Dict[str, Tuple[float, int]]:
    meta = message.get("metadata") or {}
    label_map: Dict[str, str] = meta.get("label_to_model") or {}
    aggregate = meta.get("aggregate_rankings")
    if isinstance(aggregate, list) and aggregate:
        ranks: Dict[str, Tuple[float, int]] = {}
        for entry in aggregate:
            model = entry.get("model")
            avg = entry.get("average_rank")
            count = entry.get("rankings_count") or 0
            if model and isinstance(avg, (int, float)):
                ranks[model] = (float(avg) * (count or 1), int(count or 1))
        return ranks

    stage2 = message.get("stage2") or []
    ranks: Dict[str, Tuple[float, int]] = defaultdict(lambda: (0.0, 0))
    for ranking in stage2:
        parsed = ranking.get("parsed_ranking") or []
        for idx, label in enumerate(parsed):
            model = label_map.get(label)
            if not model:
                continue
            sum_so_far, count_so_far = ranks[model]
            ranks[model] = (sum_so_far + idx + 1, count_so_far + 1)
    return ranks


def compute_stats() -> Dict[str, Dict[str, float]]:
    conversations = _load_conversations(DATA_DIR)
    accum: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {
            "rank_sum": 0.0,
            "rank_count": 0.0,
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
            ranks = _collect_ranks(message)

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

            for model, (rank_sum, rank_count) in ranks.items():
                if rank_count:
                    stats = accum[model]
                    stats["rank_sum"] += rank_sum
                    stats["rank_count"] += rank_count

    return accum


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
        avg_rank = data["rank_sum"] / data["rank_count"] if data["rank_count"] else None
        avg_delay = data["delay_sum"] / data["delay_count"] if data["delay_count"] else None
        avg_cost = data["cost_sum"] / data["cost_count"] if data["cost_count"] else None
        rows.append((model, avg_rank, avg_delay, avg_cost))

    rows.sort(key=lambda r: (r[1] if r[1] is not None else float("inf"), r[0]))
    return rows


def print_table(rows) -> None:
    header = f"{'Model':<35} {'AvgRank':>8} {'NormDelay':>10} {'AvgCost(cents)':>15}"
    print(header)
    print("-" * len(header))
    for model, avg_rank, avg_delay, avg_cost in rows:
        cost_cents = avg_cost * 100 if avg_cost is not None else None
        print(
            f"{model:<35} {_fmt(avg_rank):>8} {_fmt(avg_delay):>10} {_fmt(cost_cents):>15}"
        )


def plot_rows(rows, output_path: str, show: bool = False) -> None:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except ImportError:  # pragma: no cover - optional dependency
        print("matplotlib not installed; skip plotting")
        return

    rank_delay = [(r[1], r[2], r[0]) for r in rows if r[1] is not None and r[2] is not None]
    rank_cost = [
        (r[1], r[3] * 100.0, r[0]) for r in rows if r[1] is not None and r[3] is not None
    ]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    if rank_delay:
        x, y, labels = zip(*rank_delay)
        axes[0].scatter(x, y, alpha=0.7)
        for xi, yi, label in zip(x, y, labels):
            axes[0].text(xi, yi, label, fontsize=8, ha="left", va="bottom")
        axes[0].set_xlabel("Average Rank (lower is better)")
        axes[0].set_ylabel("Normalized Delay")
        axes[0].set_title("Delay vs. Rank")
        axes[0].grid(True, alpha=0.2)
    else:
        axes[0].set_title("No delay data")

    if rank_cost:
        x, y, labels = zip(*rank_cost)
        axes[1].scatter(x, y, alpha=0.7)
        for xi, yi, label in zip(x, y, labels):
            axes[1].text(xi, yi, label, fontsize=8, ha="left", va="bottom")
        axes[1].set_xlabel("Average Rank (lower is better)")
        axes[1].set_ylabel("Average Cost (cents)")
        axes[1].set_title("Cost vs. Rank (cents)")
        axes[1].grid(True, alpha=0.2)
    else:
        axes[1].set_title("No cost data")

    fig.tight_layout()
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
        "--output", default="conversation_stats.png", help="Plot output path (ignored if empty)"
    )
    args = parser.parse_args()

    stats = compute_stats()
    rows = build_rows(stats)

    print_table(rows)

    if not args.no_plot:
        plot_rows(rows, args.output, show=args.show)


if __name__ == "__main__":
    main()
