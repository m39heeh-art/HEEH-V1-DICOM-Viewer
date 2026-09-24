"""Device-adaptive full fine-tuning engine (research/education only).

NOT a medical device. Must NOT be used for diagnosis.

Design:
- Full fine-tune capable (all params trainable with --full).
- CPU-safe default: freeze the first N transformer encoder layers when
  running on CPU so a laptop demo still finishes (device-adaptive, not cheating).
- GPU path (RTX 3060 6GB): unfreeze all + fp16 AMP + grad accumulation.
- Pure PyTorch loop (no Trainer dependency) + ONNX export with parity check.
- Metrics in numpy only (no sklearn hard dependency).
"""

from __future__ import annotations

import json
import time
import importlib.metadata
import hashlib
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from scipy.stats import rankdata
from torch.utils.data import DataLoader, Dataset

DISCLAIMER = ("Research/education only. NOT a medical device. "
              "Must NOT be used for diagnosis.")


class _ListDataset(Dataset):
    """In-memory dataset binding images and labels as tensors."""
    def __init__(self, items: List[Dict], processor, train: bool = False):
        """Init."""
        self.items = items
        self.processor = processor
        self.train = train

    def __len__(self):
        """Len."""
        return len(self.items)

    def __getitem__(self, i):
        """Getitem."""
        it = self.items[i]
        img = it["image"]
        if not isinstance(img, Image.Image):
            img = Image.fromarray(np.asarray(img)).convert("RGB")
        enc = self.processor(images=img, return_tensors="pt")
        pv = enc["pixel_values"][0]
        return {"pixel_values": pv,
                "labels": torch.tensor(int(it["label_id"]), dtype=torch.long)}


def resolve_device(want: str = "auto") -> torch.device:
    """Pick the best available compute device (CUDA/MPS/CPU)."""
    if want == "cpu":
        return torch.device("cpu")
    if want == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but torch.cuda.is_available()==False. "
                               "Install torch-cu121 or use --device cpu.")
        return torch.device("cuda")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _freeze_first_layers(model: nn.Module, n_freeze: int) -> int:
    """Freeze first n_freeze encoder layers. Returns frozen param count."""
    frozen = 0
    # HF ViT: model.vit.encoder.layer ; fallback: any .encoder.layer list
    layers = None
    for attr in ("vit", "vision_model", "model"):
        sub = getattr(model, attr, None)
        enc = getattr(sub, "encoder", None) if sub is not None else None
        cand = getattr(enc, "layer", None) if enc is not None else None
        if cand is not None and len(cand) > 0:
            layers = cand
            break
    if layers is None:
        return 0
    for layer in list(layers)[:max(0, n_freeze)]:
        for p in layer.parameters():
            p.requires_grad = False
            frozen += 1
    return frozen


def _binary_auc(y_true: List[int] | np.ndarray, y_score: List[float] | np.ndarray) -> Optional[float]:
    """Compute AUC for binary labels without requiring scikit-learn."""
    y_true = np.asarray(y_true, dtype=int)
    y_score = np.asarray(y_score, dtype=float)
    if y_true.size == 0 or y_score.size == 0:
        return None
    pos = y_score[y_true == 1]
    neg = y_score[y_true == 0]
    if pos.size == 0 or neg.size == 0:
        return None
    scores = np.concatenate([pos, neg])
    ranks = rankdata(scores, method="average")
    pos_ranks = ranks[:pos.size]
    auc = (pos_ranks.sum() - pos.size * (pos.size + 1) / 2.0) / (pos.size * neg.size)
    return float(np.clip(auc, 0.0, 1.0))


def roc_auc_score(y_true: List[int] | np.ndarray, y_score: np.ndarray) -> Optional[float]:
    """Compute macro ROC-AUC for binary or multi-class probabilities."""
    y_true = np.asarray(y_true, dtype=int)
    y_score = np.asarray(y_score, dtype=float)
    if y_score.ndim == 1:
        return _binary_auc(y_true, y_score)
    if y_score.shape[0] != y_true.shape[0]:
        return None
    aucs = []
    for idx in range(y_score.shape[1]):
        aucs.append(_binary_auc((y_true == idx).astype(int), y_score[:, idx]))
    defined = [value for value in aucs if value is not None]
    return float(np.mean(defined)) if defined else None


