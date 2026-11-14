import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src.lroc_quality_mask import build_lroc_quality_mask


def write_dtm(path, data, transform=None):
    if transform is None:
        transform = from_origin(100, 200, 2, 2)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype="float32",
        crs="EPSG:3857",
        transform=transform,
        nodata=-9999,
    ) as ds:
        ds.write(data.astype("float32"), 1)


def write_confidence(path, data, transform=None):
    if transform is None:
        transform = from_origin(100, 200, 2, 2)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype="uint8",
        crs="EPSG:3857",
        transform=transform,
    ) as ds:
        ds.write(data.astype("uint8"), 1)


def test_builds_expected_native_quality_classes(tmp_path):
    dtm_path = tmp_path / "dtm.tif"
    conf_path = tmp_path / "conf.tif"
    output_path = tmp_path / "quality.tif"
    report_path = tmp_path / "quality.json"

    dtm = np.array([
        [10, 10, 10],
        [10, -9999, 10],
    ], dtype=np.float32)

    conf = np.array([
        [14, 4, 2],
        [1, 14, 0],
    ], dtype=np.uint8)

    write_dtm(dtm_path, dtm)
    write_confidence(conf_path, conf)

    report = build_lroc_quality_mask(
        dtm_path, conf_path, output_path, report_path
    )

    with rasterio.open(output_path) as ds:
        result = ds.read(1)
        assert ds.nodata == 255
        assert ds.dtypes[0] == "uint8"
        assert ds.transform == from_origin(100, 200, 2, 2)

    expected = np.array([
        [1, 2, 3],
        [0, 0, 0],
    ], dtype=np.uint8)

    np.testing.assert_array_equal(result, expected)
    assert report["pixel_counts"] == {
        "INVALID": 3,
        "PRIMARY": 1,
        "INTERPOLATED": 1,
        "UNRESOLVED": 1,
    }
    assert report["unresolved_confidence_codes_on_valid_dtm"] == [2]
    assert json.loads(report_path.read_text())["status"] == "success"


def test_rejects_different_dimensions(tmp_path):
    dtm_path = tmp_path / "dtm.tif"
    conf_path = tmp_path / "conf.tif"

    write_dtm(dtm_path, np.ones((2, 2), dtype=np.float32))
    write_confidence(conf_path, np.ones((3, 2), dtype=np.uint8))

    with pytest.raises(ValueError, match="Dimensioni"):
        build_lroc_quality_mask(
            dtm_path,
            conf_path,
            tmp_path / "out.tif",
            tmp_path / "report.json",
        )


def test_rejects_different_transform(tmp_path):
    dtm_path = tmp_path / "dtm.tif"
    conf_path = tmp_path / "conf.tif"

    write_dtm(dtm_path, np.ones((2, 2), dtype=np.float32))
    write_confidence(
        conf_path,
        np.ones((2, 2), dtype=np.uint8),
        transform=from_origin(101, 200, 2, 2),
    )

    with pytest.raises(ValueError, match="Trasformazioni affine"):
        build_lroc_quality_mask(
            dtm_path,
            conf_path,
            tmp_path / "out.tif",
            tmp_path / "report.json",
        )


def test_missing_source_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_lroc_quality_mask(
            tmp_path / "missing.tif",
            tmp_path / "missing_conf.tif",
            tmp_path / "out.tif",
            tmp_path / "report.json",
        )


def test_unknown_confidence_codes_are_unresolved(tmp_path):
    dtm_path = tmp_path / "dtm.tif"
    conf_path = tmp_path / "conf.tif"

    write_dtm(dtm_path, np.ones((1, 3), dtype=np.float32))
    write_confidence(
        conf_path,
        np.array([[5, 6, 12]], dtype=np.uint8),
    )

    report = build_lroc_quality_mask(
        dtm_path,
        conf_path,
        tmp_path / "out.tif",
        tmp_path / "report.json",
    )

    with rasterio.open(tmp_path / "out.tif") as ds:
        np.testing.assert_array_equal(
            ds.read(1),
            np.array([[3, 3, 3]], dtype=np.uint8),
        )

    assert report["unresolved_confidence_codes_on_valid_dtm"] == [5, 6, 12]
    assert report["pixel_counts"]["UNRESOLVED"] == 3
