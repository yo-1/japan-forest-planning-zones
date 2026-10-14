"""Add audited narrow-gap patches to derived polygons, never alter N03.

Closing is used only to discover patches. Original coordinates are retained;
only accepted additions are unioned into the original. Width is measured in a
local metre frame (latitude-dependent equirectangular approximation).
"""
import math

from shapely import affinity, make_valid
from shapely.geometry import Polygon, MultiPolygon, LineString
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
    if not accepted:
        return original, audit
    # Merge only parts connected by a patch. A global union can collapse tiny
    # offshore parts at double precision even though no patch touches them.
    source_parts = list(polygons(original))
    tree = STRtree(source_parts)
    parent = list(range(len(source_parts)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    connected = []
    for patch in accepted:
        touched = list(tree.query(patch, predicate='intersects'))
        if not touched:
            connected.append(None)
            continue
        root = find(touched[0])
        for i in touched[1:]:
            parent[find(i)] = root
        connected.append(touched[0])
    components = {}
    for patch, i in zip(accepted, connected):
        if i is not None:
            components.setdefault(find(i), []).append(patch)
    members = {root: [] for root in components}
    unchanged = []
    for i, part in enumerate(source_parts):
        root = find(i)
        if root in members:
            members[root].append(part)
        else:
            unchanged.append(part)
    rejected = {}
    changed = []
    for root, patches in components.items():
        before = unary_union(members[root])
        after = unary_union([*members[root], *patches])
        loss = before.difference(after)
        if metric and not loss.is_empty:
            forward, _ = metre_frame(before)
            loss_area = forward(loss).area
        else:
            loss_area = loss.area
        if not after.is_valid or loss_area > 1e-4:
            rejected[root] = 'review_result_invalid' if not after.is_valid else 'review_result_loss'
            changed.extend(members[root])
        else:
            changed.extend(polygons(after))
    result_parts = unchanged + changed
    repaired = result_parts[0] if len(result_parts) == 1 else MultiPolygon(result_parts)
    accepted_index = 0
    revised_audit = []
    for patch, measurements, decision in audit:
        if decision == 'accepted':
            component = connected[accepted_index]
            accepted_index += 1
            if component is None:
                decision = 'review_detached'
            else:
                decision = rejected.get(find(component), decision)
        revised_audit.append((patch, measurements, decision))
    audit = revised_audit
    if not repaired.is_valid or repaired.is_empty:
        return original, [(p, m, 'review_result_invalid' if d == 'accepted' else d) for p, m, d in audit]
    # An additive repair must not lose any original area.
    loss = original.difference(repaired)
    if metric and not loss.is_empty:
        forward, _ = metre_frame(original)
        loss_m2 = forward(loss).area
    else:
        loss_m2 = loss.area
    if loss_m2 > 1e-4:
        return original, [(p, m, 'review_result_loss' if d == 'accepted' else d) for p, m, d in audit]
    return repaired, audit


def repair_geometry(original, width, blockers=(), metric=True):
    return accept_patches(original, discover_patches(original, width, metric), blockers, metric)
