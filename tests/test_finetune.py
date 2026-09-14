"""Offline tests for local fine-tune plumbing (no network, no GPU).

Research/education tools only. Asserts numerical contracts, not clinical validity.
"""

import numpy as np
import torch
from PIL import Image

from engines.finetune_trainer import confusion_and_macro_f1, resolve_device, roc_auc_score
from engines.tcia_dataset import (encode_labels, load_labels_csv,
                                  slice_to_rgb, stratified_split)


def _rand_rgb(seed=0, size=(32, 32)):
    """Return a random RGB image at the given size from a seeded RNG."""
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 255, (*size, 3),
                                        dtype=np.uint8))


def test_labels_csv_parsing(tmp_path):
    """Verify the labels CSV is parsed into a series-uid -> label map."""
    p = tmp_path / "labels.csv"
    p.write_text("series_uid,label\n1.2.3,CT_HEAD\n1.2.4,MR_HEAD\n",
                 encoding="utf-8")
    assert load_labels_csv(p) == {"1.2.3": "CT_HEAD", "1.2.4": "MR_HEAD"}


def test_slice_to_rgb_middle_slice():
    """Verify a CT slice converts to an RGB middle-slice image."""
    vol = np.zeros((8, 16, 16), dtype=np.float32)
    vol[4] = 500.0
    img = slice_to_rgb(vol, is_ct=True)
    assert isinstance(img, Image.Image) and img.size == (16, 16)
    assert img.mode == "RGB"


def test_encode_and_stratified_split():
    """Verify label encoding and stratified split balance both classes."""
    items = [{"image": _rand_rgb(i), "label": ("A" if i % 2 == 0 else "B"),
              "source": f"s{i}"} for i in range(12)]
    items, mapping = encode_labels(items)
    assert mapping == {"A": 0, "B": 1}
    train, val = stratified_split(items, seed=0)
    assert len(train) + len(val) == 12
    assert {it["label"] for it in val} == {"A", "B"}


def test_stratified_split_keeps_series_together():
    """Validation must not contain slices from a series used for training."""
    items = []
    for series in ("s1", "s2", "s3", "s4"):
        for slice_index in range(3):
            items.append({
                "image": _rand_rgb(slice_index),
                "label": "A" if series in ("s1", "s2") else "B",
                "series_uid": series,
                "source": f"{series}/slice-{slice_index}.dcm",
            })
    train, val = stratified_split(items, val_frac=0.25, seed=0)
    assert {item["series_uid"] for item in train}.isdisjoint(
        {item["series_uid"] for item in val}
    )


def test_confusion_macro_f1_known():
    """Verify confusion matrix, accuracy, and macro-F1 on known labels."""
    r = confusion_and_macro_f1([0, 0, 1, 1], [0, 1, 1, 1], 2)
    assert r["accuracy"] == 0.75
    assert 0.0 <= r["macro_f1"] <= 1.0
    assert len(r["confusion_matrix"]) == 2


def test_resolve_device_cpu():
    """Verify an explicit CPU device request resolves to CPU."""
    assert str(resolve_device("cpu")) == "cpu"


def test_roc_auc_binary_and_multiclass():
    """Verify ROC-AUC is reported for binary and multiclass probability vectors."""
    assert round(roc_auc_score([0, 0, 1, 1], np.array([0.1, 0.2, 0.8, 0.9])), 3) == 1.0
    probs = np.array([
        [0.9, 0.1],
        [0.7, 0.3],
        [0.2, 0.8],
        [0.1, 0.9],
    ])
    assert 0.0 <= roc_auc_score([0, 0, 1, 1], probs) <= 1.0
    assert roc_auc_score([0, 0], np.array([0.1, 0.2])) is None


def test_tiny_train_loop_overfits(tmp_path):
    """Minimal torch loop sanity: loss must decrease on separable data."""
    torch.manual_seed(0)
    n = 16
    X = torch.cat([torch.randn(n // 2, 4) - 2.0, torch.randn(n // 2, 4) + 2.0])
    y = torch.tensor([0] * (n // 2) + [1] * (n // 2))
    net = torch.nn.Linear(4, 2)
    opt = torch.optim.AdamW(net.parameters(), lr=0.05)
    fn = torch.nn.CrossEntropyLoss()
    l0 = float(fn(net(X), y))
    for _ in range(60):
        opt.zero_grad()
        fn(net(X), y).backward()
        opt.step()
    l1 = float(fn(net(X), y))
    assert l1 < l0 * 0.5


def test_onnx_export_tiny_model(tmp_path):
    """Verify a tiny model exports to ONNX and runs via onnxruntime."""
    torch.manual_seed(0)
    net = torch.nn.Sequential(torch.nn.Flatten(), torch.nn.Linear(3 * 8 * 8, 2)).eval()
    dummy = torch.zeros(1, 3, 8, 8)
    path = str(tmp_path / "tiny.onnx")
    torch.onnx.export(net, dummy, path, input_names=["x"], output_names=["y"],
                      opset_version=17, dynamic_axes={"x": {0: "b"}, "y": {0: "b"}})
    import onnxruntime as ort
    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    got = sess.run(["y"], {"x": dummy.numpy()})[0]
    assert got.shape == (1, 2) and np.isfinite(got).all()
