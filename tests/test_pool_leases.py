import math
import multiprocessing
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from pool_leases import LeaseStore, LeaseStoreFull


def acquire_child(database, barrier, queue, token):
    try:
        store = LeaseStore(database, capacity=4, reserve_runtime=1)
        barrier.wait(15)
        queue.put(('ok', store.acquire(token, 'source-owner', now=0, ttl=100).newly_acquired))
    except BaseException as error:
        queue.put(('error', type(error).__name__))


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'leases.sqlite'

    def tearDown(self):
        self.temp.cleanup()

    def test_future_runtime_place_is_reserved_before_runtime_exists(self):
        store = LeaseStore(self.path, capacity=3)
        self.assertTrue(store.acquire('a', 'one', now=0, ttl=100).newly_acquired)
        self.assertTrue(store.acquire('b', 'two', now=0, ttl=100).newly_acquired)
        self.assertEqual(store.acquire('c', 'three', now=0, ttl=100).outcome, 'CAPACITY')
        self.assertTrue(store.acquire('runtime', 'runtime-owner', lane='runtime', now=0, ttl=100).newly_acquired)
        self.assertEqual(store.snapshot(now=1)['occupied'], 3)
        store.release('runtime', 'runtime-owner', verified_no_live_post=True)
        self.assertEqual(store.acquire('d', 'four', now=1, ttl=100).outcome, 'CAPACITY')

    def test_expiry_is_sticky_across_restart_and_explicit_release_is_terminal(self):
        store = LeaseStore(self.path, capacity=1, reserve_runtime=0)
        store.acquire('a', 'owner', now=0, ttl=5)
        reopened = LeaseStore(self.path, capacity=1, reserve_runtime=0)
        self.assertEqual(reopened.snapshot(now=5)['unknown'], 1)
        self.assertEqual(reopened.acquire('b', 'owner', now=6, ttl=5).outcome, 'CAPACITY')
        self.assertEqual(reopened.acquire('a', 'owner', now=6, ttl=5).outcome, 'RECOVERY_REQUIRED')
        self.assertFalse(reopened.release('a', 'owner', verified_no_live_post=1))
        self.assertFalse(reopened.release('a', 'other', verified_no_live_post=True))
        self.assertTrue(reopened.release('a', 'owner', verified_no_live_post=True))
        self.assertEqual(reopened.acquire('a', 'owner', now=6, ttl=5).outcome, 'TERMINAL')
        self.assertTrue(reopened.acquire('b', 'owner', now=6, ttl=5).newly_acquired)

    def test_idempotence_does_not_renew_or_authorize_second_dispatch(self):
        store = LeaseStore(self.path)
        first = store.acquire('a', 'owner', now=0, ttl=10)
        again = store.acquire('a', 'owner', now=5, ttl=1000)
        self.assertEqual((first.outcome, again.outcome), ('ACQUIRED', 'EXISTING'))
        self.assertFalse(again.newly_acquired)
        with self.assertRaises(TypeError):
            bool(again)
        self.assertEqual(store.get('a')['expires'], 10)
        self.assertEqual(store.acquire('a', 'wrong', now=5, ttl=1).outcome, 'CONFLICT')
        self.assertEqual(store.acquire('a', 'owner', lane='runtime', now=5, ttl=1).outcome, 'CONFLICT')
        self.assertEqual(store.snapshot(now=10)['occupied'], 1)

    def test_configuration_is_persistent_and_not_a_per_process_capacity_override(self):
        store = LeaseStore(self.path, capacity=2, max_records=10)
        store.acquire('a', 'owner', now=0, ttl=10)
        for limits in ({'capacity': 60, 'max_records': 10}, {'capacity': 2, 'reserve_runtime': 0, 'max_records': 10}, {'capacity': 2, 'max_records': 11}):
            with self.assertRaises(ValueError):
                LeaseStore(self.path, **limits)
        self.assertEqual(store.snapshot(now=1)['occupied'], 1)

    def test_history_bound_keeps_released_tombstones(self):
        store = LeaseStore(self.path, capacity=2, reserve_runtime=0, max_records=2)
        for token in ('a', 'b'):
            store.acquire(token, 'owner', now=0, ttl=10)
            store.release(token, 'owner', verified_no_live_post=True)
        with self.assertRaises(LeaseStoreFull):
            store.acquire('c', 'owner', now=1, ttl=10)
        self.assertEqual(store.get('a')['state'], 'RELEASED')
        self.assertEqual(store.snapshot(now=1)['records'], 2)

    def test_nonfinite_bool_unencodable_and_oversized_inputs_do_not_write_records(self):
        store = LeaseStore(self.path)
        for value in (True, False, math.nan, math.inf, -math.inf, -1, 2 ** 54, 10 ** 1000):
            for name in ('now', 'ttl'):
                arguments = {'now': 0, 'ttl': 10, name: value}
                with self.assertRaises(ValueError):
                    store.acquire('a', 'owner', **arguments)
        for token in ('', '\0', '\ud800', '界' * 171):
            with self.assertRaises(ValueError):
                store.acquire(token, 'owner', now=0, ttl=10)
        with self.assertRaises(ValueError):
            LeaseStore(self.path, capacity=True)
        self.assertEqual(store.snapshot(now=0)['records'], 0)

    def test_uncertain_launch_stays_occupied_until_owner_attestation(self):
        store = LeaseStore(self.path, capacity=1, reserve_runtime=0)
        store.acquire('a', 'owner', now=0, ttl=100)
        self.assertFalse(store.mark_unknown('a', 'wrong'))
        self.assertTrue(store.mark_unknown('a', 'owner'))
        self.assertTrue(store.mark_unknown('a', 'owner'))
        self.assertEqual(store.snapshot(now=1)['unknown'], 1)
        self.assertEqual(store.acquire('b', 'owner', now=1, ttl=100).outcome, 'CAPACITY')
        self.assertFalse(store.release('a', 'owner', verified_no_live_post=False))

    def test_twelve_processes_cannot_overadmit_three_source_places(self):
        LeaseStore(self.path, capacity=4, reserve_runtime=1)
        context = multiprocessing.get_context('spawn')
        barrier, queue = context.Barrier(12), context.Queue()
        children = [context.Process(target=acquire_child, args=(str(self.path), barrier, queue, str(i))) for i in range(12)]
        try:
            for child in children:
                child.start()
            results = [queue.get(timeout=30) for _ in children]
            for child in children:
                child.join(15)
                self.assertEqual(child.exitcode, 0)
            self.assertTrue(all(kind == 'ok' for kind, _ in results), results)
            self.assertEqual(sum(value for _, value in results), 3)
            store = LeaseStore(self.path, capacity=4, reserve_runtime=1)
            self.assertEqual(store.snapshot(now=1)['occupied'], 3)
            self.assertTrue(store.acquire('game', 'runtime-owner', lane='runtime', now=1, ttl=100).newly_acquired)
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                child.join(5)
            queue.close()
            queue.join_thread()


if __name__ == '__main__':
    unittest.main()
