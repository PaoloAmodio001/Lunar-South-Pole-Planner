import json

import numpy as np
import rasterio
from rasterio.transform import from_origin

from src.mission_orchestrator import run_mission_workflow


def _write_raster(path, data, dtype):
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype=dtype,
        crs="EPSG:4326",
        transform=from_origin(10, 20, 0.001, 0.001),
    ) as dst:
        dst.write(data.astype(dtype), 1)


def test_orchestrator_runs_lola_lroc_quality_step(tmp_path):
    lola_path = tmp_path / "lola.tif"
    lroc_path = tmp_path / "lroc.tif"
    conf_path = tmp_path / "confidence.tif"

    lola = np.zeros((2, 4), dtype=np.float32)
    lroc = np.array(
        [[1, 2, 3, 4], [5, 6, 7, 8]],
        dtype=np.float32,
    )
    confidence = np.array(
        [[14, 4, 1, 0], [2, 5, 6, 12]],
        dtype=np.uint8,
    )

    _write_raster(lola_path, lola, "float32")
    _write_raster(lroc_path, lroc, "float32")
    _write_raster(conf_path, confidence, "uint8")

    output_dir = tmp_path / "output"
    config_path = tmp_path / "mission_config.json"

    config = {
        "output_dir": str(output_dir),
        "mission_report": {"enabled": False},
        "lola_lroc_quality": {
            "lola_path": str(lola_path),
            "lroc_path": str(lroc_path),
            "confidence_path": str(conf_path),
            "report_name": "integration_quality.json",
        },
    }

    config_path.write_text(
        json.dumps(config, indent=2),
        encoding="utf-8",
    )

    result = run_mission_workflow(config_path)

    step = result["steps"]["lola_lroc_quality"]
    assert step["status"] == "success"

    artifact = result["artifacts"]["lola_lroc_quality"]
    assert artifact == str(output_dir / "integration_quality.json")

    report_path = output_dir / "integration_quality.json"
    assert report_path.is_file()

    quality_report = json.loads(
        report_path.read_text(encoding="utf-8")
    )

    assert quality_report["coverage"]["valid_comparison_pixels"] == 2
    assert result["status"] != "completed_with_errors"
