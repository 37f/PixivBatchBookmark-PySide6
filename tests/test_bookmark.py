import unittest

from pixiv.bookmark import ApiError, BookmarkService


def detail(private=None, bookmark_id='55'):
    data = None if private is None else {'id': bookmark_id, 'private': private}
    return {'error': False, 'body': {'id': '97003966', 'title': 'Example', 'bookmarkData': data}}


def drive(generator, replies):
    """External network responses are fixtures; all domain decisions run for real."""
    requests = []
    next_value = None
    for reply in replies:
        request = generator.throw(next_value) if isinstance(next_value, Exception) else generator.send(next_value)
        requests.append(request)
        next_value = reply
    try:
        request = generator.throw(next_value) if isinstance(next_value, Exception) else generator.send(next_value)
    except StopIteration as done:
        return done.value, requests
    raise AssertionError(f'Unexpected additional request: {request}')


class BookmarkTests(unittest.TestCase):
    def setUp(self):
        self.service = BookmarkService()
        self.metadata = {'error': False, 'body': {'tags': ['お気に入り', 'test'], 'comment': 'keep'}}

    def test_new_private_bookmark_is_verified(self):
        result, requests = drive(self.service.apply_one('97003966', 'bookmark', True),
                                 [detail(), {'error': False, 'body': {}}, detail(True)])
        self.assertEqual(result.status, 'success')
        self.assertEqual(requests[1].data, {'illust_id': '97003966', 'restrict': 1, 'tags': [], 'comment': ''})

    def test_same_mode_skips_without_mutation(self):
        result, requests = drive(self.service.apply_one('97003966', 'bookmark', False), [detail(False)])
        self.assertEqual(result.status, 'skipped')
        self.assertEqual(len(requests), 1)

    def test_both_conversion_directions_delete_then_add_and_preserve_tags(self):
        for old in (False, True):
            with self.subTest(old=old):
                result, requests = drive(self.service.apply_one('97003966', 'bookmark', not old),
                    [detail(old), self.metadata, {'error': False}, detail(), {'error': False}, detail(not old)])
                self.assertEqual(result.status, 'success')
                self.assertEqual(requests[2].path, '/ajax/illusts/bookmarks/delete')
                self.assertEqual(requests[2].data, {'bookmark_id': '55'})
                self.assertEqual(requests[4].data['tags'], ['お気に入り', 'test'])
                self.assertEqual(requests[4].data['comment'], 'keep')
                self.assertEqual(requests[4].data['restrict'], int(not old))

    def test_failed_conversion_restores_original_mode(self):
        result, requests = drive(self.service.apply_one('97003966', 'bookmark', True),
            [detail(False), self.metadata, {'error': False}, detail(),
             ApiError('network lost'), detail(), {'error': False}, detail(False)])
        self.assertEqual(result.status, 'failed')
        self.assertIn('已恢复原收藏', result.message)
        self.assertEqual(requests[6].data['restrict'], 0)
        self.assertEqual(requests[6].data['tags'], ['お気に入り', 'test'])

    def test_lost_add_response_is_checked_before_any_retry(self):
        result, requests = drive(self.service.apply_one('97003966', 'bookmark', True),
            [detail(), ApiError('timeout'), detail(True)])
        self.assertEqual(result.status, 'success')
        self.assertEqual(sum(r.method == 'POST' for r in requests), 1)

    def test_unbookmarked_cancel_skips(self):
        result, requests = drive(self.service.apply_one('97003966', 'remove', False), [detail()])
        self.assertEqual(result.status, 'skipped')

    def test_cancel_uses_bookmark_id_and_verifies(self):
        result, requests = drive(self.service.apply_one('97003966', 'remove', False),
                                 [detail(True), {'error': False}, detail()])
        self.assertEqual(result.status, 'success')
        self.assertEqual(requests[1].data, {'bookmark_id': '55'})
        self.assertEqual(requests[1].encoding, 'form')

    def test_delete_failure_does_not_create_duplicate_bookmark(self):
        result, requests = drive(self.service.apply_one('97003966', 'bookmark', True),
            [detail(False), self.metadata, ApiError('rejected'), detail(False)])
        self.assertEqual(result.status, 'failed')
        self.assertFalse(any(r.path.endswith('/add') for r in requests))

    def test_missing_metadata_does_not_delete_original(self):
        result, requests = drive(self.service.apply_one('97003966', 'bookmark', True),
                                 [detail(False), ApiError('metadata schema changed')])
        self.assertEqual(result.status, 'failed')
        self.assertFalse(any(r.method == 'POST' for r in requests))

    def test_schema_change_is_not_unbookmarked(self):
        result, requests = drive(self.service.apply_one('97003966', 'bookmark', True),
                                 [{'error': False, 'body': {'title': 'schema changed'}}])
        self.assertEqual(result.status, 'failed')
        self.assertTrue(result.stop_batch)
        self.assertEqual(len(requests), 1)

    def test_recovery_failure_reports_uncertain_state_and_stops(self):
        result, requests = drive(self.service.apply_one('97003966', 'bookmark', True),
            [detail(False), self.metadata, {'error': False}, detail(),
             ApiError('failed'), detail(), ApiError('restore failed'), detail()])
        self.assertEqual(result.status, 'failed')
        self.assertTrue(result.stop_batch)
        self.assertIn('人工检查', result.message)

    def test_rate_limit_stops_batch(self):
        result, requests = drive(self.service.apply_one('97003966', 'bookmark', True),
                                 [ApiError('限流', status=429)])
        self.assertTrue(result.stop_batch)

    def test_rate_limit_with_successful_final_state_still_stops(self):
        result, requests = drive(self.service.apply_one('97003966', 'bookmark', True),
            [detail(), ApiError('限流', status=429), detail(True)])
        self.assertEqual(result.status, 'success')
        self.assertTrue(result.stop_batch)

    def test_recovery_rate_limit_with_restored_state_still_stops(self):
        result, requests = drive(self.service.apply_one('97003966', 'bookmark', True),
            [detail(False), self.metadata, {'error': False}, detail(),
             ApiError('network lost'), detail(), ApiError('restore limited', status=429), detail(False)])
        self.assertEqual(result.status, 'failed')
        self.assertIn('已恢复原收藏', result.message)
        self.assertTrue(result.stop_batch)

    def test_delete_rate_limit_restores_original_instead_of_changing_mode(self):
        result, requests = drive(self.service.apply_one('97003966', 'bookmark', True),
            [detail(False), self.metadata, ApiError('限流', status=429), detail(),
             detail(), {'error': False}, detail(False)])
        self.assertEqual(result.status, 'failed')
        self.assertTrue(result.stop_batch)
        self.assertEqual(requests[-2].data['restrict'], 0)
        self.assertFalse(any(r.path.endswith('/add') and r.data['restrict'] == 1 for r in requests))

    def test_rejects_unknown_action_and_malformed_privacy(self):
        with self.assertRaises(ValueError):
            next(self.service.apply_one('97003966', 'unknown', False))
        result, _ = drive(self.service.apply_one('97003966', 'remove', False),
                          [{'error': False, 'body': {'bookmarkData': {'id': '55', 'private': 'false'}}}])
        self.assertTrue(result.stop_batch)


if __name__ == '__main__':
    unittest.main()
