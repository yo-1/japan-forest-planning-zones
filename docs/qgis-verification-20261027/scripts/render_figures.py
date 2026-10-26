"""Verification B step 5: headless rendering figures (QGIS 3.44).

Rendering-image output only, NOT a GUI visual check.
Overview figures use simplified copies (see prep_figure_data.py) because
rendering the original nationwide geometries ran out of memory on this
VM (7.7 GB). The zoom figure uses original geometries clipped to the
district 025 extent plus margin.
Output: figures/*.png
"""
from pathlib import Path

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QColor, QImage, QPainter
from qgis.core import (QgsApplication, QgsFillSymbol,
                       QgsMapRendererCustomPainterJob, QgsMapSettings,
                       QgsRectangle, QgsSingleSymbolRenderer, QgsVectorLayer)

BASE = Path.home() / "workspace/forest-planning-zones"
FW = BASE / "verification-b/figures/work"
OUT = BASE / "verification-b/figures"


def load(gpkg, layer, color, outline, width):
    lyr = QgsVectorLayer(f"{gpkg}|layername={layer}", layer, "ogr")
    assert lyr.isValid(), layer
    sym = QgsFillSymbol.createSimple({
        "color": color, "outline_color": outline, "outline_width": str(width)})
    lyr.setRenderer(QgsSingleSymbolRenderer(sym))
    return lyr


def render(layers, extent, filename, w=2000, h=1450):
    ms = QgsMapSettings()
    ms.setLayers(layers)
    ms.setExtent(extent)
    ms.setOutputSize(QSize(w, h))
    ms.setDestinationCrs(layers[0].crs())
    ms.setBackgroundColor(QColor(255, 255, 255))
    img = QImage(QSize(w, h), QImage.Format_ARGB32_Premultiplied)
    img.setDotsPerMeterX(3780)
    img.setDotsPerMeterY(3780)
    painter = QPainter(img)
    job = QgsMapRendererCustomPainterJob(ms, painter)
    job.start()
    job.waitForFinished()
    painter.end()
    path = OUT / filename
    img.save(str(path))
    print("wrote", path, path.stat().st_size, "bytes", flush=True)


def main():
    app = QgsApplication([], False)
    app.initQgis()

    districts = load(FW / "fig_districts.gpkg", "districts",
                     "168,213,162,255", "#3c643c", 0.3)
    basins = load(FW / "fig_basins.gpkg", "basins",
                  "0,0,0,0", "#2050c8", 0.7)
    unassigned = load(FW / "fig_unassigned.gpkg", "unassigned",
                      "230,60,40,255", "#7a1408", 0.5)
    full = districts.extent()
    full.grow(0.5)
    render([basins, districts], full, "fig_overview_districts.png")
    render([unassigned, districts], full, "fig_overview_unassigned.png")

    z_districts = load(FW / "zoom_districts.gpkg", "districts",
                       "168,213,162,90", "#3c643c", 0.5)
    z_basins = load(FW / "zoom_basins.gpkg", "basins",
                    "0,0,0,0", "#2050c8", 0.9)
    z_muni = load(FW / "zoom_muni.gpkg", "muni",
                  "0,0,0,0", "#888888", 0.25)
    zoom = QgsRectangle(139.5417, 39.6456, 141.1454, 40.6611)
    render([z_basins, z_muni, z_districts], zoom, "fig_zoom_district025.png")
    print("done")


if __name__ == "__main__":
    main()