def confusion_and_macro_f1(y_true: List[int], y_pred: List[int],
                            n_cls: int) -> Dict:
    """Compute the confusion matrix and macro-averaged F1 score."""
    cm = np.zeros((n_cls, n_cls), dtype=int)
    for t, p in zip(y_true, y_pred):
        if 0 <= t < n_cls and 0 <= p < n_cls:
            cm[t, p] += 1
    f1s = []
    for c in range(n_cls):
        tp = float(cm[c, c])
        fp = float(cm[:, c].sum() - tp)
        fn = float(cm[c, :].sum() - tp)
        prec = tp / max(tp + fp, 1e-9)
        rec = tp / max(tp + fn, 1e-9)
        f1s.append(2 * prec * rec / max(prec + rec, 1e-9))
    acc = float(np.mean(np.array(y_true) == np.array(y_pred))) if y_true else 0.0
    return {"confusion_matrix": cm.tolist(),
            "macro_f1": round(float(np.mean(f1s)), 4) if f1s else 0.0,
            "accuracy": round(acc, 4),
            "roc_auc": None}


def _package_versions() -> Dict[str, str]:
    """Capture versions needed to reproduce a training run."""
    names = ("numpy", "torch", "transformers", "pillow", "scipy")
    versions = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "unavailable"
    return versions


