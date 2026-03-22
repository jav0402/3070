from __future__ import annotations

import os
from typing import Any

import featured_prototype as fp


GENERAL_CLASSIFIER_TRIGGER = float(
    os.environ.get("GENERAL_CLASSIFIER_TRIGGER", "0.50")
)


def load_general_classifier(device) -> dict[str, Any]:
    """Load a generic image classifier used as fallback after low-confidence food classification."""
    model, class_names = fp.load_model(device)
    transform = fp.build_transform()
    return {
        "model": model,
        "class_names": class_names,
        "transform": transform,
        "device": device,
    }


def predict_general_fallback(
    image,
    classifier: dict[str, Any] | None,
    top_k: int = 3,
) -> list[tuple[str, float]]:
    if classifier is None:
        return []

    input_tensor = fp.preprocess_pil_image(image, classifier["transform"])
    return fp.predict(
        classifier["model"],
        input_tensor,
        classifier["device"],
        classifier["class_names"],
        top_k=top_k,
    )


def classify_with_fallback(
    image,
    primary_pipe,
    fallback_classifier: dict[str, Any] | None,
    threshold: float = GENERAL_CLASSIFIER_TRIGGER,
    top_k: int = 3,
) -> tuple[list[tuple[str, float]], bool, str]:
    preds_raw = primary_pipe(image, top_k=top_k)
    primary_preds = [
        (item.get("label", ""), float(item.get("score", 0.0)))
        for item in preds_raw
    ]
    if not primary_preds:
        return [], False, "primary"

    top1_prob = primary_preds[0][1]
    if top1_prob >= threshold or fallback_classifier is None:
        return primary_preds, top1_prob < threshold, "primary"

    print(
        f"[INFO] primary classifier confidence {top1_prob:.3f} fell below "
        f"{threshold:.2f}; using fallback general classifier."
    )
    fallback_preds = predict_general_fallback(
        image,
        fallback_classifier,
        top_k=top_k,
    )
    if fallback_preds:
        return fallback_preds, False, "fallback_general"

    return primary_preds, True, "primary"
