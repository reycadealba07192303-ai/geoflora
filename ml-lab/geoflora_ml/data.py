"""tf.data input pipelines.

Preprocessing contract (shared by training, evaluation, prediction and the exported model):
  1. decode as RGB with EXIF orientation applied (split folders are already EXIF-corrected JPEGs)
  2. resize to image_size x image_size with bilinear interpolation (tf.image.resize, no aspect preservation)
  3. float32 pixel values in [0, 255]
MobileNetV2 scaling to [-1, 1] happens *inside* the model (Rescaling layer), so integrators only
need steps 1-3.
"""

from __future__ import annotations

import numpy as np
import tensorflow as tf
from tensorflow import keras

AUTOTUNE = tf.data.AUTOTUNE


def decode_and_resize(path: tf.Tensor, image_size: int) -> tf.Tensor:
    data = tf.io.read_file(path)
    img = tf.io.decode_jpeg(data, channels=3)
    img = tf.image.resize(img, (image_size, image_size), method="bilinear")
    return tf.cast(img, tf.float32)


def build_augmenter(aug: dict, seed: int) -> keras.Sequential:
    layers = []
    if aug.get("horizontal_flip"):
        layers.append(keras.layers.RandomFlip("horizontal", seed=seed))
    if aug.get("rotation"):
        layers.append(keras.layers.RandomRotation(aug["rotation"], fill_mode="reflect", seed=seed))
    if aug.get("zoom"):
        layers.append(keras.layers.RandomZoom(aug["zoom"], fill_mode="reflect", seed=seed))
    if aug.get("translation"):
        layers.append(keras.layers.RandomTranslation(aug["translation"], aug["translation"], fill_mode="reflect", seed=seed))
    if aug.get("contrast"):
        layers.append(keras.layers.RandomContrast(aug["contrast"], seed=seed))
    if aug.get("brightness"):
        layers.append(keras.layers.RandomBrightness(aug["brightness"], value_range=(0, 255), seed=seed))
    return keras.Sequential(layers, name="augmentation")


def make_dataset(paths: list[str], labels: list[int] | None, num_classes: int, image_size: int, batch_size: int,
                 training: bool = False, augment_cfg: dict | None = None, seed: int = 42,
                 shuffle_buffer: int = 1000) -> tf.data.Dataset:
    paths_t = tf.constant(paths, dtype=tf.string)
    if labels is None:
        ds = tf.data.Dataset.from_tensor_slices(paths_t)
        ds = ds.map(lambda p: decode_and_resize(p, image_size), num_parallel_calls=AUTOTUNE)
        return ds.batch(batch_size).prefetch(AUTOTUNE)

    onehot = tf.one_hot(np.asarray(labels, dtype=np.int32), num_classes)
    ds = tf.data.Dataset.from_tensor_slices((paths_t, onehot))
    if training:
        ds = ds.shuffle(min(len(paths), shuffle_buffer), seed=seed, reshuffle_each_iteration=True)
    ds = ds.map(lambda p, y: (decode_and_resize(p, image_size), y), num_parallel_calls=AUTOTUNE)
    ds = ds.batch(batch_size)
    if training and augment_cfg:
        augmenter = build_augmenter(augment_cfg, seed)
        ds = ds.map(lambda x, y: (tf.clip_by_value(augmenter(x, training=True), 0.0, 255.0), y),
                    num_parallel_calls=AUTOTUNE)
    return ds.prefetch(AUTOTUNE)
