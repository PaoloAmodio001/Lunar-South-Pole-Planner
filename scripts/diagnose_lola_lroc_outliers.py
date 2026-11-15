from pathlib import Path

import csv
import numpy as np
import rasterio
import matplotlib.pyplot as plt

from rasterio.windows import Window
from rasterio.warp import reproject, Resampling

LOLA = Path("data/terrain/official-lola/Site04_final_adj_5mpp_surf.tif")
LROC = Path("data/terrain/reference-lroc/NAC_DTM_ESALL_SR12.TIF")
CONF = Path("data/terrain/reference-lroc/source-check/NAC_DTM_ESALL_SR12_CONF_original.IMG")

OUTLIERS = Path("audit-reports/lola-lroc-conf4-outliers-20261114.csv")
OUTPUT = Path("audit-reports/lola-lroc-diagnostic-maps")
OUTPUT.mkdir(parents=True, exist_ok=True)

ZONES = {
    "A": (-4022.5, -6167.5),
    "B": (-1052.5, -7657.5),
    "C": (-1002.5, -7342.5),
}

HALF = 30


def load_outliers():
    points = {name: [] for name in ZONES}

    with OUTLIERS.open(newline="", encoding="utf-8") as f:
        for item in csv.DictReader(f):
            x = float(item["x_lunar_projected_m"])
            y = float(item["y_lunar_projected_m"])

            for name, (zx, zy) in ZONES.items():
                if abs(x - zx) <= 150 and abs(y - zy) <= 150:
                    points[name].append((x, y))

    return points


def main():
    for path in (LOLA, LROC, CONF, OUTLIERS):
        if not path.is_file():
            raise FileNotFoundError(path)

    outliers = load_outliers()

    with rasterio.open(LOLA) as lo, \
         rasterio.open(LROC) as lr, \
         rasterio.open(CONF) as cf:

        for name, (x, y) in ZONES.items():
            row, col = rasterio.transform.rowcol(lo.transform, x, y)

            window = Window(
                col - HALF,
                row - HALF,
                HALF * 2 + 1,
                HALF * 2 + 1,
            )

            transform = lo.window_transform(window)
            height = int(window.height)
            width = int(window.width)

            lola_ma = lo.read(1, window=window, masked=True)
            lola = lola_ma.astype(np.float64).filled(np.nan)

            lroc_source_ma = lr.read(1, masked=True)
            lroc_source = lroc_source_ma.filled(np.nan).astype(np.float32)

            lroc = np.full((height, width), np.nan, dtype=np.float32)

            reproject(
                source=lroc_source,
                destination=lroc,
                src_transform=lr.transform,
                src_crs=lr.crs,
                src_nodata=np.nan,
                dst_transform=transform,
                dst_crs=lo.crs,
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
                init_dest_nodata=True,
            )

            conf_source = cf.read(1, masked=False).astype(np.int16)
            conf = np.full((height, width), -1, dtype=np.int16)

            reproject(
                source=conf_source,
                destination=conf,
                src_transform=cf.transform,
                src_crs=cf.crs,
                src_nodata=None,
                dst_transform=transform,
                dst_crs=lo.crs,
                dst_nodata=-1,
                resampling=Resampling.nearest,
                init_dest_nodata=True,
            )

            delta = lroc.astype(np.float64) - lola

            valid = np.isfinite(lola) & np.isfinite(lroc)
            delta[~valid] = np.nan

            conf_display = np.ma.masked_where(conf < 0, conf)

            left = transform.c
            top = transform.f
            right = left + width * transform.a
            bottom = top + height * transform.e
            extent = [left, right, bottom, top]

            # Coordinate dei pixel centrali della finestra.
            xs = left + (np.arange(width) + 0.5) * transform.a
            ys = top + (np.arange(height) + 0.5) * transform.e

            center_row = HALF
            center_col = HALF

            fig, axes = plt.subplots(
                2, 3,
                figsize=(19, 12),
                constrained_layout=True,
            )

            fig.suptitle(
                f"Diagnostica LOLA–LROC | Zona {name}\n"
                f"Centro X={x:.1f} m, Y={y:.1f} m",
                fontsize=15,
            )

            panels = [
                (axes[0, 0], lola, "LOLA SURF", "Altezza (m)", "viridis"),
                (axes[0, 1], lroc, "LROC DTM ricampionato", "Altezza (m)", "viridis"),
                (axes[0, 2], delta, "Differenza LROC − LOLA", "Differenza (m)", "coolwarm"),
            ]

            for ax, data, title, colorbar_label, cmap in panels:
                image = ax.imshow(
                    data,
                    extent=extent,
                    origin="upper",
                    cmap=cmap,
                    interpolation="nearest",
                )
                ax.set_title(title)
                ax.set_xlabel("X lunare proiettata (m)")
                ax.set_ylabel("Y lunare proiettata (m)")
                fig.colorbar(image, ax=ax, label=colorbar_label)

                for ox, oy in outliers[name]:
                    ax.scatter(
                        ox, oy,
                        marker="x",
                        color="red",
                        s=45,
                        linewidths=1.5,
                    )

                ax.scatter(
                    x, y,
                    marker="+",
                    color="black",
                    s=100,
                    linewidths=2,
                )

            conf_image = axes[1, 0].imshow(
                conf_display,
                extent=extent,
                origin="upper",
                cmap="tab20",
                interpolation="nearest",
                vmin=0,
                vmax=14,
            )
            axes[1, 0].set_title("Classi CONF PDS3")
            axes[1, 0].set_xlabel("X lunare proiettata (m)")
            axes[1, 0].set_ylabel("Y lunare proiettata (m)")
            fig.colorbar(conf_image, ax=axes[1, 0], label="Codice CONF")

            for ox, oy in outliers[name]:
                axes[1, 0].scatter(
                    ox, oy, marker="x", color="red", s=45
                )

            # Profilo orizzontale e verticale attraverso il centro.
            axes[1, 1].plot(
                xs, lola[center_row, :],
                label="LOLA", linewidth=1.5,
            )
            axes[1, 1].plot(
                xs, lroc[center_row, :],
                label="LROC", linewidth=1.5,
            )
            axes[1, 1].set_title("Profilo altimetrico orizzontale")
            axes[1, 1].set_xlabel("X proiettata (m)")
            axes[1, 1].set_ylabel("Altezza (m)")
            axes[1, 1].legend()
            axes[1, 1].grid(True, alpha=0.3)

            axes[1, 2].plot(
                ys, lola[:, center_col],
                label="LOLA", linewidth=1.5,
            )
            axes[1, 2].plot(
                ys, lroc[:, center_col],
                label="LROC", linewidth=1.5,
            )
            axes[1, 2].set_title("Profilo altimetrico verticale")
            axes[1, 2].set_xlabel("Y proiettata (m)")
            axes[1, 2].set_ylabel("Altezza (m)")
            axes[1, 2].legend()
            axes[1, 2].grid(True, alpha=0.3)

            output_file = OUTPUT / f"zone_{name}_diagnostic.png"
            fig.savefig(output_file, dpi=180)
            plt.close(fig)

            count_valid = int(np.count_nonzero(valid))
            count_conf4 = int(np.count_nonzero(valid & (conf == 4)))
            count_outliers = len(outliers[name])

            print(f"\nZona {name}")
            print("  Pixel DEM validi:", count_valid)
            print("  Pixel CONF 4:", count_conf4)
            print("  Outlier >100 m:", count_outliers)
            print("  Immagine:", output_file)

    print("\nDiagnostica completata.")


if __name__ == "__main__":
    main()
