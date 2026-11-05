"""MobileNetV2 transfer-learning classifier."""

from __future__ import annotations

from tensorflow import keras


def build_model(num_classes: int, image_size: int = 224, alpha: float = 1.0, weights: str | None = "imagenet",
                dropout: float = 0.3) -> tuple[keras.Model, keras.Model]:
    """Return (model, base). Input: float32 RGB in [0, 255]. Output: softmax over num_classes."""
    if num_classes < 2:
        raise ValueError("at least two classes are required")
    inputs = keras.Input(shape=(image_size, image_size, 3), name="image")
    x = keras.layers.Rescaling(1.0 / 127.5, offset=-1.0, name="mobilenetv2_preprocess")(inputs)
    base = keras.applications.MobileNetV2(input_shape=(image_size, image_size, 3), include_top=False,
                                          weights=weights, alpha=alpha)
    base.trainable = False
    x = base(x, training=False)  # BatchNorm stays in inference mode, also during fine-tuning
    x = keras.layers.GlobalAveragePooling2D(name="gap")(x)
    x = keras.layers.Dropout(dropout, name="head_dropout")(x)
    outputs = keras.layers.Dense(num_classes, activation="softmax", name="species_probabilities")(x)
    return keras.Model(inputs, outputs, name="geoflora_mobilenetv2"), base


def unfreeze_top(base: keras.Model, fine_tune_at: int) -> int:
    """Unfreeze layers from `fine_tune_at` upward, keeping BatchNorm frozen. Returns #trainable layers."""
    base.trainable = True
    n = 0
    for i, layer in enumerate(base.layers):
        trainable = i >= fine_tune_at and not isinstance(layer, keras.layers.BatchNormalization)
        layer.trainable = trainable
        n += int(trainable)
    return n


def find_base(model: keras.Model) -> keras.Model:
    for layer in model.layers:
        if isinstance(layer, keras.Model) and layer.name.startswith("mobilenetv2"):
            return layer
    raise ValueError("MobileNetV2 base not found in model")