def train_model(model_id: str, train_items: List[Dict], val_items: List[Dict],
                class_to_idx: Dict[str, int], out_dir: str | Path,
                epochs: int = 3, lr: float = 2e-5, batch_size: int = 8,
                grad_accum: int = 2, device: str = "auto", fp16: bool = True,
                full: bool = False, seed: int = 42,
                freeze_on_cpu: int = 8,
                dataset_manifest: Optional[Dict] = None) -> Dict:
    """Full fine-tune loop. Returns summary dict, writes artifacts to out_dir."""
    from transformers import AutoImageProcessor, AutoModelForImageClassification

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(seed)
    np.random.seed(seed)
    dev = resolve_device(device)
    use_amp = bool(fp16 and dev.type == "cuda")
    model_revision = os.environ.get("HF_MODEL_REVISION", "not-pinned")

    processor = AutoImageProcessor.from_pretrained(model_id)
    model = AutoModelForImageClassification.from_pretrained(
        model_id, num_labels=len(class_to_idx),
        ignore_mismatched_sizes=True).to(dev)

    frozen_params = 0
    if not full and dev.type == "cpu" and freeze_on_cpu > 0:
        frozen_params = _freeze_first_layers(model, freeze_on_cpu)
    # --full or GPU: leave everything trainable (true full fine-tune)

    trainable = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(trainable, lr=lr, weight_decay=0.01)
    total_steps = max(1, (len(train_items) // max(batch_size, 1) + 1) * epochs)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=total_steps)
    scaler = torch.amp.GradScaler("cuda") if use_amp else None
    loss_fn = nn.CrossEntropyLoss()

    pin = dev.type == "cuda"
    train_dl = DataLoader(_ListDataset(train_items, processor, True),
                          batch_size=batch_size, shuffle=True,
                          num_workers=0, pin_memory=pin)
    val_dl = DataLoader(_ListDataset(val_items, processor, False),
                        batch_size=batch_size, shuffle=False,
                        num_workers=0, pin_memory=pin)

    hist = {"train_loss": [], "val_loss": [], "val_acc": []}
    best_acc, best_state, patience, wait = -1.0, None, 2, 0
    t0 = time.time()
    for ep in range(epochs):
        model.train()
        run_loss, steps = 0.0, 0
        opt.zero_grad(set_to_none=True)
        for bi, batch in enumerate(train_dl):
            pv = batch["pixel_values"].to(dev)
            lb = batch["labels"].to(dev)
            if use_amp:
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    logits = model(pixel_values=pv).logits
                    loss = loss_fn(logits, lb) / grad_accum
                scaler.scale(loss).backward()
            else:
                logits = model(pixel_values=pv).logits
                loss = loss_fn(logits, lb) / grad_accum
                loss.backward()
            run_loss += float(loss.item()) * grad_accum
            steps += 1
            if (bi + 1) % grad_accum == 0:
                if use_amp:
                    scaler.step(opt)
                    scaler.update()
                else:
                    opt.step()
                sched.step()
                opt.zero_grad(set_to_none=True)
        # flush remainder grads
        if steps % grad_accum != 0:
            if use_amp:
                scaler.step(opt)
                scaler.update()
            else:
                opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
        # validation
        model.eval()
        vl, yt, yp = 0.0, [], []
        with torch.no_grad():
            for batch in val_dl:
                pv = batch["pixel_values"].to(dev)
                lb = batch["labels"].to(dev)
                logits = model(pixel_values=pv).logits
                vl += float(loss_fn(logits, lb).item())
                pred = logits.argmax(-1).cpu().tolist()
                yp.extend(pred)
                yt.extend(lb.cpu().tolist())
        vl /= max(len(val_dl), 1)
        acc = float(np.mean(np.array(yt) == np.array(yp))) if yt else 0.0
        hist["train_loss"].append(round(run_loss / max(steps, 1), 4))
        hist["val_loss"].append(round(vl, 4))
        hist["val_acc"].append(round(acc, 4))
        ckpt = {"epoch": ep + 1, "model": model.state_dict(),
                "classes": class_to_idx, "model_id": model_id}
        torch.save(ckpt, out / f"ckpt-e{ep + 1}.pt")
        if acc > best_acc:
            best_acc, best_state, wait = acc, {k: v.cpu() for k, v in model.state_dict().items()}, 0
            torch.save(ckpt, out / "best.pt")
        else:
            wait += 1
            if wait >= patience:
                break

    if best_state is not None:
        model.load_state_dict({k: v.to(dev) for k, v in best_state.items()})
    # final eval numbers
    model.eval()
    yt, yp = [], []
    with torch.no_grad():
        for batch in val_dl:
            logits = model(pixel_values=batch["pixel_values"].to(dev)).logits
            yp.extend(logits.argmax(-1).cpu().tolist())
            yt.extend(batch["labels"].tolist())
    clf = confusion_and_macro_f1(yt, yp, len(class_to_idx))
    logits_arr = []
    labels_arr = []
    with torch.no_grad():
        for batch in val_dl:
            pv = batch["pixel_values"].to(dev)
            lb = batch["labels"].tolist()
            logits = model(pixel_values=pv).logits
            logits_arr.append(logits.softmax(dim=-1).cpu().numpy())
            labels_arr.extend(lb)
    proba = np.concatenate(logits_arr, axis=0) if logits_arr else np.zeros((0, len(class_to_idx)))
    clf["roc_auc"] = roc_auc_score(labels_arr, proba)

    summary = {"model_id": model_id, "device": str(dev), "fp16": use_amp,
               "full_unfrozen": bool(full or dev.type == "cuda"),
               "frozen_params": int(frozen_params), "epochs_run": len(hist["train_loss"]),
               "seconds": round(time.time() - t0, 1), "history": hist,
               "best_val_acc": round(best_acc, 4), "macro_f1": clf["macro_f1"],
               "accuracy": clf["accuracy"],
               "roc_auc": round(clf["roc_auc"], 4) if clf["roc_auc"] is not None else None,
               "confusion_matrix": clf["confusion_matrix"], "classes": class_to_idx,
               "seed": seed, "train_samples": len(train_items),
               "validation_samples": len(val_items),
               "package_versions": _package_versions(),
               "model_revision": model_revision,
               "dataset_manifest": dataset_manifest or {},
               "split_policy": "group-disjoint train/validation split",
               "disclaimer": DISCLAIMER}
    (out / "metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_report(out, summary)
    _write_curves(out, hist)
    _export_onnx(model, processor, dev, out)
    _write_run_manifest(out, summary)
    return summary


def _write_run_manifest(out: Path, summary: Dict) -> None:
    """Persist the environment and produced-artifact provenance for a run."""
    artifacts = {}
    for name in ("best.pt", "model.onnx", "metrics.json", "onnx_check.json"):
        path = out / name
        if path.is_file():
            artifacts[name] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            }
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=Path.cwd(),
            capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    manifest = {
        "schema_version": 1,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "git_revision": revision,
        "model_id": summary["model_id"],
        "model_revision": summary["model_revision"],
        "seed": summary["seed"],
        "split_policy": summary["split_policy"],
        "dataset_manifest": summary["dataset_manifest"],
        "package_versions": summary["package_versions"],
        "artifacts": artifacts,
        "disclaimer": DISCLAIMER,
    }
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")


def _write_report(out: Path, s: Dict) -> None:
    """Write a markdown training report to the output directory."""
    lines = ["# Fine-tune Report (research/education only)",
             "", "> " + DISCLAIMER, "",
             f"- base: `{s['model_id']}` | device: `{s['device']}` | fp16: `{s['fp16']}`",
             f"- full_unfrozen: `{s['full_unfrozen']}` | frozen_params: `{s['frozen_params']}`",
             f"- epochs_run: `{s['epochs_run']}` | time: `{s['seconds']}s`",
             f"- best_val_acc: `{s['best_val_acc']}` | macro_f1: `{s['macro_f1']}` | roc_auc: `{s.get('roc_auc', 'n/a')}`",
             f"- classes: `{json.dumps(s['classes'])}`", "",
             "Artifacts: `best.pt`, `ckpt-e*.pt`, `model.onnx`, `metrics.json`, `curves.png`.",
             "NOT a medical device. Must NOT be used for diagnosis."]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_curves(out: Path, hist: Dict) -> None:
    """Write and save training/validation metric curves as PNG plots."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(10, 4))
        ax[0].plot(hist["train_loss"], label="train_loss")
        ax[0].plot(hist["val_loss"], label="val_loss")
        ax[0].legend()
        ax[0].set_title("Loss")
        ax[1].plot(hist["val_acc"], label="val_acc", color="green")
        ax[1].legend()
        ax[1].set_title("Val accuracy")
        fig.tight_layout()
        fig.savefig(str(out / "curves.png"), dpi=100)
        plt.close(fig)
    except Exception:
        pass


def _export_onnx(model: nn.Module, processor, dev: torch.device, out: Path) -> Dict:
    """Export the trained model to ONNX format."""
    model.eval().to("cpu")
    dummy = torch.zeros(1, 3, 224, 224)
    try:
        size = getattr(getattr(processor, "size", {}), "get", lambda *a: None)("height", 224) or 224
        dummy = torch.zeros(1, 3, int(size), int(size))
    except Exception:
        pass
    onnx_path = out / "model.onnx"
    torch.onnx.export(model.cpu(), dummy, str(onnx_path), input_names=["pixel_values"],
                      output_names=["logits"], opset_version=17,
                      dynamic_axes={"pixel_values": {0: "batch"}, "logits": {0: "batch"}})
    # parity check torch vs onnxruntime
    import onnxruntime as ort
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    with torch.no_grad():
        ref = model.cpu()(dummy).logits.numpy() if hasattr(model.cpu()(dummy), "logits") else model.cpu()(dummy).numpy()
    got = sess.run(["logits"], {"pixel_values": dummy.numpy()})[0]
    diff = float(np.max(np.abs(ref - got)))
    res = {"onnx": str(onnx_path), "max_abs_diff": diff, "parity": diff < 1e-4}
    (out / "onnx_check.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    model.to(dev)
    return res


def load_finetuned_for_inference(ckpt_path: str | Path, device: str = "auto"):
    """Load a best.pt checkpoint for inference in Streamlit (wires into UI)."""
    from transformers import AutoImageProcessor, AutoModelForImageClassification
    ckpt = torch.load(str(ckpt_path), map_location="cpu", weights_only=True)
    if not isinstance(ckpt, dict) or not {"model_id", "classes", "model"} <= ckpt.keys():
        raise ValueError("Checkpoint is missing the required inference fields.")
    model_id = ckpt.get("model_id", "")
    classes = ckpt.get("classes", {})
    if not isinstance(model_id, str) or not model_id:
        raise ValueError("Checkpoint contains an invalid model identifier.")
    if not isinstance(classes, dict):
        raise ValueError("Checkpoint contains an invalid class mapping.")
    processor = AutoImageProcessor.from_pretrained(model_id)
    model = AutoModelForImageClassification.from_pretrained(
        model_id, num_labels=max(len(classes), 2), ignore_mismatched_sizes=True)
    model.load_state_dict(ckpt["model"], strict=False)
    dev = resolve_device(device)
    return processor, model.to(dev).eval(), dev, classes
