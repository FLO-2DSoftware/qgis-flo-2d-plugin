# -*- coding: utf-8 -*-
"""Discover downstream confluences and maintain paired connection records.

No engine selection is made here. Both rows of a pair carry CONFLUENCE
(allowed) or NOFLOC (blocked). Import/export translation remains separate.
"""
from collections import defaultdict
from contextlib import contextmanager


class ConfluenceManager:
    def __init__(self, gutils, lyrs):
        self.gutils = gutils
        self.con = gutils.con
        self.lyrs = lyrs
        self.candidates = {}  # tributary grid ID -> sorted main bank grid IDs
        self.issues = []

    def assess_confluences(self):
        """Use explicit channel order, then test all eight neighboring cells.

        This retains the existing downstream-end rule. It does not discover
        upstream split-flow connections or all lateral 2009 exchange pairs.
        """
        from qgis.core import QgsFeatureRequest
        from .grid_tools import adjacent_grids

        self.issues = []
        self.candidates = {}
        segments = defaultdict(list)
        banks = defaultdict(set)
        rows = self.con.execute(
            'SELECT fid, seg_fid, nr_in_seg, rbankgrid FROM chan_elems'
        ).fetchall()
        for cell, segment, sequence, right in rows:
            segments[segment].append((cell, sequence))
            banks[cell].add(segment)
            if right is not None and int(right) > 0:
                banks[int(right)].add(segment)
        grid = self.lyrs.data['grid']['qlyr']
        size = float(self.gutils.get_cont_par('CELLSIZE'))
        for segment, elements in segments.items():
            orders = [sequence for _, sequence in elements]
            if None in orders or len(set(orders)) != len(orders):
                self.issues.append(
                    f'Segment {segment}: missing or duplicate nr_in_seg; endpoint assessment skipped.'
                )
                continue
            endpoint = max(elements, key=lambda item: item[1])[0]
            feature = next(grid.getFeatures(QgsFeatureRequest().setFilterFid(int(endpoint))), None)
            if feature is None:
                self.issues.append(f'Segment {segment}: endpoint grid {endpoint} is missing.')
                continue
            neighbors = adjacent_grids(self.gutils, feature, size)
            mains = sorted({int(cell) for cell in neighbors if cell and
                            any(other != segment for other in banks.get(int(cell), ()))})
            if mains:
                self.candidates[int(endpoint)] = mains
        return self.candidates

    def pairs(self):
        groups = defaultdict(list)
        for row in self.con.execute(
                'SELECT fid, conf_fid, type, chan_elem_fid, notes FROM chan_confluences ORDER BY fid'):
            groups[row[1]].append(row)
        pairs = []
        seen = set()
        for identifier, rows in groups.items():
            if len(rows) != 2 or {r[2] for r in rows} != {0, 1}:
                self.issues.append(f'Pair {identifier}: expected one type 0 and one type 1 row; preserved.')
                continue
            tributary = next(r for r in rows if r[2] == 0)
            main = next(r for r in rows if r[2] == 1)
            a, b = int(tributary[3]), int(main[3])
            key = tuple(sorted((a, b)))
            if key in seen:
                self.issues.append(f'Pair {identifier} ({a}–{b}): duplicate grid pair; preserved.')
            seen.add(key)
            notes = {str(r[4] or '').strip().upper() for r in rows}
            note = next(iter(notes)) if len(notes) == 1 else None
            if note not in ('CONFLUENCE', 'NOFLOC'):
                self.issues.append(f'Pair {identifier} ({a}–{b}): inconsistent or unknown notes; preserved.')
            pairs.append((identifier, a, b, note))
        return pairs

    @contextmanager
    def transaction(self):
        # SAVEPOINT supports an already-open caller transaction.
        self.con.execute('SAVEPOINT confluence_manager')
        try:
            yield
            self.con.execute('RELEASE SAVEPOINT confluence_manager')
        except Exception:
            # Do not hide the original error if an external utility committed
            # and implicitly removed our savepoint.
            try:
                self.con.execute('ROLLBACK TO SAVEPOINT confluence_manager')
                self.con.execute('RELEASE SAVEPOINT confluence_manager')
            except Exception:
                pass
            raise

    def insert_pair(self, a, b, note, cells):
        identifier = self.con.execute(
            'SELECT COALESCE(MAX(conf_fid), 0) + 1 FROM chan_confluences').fetchone()[0]
        self.con.executemany(
            'INSERT INTO chan_confluences (geom, conf_fid, type, chan_elem_fid, notes) '
            'VALUES (?, ?, ?, ?, ?)',
            [(cells[str(a)], identifier, 0, a, note),
             (cells[str(b)], identifier, 1, b, note)])

    def reconcile_confluences(self):
        """Add missing valid candidates; never delete or relabel existing pairs.

        A missing pair is allowed when no allowed pair already exists for that
        endpoint. Multiple inferred allowed pairs require an explicit choice in
        the dialog; no arbitrary first candidate is selected.
        """
        pairs = self.pairs()
        existing = {tuple(sorted((a, b))) for _, a, b, _ in pairs}
        active = {a for _, a, _, note in pairs if note == 'CONFLUENCE'}
        # Calculate geometries BEFORE opening a SQLite savepoint. Some
        # GeoPackage utility methods commit internally, which releases all
        # active SQLite savepoints and causes "no such savepoint" on rollback.
        pending = []
        for a, mains in self.candidates.items():
            for b in mains:
                key = tuple(sorted((a, b)))
                if key not in existing:
                    cells = self.gutils.grid_centroids([str(a), str(b)], buffers=True)
                    pending.append((a, b, 'NOFLOC' if a in active else 'CONFLUENCE', cells))
                    existing.add(key)
        with self.transaction():
            for a, b, note, cells in pending:
                self.insert_pair(a, b, note, cells)
        self.validate_confluences()

    def validate_nofloc_pairs(self, pairs=None):
        """Report invalid NOFLOC references without modifying imported records.

        Includes left-bank channel cells and rbankgrid right-bank cells.
        NF-004 (hydraulic exchange eligibility) is intentionally deferred until
        the 2009 exchange rules can be tested independently of geometry.
        """
        from qgis.core import QgsFeatureRequest
        from .grid_tools import adjacent_grids

        if pairs is None:
            pairs = self.pairs()

        membership = defaultdict(set)
        for cell, segment, right in self.con.execute(
                'SELECT fid, seg_fid, rbankgrid FROM chan_elems'):
            if cell is not None:
                membership[int(cell)].add(segment)
            if right is not None and int(right) > 0:
                membership[int(right)].add(segment)

        grid = self.lyrs.data['grid']['qlyr']
        size = float(self.gutils.get_cont_par('CELLSIZE'))
        neighbor_cache = {}

        for identifier, a, b, note in pairs:
            if note != 'NOFLOC':
                continue

            a_segments = membership.get(a, set())
            b_segments = membership.get(b, set())
            if not a_segments or not b_segments:
                missing = [str(cell) for cell, segments in
                           ((a, a_segments), (b, b_segments)) if not segments]
                self.issues.append(
                    f'NF-002 Pair {identifier} ({a}–{b}): grid element(s) '
                    f'{", ".join(missing)} not found in channel network; preserved.'
                )
                continue

            common = a_segments & b_segments
            if common:
                self.issues.append(
                    f'NF-001 Pair {identifier} ({a}–{b}): both grid elements '
                    f'belong to channel segment(s) {sorted(common, key=str)}; '
                    'same-segment NOFLOC requires review; preserved.'
                )

            # Use the same eight-neighbor grid test as confluence discovery.
            # An absent grid feature is reported separately from non-adjacency.
            if a not in neighbor_cache:
                feature = next(grid.getFeatures(
                    QgsFeatureRequest().setFilterFid(int(a))), None)
                if feature is None:
                    neighbor_cache[a] = None
                else:
                    neighbor_cache[a] = {
                        int(cell) for cell in adjacent_grids(
                            self.gutils, feature, size) if cell is not None
                    }
            if neighbor_cache[a] is None:
                self.issues.append(
                    f'NF-002 Pair {identifier} ({a}–{b}): grid {a} '
                    'is missing from the grid layer; preserved.'
                )
                continue
            if b not in neighbor_cache[a]:
                self.issues.append(
                    f'NF-003 Pair {identifier} ({a}–{b}): cells are not '
                    'eight-neighbor adjacent; preserved for review.'
                )

    def validate_confluences(self):
        pairs = self.pairs()
        self.validate_nofloc_pairs(pairs)
        # The dialog limits CONFLUENCE selections to discovered candidates.
        # Retain a check for imported or legacy CONFLUENCE records, but do not
        # apply the downstream-end test to lateral NOFLOC records.
        for identifier, a, b, note in pairs:
            if note == 'CONFLUENCE' and b not in self.candidates.get(a, ()):
                self.issues.append(
                    f'Pair {identifier} ({a}–{b}, CONFLUENCE): not among '
                    'the currently detected downstream-end candidates; '
                    'preserved for review.'
                )
        for a, mains in self.selected_connections().items():
            if len(mains) > 1:
                self.issues.append(
                    f'Endpoint {a}: multiple CONFLUENCE pairs {mains}; '
                    'choose one main cell.'
                )
        self.issues = list(dict.fromkeys(self.issues))
        return self.issues

    def selected_connections(self):
        selected = defaultdict(list)
        for _, a, b, note in self.pairs():
            if note == 'CONFLUENCE' and b in self.candidates.get(a, ()):
                selected[a].append(b)
        return dict(selected)

    def save(self, selections):
        """Change notes on eligible pairs only; retain IDs and unrelated rows.

        None means no connection. Dialog ambiguity must be resolved before this
        method is called. Reversed legacy pairs are left unchanged and reported
        by validation rather than silently swapping their hydraulic roles.
        """
        pairs = self.pairs()
        for a, b in selections.items():
            if a not in self.candidates or (b is not None and b not in self.candidates[a]):
                raise ValueError(f'Invalid confluence selection {a}–{b}')
        with self.transaction():
            for identifier, a, b, note in pairs:
                if (a in selections and b in self.candidates.get(a, ())
                        and note in ('CONFLUENCE', 'NOFLOC')):
                    self.con.execute(
                        'UPDATE chan_confluences SET notes = ? WHERE conf_fid = ?',
                        ('CONFLUENCE' if selections[a] == b else 'NOFLOC', identifier))
