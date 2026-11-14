import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src.lola_lroc_quality import compare_lola_lroc_quality


def write_raster(path, data, dtype, nodata=None):
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=data.shape[1],
        height=data.shape[0],
        count=1,
        dtype=dtype,
        crs="EPSG:3857",
        transform=from_origin(0, data.shape[0], 1, 1),
        nodata=nodata,
    ) as ds:
        ds.write(data.astype(dtype), 1)


def make_inputs(tmp_path, lola, lroc, conf, lola_nodata=None, lroc_nodata=None, conf_nodata=None):
    lola_path = tmp_path / "lola.tif"
    lroc_path = tmp_path / "lroc.tif"
    conf_path = tmp_path / "conf.tif"

    write_raster(lola_path, lola, "float32", lola_nodata)
    write_raster(lroc_path, lroc, "float32", lroc_nodata)
    write_raster(conf_path, conf, "uint8", conf_nodata)

    return lola_path, lroc_path, conf_path


def test_separates_primary_interpolated_shadow_nodata_and_unknown(tmp_path):
    lola = np.zeros((2, 4), dtype=np.float32)
    lroc = np.array([[1, 2, 3, 4], [5, 6, 7, 8]], dtype=np.float32)
    conf = np.array([[14, 4, 1, 0], [2, 5, 6, 12]], dtype=np.uint8)

    paths = make_inputs(
        tmp_path, lola, lroc, conf, conf_nodata=0
    )
    report_path = tmp_path / "report.json"

    result = compare_lola_lroc_quality(*paths, report_path)
    report = json.loads(report_path.read_text())

    assert result["valid_overlap_pixels"] == 2
    assert report["coverage"]["dem_overlap_pixels"] == 8
    assert report["coverage"]["valid_comparison_pixels"] == 2
    assert report["coverage"]["confidence_covered_pixels_on_dem_overlap"] == 8
    assert report["coverage"]["outside_confidence_coverage_pixels_on_dem_overlap"] == 0

    assert report["comparison_groups"]["primary_conf_14"]["pixel_count"] == 1
    assert report["comparison_groups"]["interpolated_conf_4"]["pixel_count"] == 1
    assert report["comparison_groups"]["unresolved_classes"]["pixel_count"] == 4
    assert report["by_confidence_class"]["0"]["pixel_count"] == 1
    assert report["by_confidence_class"]["2"]["included_in_elevation_statistics"] is False

    assert report["excluded_pixels"]["confidence_1_shadow"] == 1
    assert report["excluded_pixels"]["confidence_0_nodata"] == 1

    assert report["code_14_reference_comparison"]["mae_m"] == 1.0
    assert report["by_confidence_class"]["4"]["mae_m"] == 2.0
    assert report["confidence_class_counts_on_overlap"] == {
        "0": 1, "1": 1, "2": 1, "4": 1, "5": 1, "6": 1, "12": 1, "14": 1
    }


def test_respects_lola_and_lroc_nodata(tmp_path):
    lola = np.array([[0, -9999], [0, 0]], dtype=np.float32)
    lroc = np.array([[1, 2], [-9999, 4]], dtype=np.float32)
    conf = np.full((2, 2), 14, dtype=np.uint8)

    paths = make_inputs(
        tmp_path, lola, lroc, conf,
        lola_nodata=-9999,
        lroc_nodata=-9999,
    )
    report_path = tmp_path / "report.json"

    compare_lola_lroc_quality(*paths, report_path)
    report = json.loads(report_path.read_text())

    assert report["coverage"]["dem_overlap_pixels"] == 2
    assert report["comparison_groups"]["primary_conf_14"]["pixel_count"] == 2


def test_rejects_missing_source(tmp_path):
    paths = [
        tmp_path / "missing_lola.tif",
        tmp_path / "missing_lroc.tif",
        tmp_path / "missing_conf.tif",
        tmp_path / "report.json",
    ]
    with pytest.raises(FileNotFoundError):
        compare_lola_lroc_quality(*paths)


def test_report_cannot_overwrite_source(tmp_path):
    paths = make_inputs(
        tmp_path,
        np.zeros((1, 1), dtype=np.float32),
        np.ones((1, 1), dtype=np.float32),
        np.array([[14]], dtype=np.uint8),
    )

    with pytest.raises(ValueError, match="sovrascrivere"):
        compare_lola_lroc_quality(*paths, paths[0])


def test_empty_comparison_group_returns_null_statistics(tmp_path):
    paths = make_inputs(
        tmp_path,
        np.zeros((1, 2), dtype=np.float32),
        np.ones((1, 2), dtype=np.float32),
        np.array([[0, 1]], dtype=np.uint8),
    )
    report_path = tmp_path / "report.json"

    compare_lola_lroc_quality(*paths, report_path)
    report = json.loads(report_path.read_text())

    assert report["coverage"]["valid_comparison_pixels"] == 0
    assert report["code_14_reference_comparison"]["mae_m"] is None
    assert report["comparison_groups"]["interpolated_conf_4"]["pixel_count"] == 0
