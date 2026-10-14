"""Add audited narrow-gap patches to derived polygons, never alter N03.

Closing is used only to discover patches. Original coordinates are retained;
only accepted additions are unioned into the original. Width is measured in a
local metre frame (latitude-dependent equirectangular approximation).
"""
import math

from shapely import affinity, make_valid
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union
from shapely.strtree import STRtree


def polygons(geom):
    if geom.geom_type == 'Polygon':
        yield geom
    elif hasattr(geom, 'geoms'):
        for part in geom.geoms:
            yield from polygons(part)


def metre_frame(geom):
    """A reversible local frame; do not round-trip the original geometry."""
    x1, y1, x2, y2 = geom.bounds
    lon, lat = (x1 + x2) / 2, (y1 + y2) / 2
    sy = math.pi * 6371008.8 / 180
    sx = sy * math.cos(math.radians(lat))
    def forward(g):
        return affinity.scale(affinity.translate(g, -lon, -lat), sx, sy, origin=(0, 0))
    def inverse(g):
        return affinity.translate(affinity.scale(g, 1 / sx, 1 / sy, origin=(0, 0)), lon, lat)
    return forward, inverse


def discover_patches(original, width, metric=True):
    """Return (patch, measurements, decision) for closed and open gaps.

    98% boundary support excludes most coast-corner closing artifacts. The
    erosion guard rejects patches with broad interiors; 2A/P is descriptive,
    not a maximum-width measurement. Real narrow water cannot be distinguished
    solely by shape; use a submillimetre default and audit larger thresholds.
    """
    if not math.isfinite(width) or width <= 0:
        raise ValueError('Gap width must be finite and positive')
    if not original.is_valid or original.is_empty:
        raise ValueError('Invalid source polygon')
    if metric:
        forward, inverse = metre_frame(original)
        g = forward(original)
    else:
        g = original
        inverse = lambda p: p
    radius = width / 2
    closed = g.buffer(radius, join_style=2).buffer(-radius, join_style=2)
    additions = closed.difference(g)
    tolerance = max(width * 1e-4, 1e-8)
    # Buffering the entire nationwide boundary creates huge intermediate
    # polygons. Index short boundary chunks and buffer only near each patch.
    chunks = []
    for part in polygons(g):
        for ring in [part.exterior, *part.interiors]:
            coords = list(ring.coords)
            for start in range(0, len(coords) - 1, 128):
                chunks.append(LineString(coords[start:start + 129]))
    boundary_tree = STRtree(chunks)
    for patch in polygons(additions):
        if patch.area <= tolerance ** 2:
            continue
        near = boundary_tree.query(patch.envelope.buffer(tolerance * 2))
        supported_boundary = unary_union([chunks[i].buffer(tolerance) for i in near])
        support = patch.boundary.intersection(supported_boundary).length / patch.length
        broad = not patch.buffer(-radius * 1.01).is_empty
        decision = 'review_broad' if broad else ('review_boundary' if support < .98 else 'accepted')
        yield inverse(patch), {
            'area_m2': patch.area, 'perimeter_m': patch.length,
            'mean_width_proxy_m': 2 * patch.area / patch.length,
            'boundary_support': support,
        }, decision


def accept_patches(original, candidates, blockers=(), metric=True):
    """Reject additions touching another area's interior, then check validity."""
    accepted, audit = [], []
    for patch, measurements, decision in candidates:
        # Convert back from the local frame may produce roundoff slivers.
        patch = patch.difference(original)
        if patch.is_empty:
            continue
        if not patch.is_valid or patch.geom_type not in ('Polygon', 'MultiPolygon'):
            # Roundoff can collapse sliver tips on conversion to degrees. Keep
            # valid polygonal evidence but require review, never auto-add it.
            patch = unary_union(list(polygons(make_valid(patch))))
            decision = 'review_invalid'
            if patch.is_empty:
                continue
        if decision == 'accepted' and any(patch.intersection(b).area > 0 for b in blockers):
            decision = 'review_other_area'
        audit.append((patch, measurements, decision))
        if decision == 'accepted':
            accepted.append(patch)
    repaired = unary_union([original, *accepted]) if accepted else original
    if not repaired.is_valid or repaired.is_empty:
        raise ValueError('Gap repair produced invalid geometry')
    # An additive repair must not lose any original area.
    loss = original.difference(repaired)
    if metric and not loss.is_empty:
        forward, _ = metre_frame(original)
        loss_m2 = forward(loss).area
    else:
        loss_m2 = loss.area
    if loss_m2 > 1e-4:
        raise ValueError(f'Gap repair removed source area: {loss_m2:.12g} m2')
    return repaired, audit


def repair_geometry(original, width, blockers=(), metric=True):
    return accept_patches(original, discover_patches(original, width, metric), blockers, metric)
