"""One new lane projection case: real isolated SQLite, no HTTP/process caller."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from pool_leases import LeaseStore


class LaneSnapshotProjectionTest(unittest.TestCase):
    def test_active_unknown_and_released_lanes_share_one_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LeaseStore(Path(folder) / 'isolated.sqlite3', capacity=5,
                               reserve_runtime=1, max_records=8)
            for token, lane, ttl in [('expires', 'source', 2),
                                     ('source-live', 'source', 100),
                                     ('runtime-live', 'runtime', 100),
                                     ('released', 'source', 100)]:
                self.assertIs(store.acquire(token, 'fixture', lane=lane,
                                            now=10, ttl=ttl).newly_acquired, True)
            self.assertTrue(store.release('released', 'fixture',
                                          verified_no_live_post=True))
            first = store.snapshot(now=11)
            self.assertEqual((first['active'], first['unknown'], first['released'],
                              first['occupied_source'], first['occupied_runtime'],
                              first['occupied']), (3, 0, 1, 2, 1, 3))
            expired = store.snapshot(now=15)
            self.assertEqual((expired['active'], expired['unknown'], expired['released'],
                              expired['occupied_source'], expired['occupied_runtime'],
                              expired['occupied']), (2, 1, 1, 2, 1, 3))
            self.assertEqual(expired['occupied_source'] + expired['occupied_runtime'],
                             expired['occupied'])
            self.assertEqual((expired['capacity'], expired['reserve_runtime'],
                              expired['max_records'], expired['records']), (5, 1, 8, 4))
            self.assertIn('NOT_ACTUAL_HTTP_OR_SERVER_SLOT', expired['scope'])
            self.assertTrue(store.release('expires', 'fixture',
                                          verified_no_live_post=True))
            final = store.snapshot(now=16)
            self.assertEqual((final['occupied_source'], final['occupied_runtime'],
                              final['occupied'], final['unknown'], final['released']),
                             (1, 1, 2, 0, 2))


if __name__ == '__main__':
    unittest.main(verbosity=2)
