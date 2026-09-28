"""Standalone local fine-tune CLI (research/education only).

NOT a medical device. Must NOT be used for diagnosis.

Examples:
    python scripts/finetune.py --data-dir data/train --epochs 3 --output models/finetuned/v1
    python scripts/finetune.py --tcia-cache ~/.neuroproject_tcia --label-column BodyPartExamined --epochs 5 --fp16 --full --output models/finetuned/brain-v1
    python scripts/finetune.py --data-dir data/train --dry-run
    python scripts/finetune.py --data-dir data/train --epochs 1 --limit 20 --output models/finetuned/smoke
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.constants import AI_MODEL_REGISTRY  # noqa: E402
from engines.finetune_trainer import train_model  # noqa: E402
from engines.tcia_dataset import (  # noqa: E402
    build_from_folder,
    build_from_tcia_cache,
    dataset_stats,
    dataset_manifest,
    encode_labels,
    stratified_split,
    validate_group_disjoint,
)


def parse_args(argv=None):
    """Parse and return the finetuning command-line arguments."""
    p = argparse.ArgumentParser(description="Local fine-tune (research only)")
    p.add_argument("--model", default="brain",
                   choices=sorted(AI_MODEL_REGISTRY),
                   help="Registry key (default brain)")
    p.add_argument("--model-id", default="",
                   help="Override HF model id directly")
    p.add_argument("--data-dir", default="",
                   help="Folder-per-class dataset root")
    p.add_argument("--tcia-cache", default="",
                   help="TCIA cache root (default ~/.neuroproject_tcia)")
    p.add_argument("--label-column", default="BodyPartExamined")
    p.add_argument("--labels-csv", default="")
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--grad-accum", type=int, default=2)
    p.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    p.add_argument("--fp16", action="store_true")
    p.add_argument("--full", action="store_true",
                   help="Unfreeze all layers (true full fine-tune)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limit", type=int, default=0,
                   help="Cap images per class/series (smoke tests)")
    p.add_argument("--dry-run", action="store_true",
                   help="Build dataset + print stats, no training")
    p.add_argument("--output", default="models/finetuned/run1")
    return p.parse_args(argv)


def main(argv=None) -> int:
    """Run the finetuning entrypoint and launch training."""
    args = parse_args(argv)
    model_id = args.model_id or AI_MODEL_REGISTRY[args.model]

    if args.data_dir:
        items = build_from_folder(args.data_dir, limit=args.limit or 0)
        src = f"folder:{args.data_dir}"
    else:
        cache = Path(args.tcia_cache or (Path.home() / ".neuroproject_tcia"))
        items = build_from_tcia_cache(
            cache, label_column=args.label_column,
            labels_csv=args.labels_csv or None,
            limit_per_series=args.limit or 4)
        src = f"tcia:{cache}"
    if not items:
        print(f"ERROR: no labeled images from {src}. "
              f"Provide --data-dir or check --label-column/--labels-csv.")
        return 2
    items, mapping = encode_labels(items)
    train, val = stratified_split(items)
    validate_group_disjoint(train, val)
    stats = dataset_stats(items)
    manifest = dataset_manifest(items)
    print(json.dumps({"source": src, "model": model_id, **stats,
                      "train": len(train), "val": len(val)}, indent=2))
    if len(mapping) < 2:
        print("ERROR: need >=2 classes for classification.")
        return 2
    if not train or not val:
        print("ERROR: empty train/val split; add more images per class (>=3).")
        return 2
    if args.dry_run:
        print("DRY-RUN OK: dataset builds, no training performed.")
        return 0
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "dataset_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf-8")
    (out / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    summary = train_model(
        model_id, train, val, mapping, out, epochs=args.epochs, lr=args.lr,
        batch_size=args.batch_size, grad_accum=args.grad_accum,
        device=args.device, fp16=args.fp16, full=args.full, seed=args.seed,
        dataset_manifest=manifest)
    print(json.dumps({k: summary[k] for k in
                      ("best_val_acc", "macro_f1", "epochs_run", "device",
                       "full_unfrozen")}, indent=2))
    print(f"DONE: {out}/report.md + model.onnx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
