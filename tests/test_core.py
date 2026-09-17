import tempfile
import unittest
from pathlib import Path
from skif_agents.core import Settings, Store, split_message, identify_owner


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.tmp.name) / 'test.sqlite')

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_authorization_fails_closed_and_rejects_groups(self):
        cfg = Settings.from_env({})
        self.assertFalse(cfg.authorized(7, 'private'))
        cfg = Settings.from_env({'SKIF_OWNER_IDS': '7,8'})
        self.assertTrue(cfg.authorized(7, 'private'))
        self.assertFalse(cfg.authorized(7, 'group'))
        self.assertFalse(cfg.authorized(9, 'private'))

    def test_only_task_owner_can_read_it_across_roles(self):
        task = self.db.create_task(7, 'legal', 'ask', 'ВРИ?')
        self.db.finish(task, 'needs_owner_review', 'Ответ', [])
        self.assertEqual(self.db.get_task(task, 7)['result'], 'Ответ')
        with self.assertRaises(PermissionError):
            self.db.get_task(task, 8)

    def test_publication_is_exact_once_and_hash_bound(self):
        task = self.db.create_task(7, 'strategy', 'blog', 'Море')
        self.db.finish(task, 'needs_owner_review', 'Текст публикации', [])
        digest = self.db.publication_digest(task, 7)
        with self.assertRaises(ValueError):
            self.db.claim_publication(task, 7, 'wrong')
        with self.assertRaises(PermissionError):
            self.db.claim_publication(task, 8, digest)
        self.assertEqual(self.db.claim_publication(task, 7, digest), 'Текст публикации')
        self.db.publication_result(task, 'published', '45')
        with self.assertRaises(ValueError):
            self.db.claim_publication(task, 7, digest)

    def test_uncertain_publication_cannot_auto_retry(self):
        task = self.db.create_task(7, 'strategy', 'blog', 'Море')
        self.db.finish(task, 'needs_owner_review', 'Текст', [])
        digest = self.db.publication_digest(task, 7)
        self.db.claim_publication(task, 7, digest)
        self.db.publication_result(task, 'unknown', '')
        with self.assertRaises(ValueError):
            self.db.claim_publication(task, 7, digest)

    def test_non_blog_cannot_publish(self):
        task = self.db.create_task(7, 'legal', 'ask', 'ВРИ?')
        self.db.finish(task, 'needs_owner_review', 'Заключение', [])
        with self.assertRaises(ValueError):
            self.db.publication_digest(task, 7)

    def test_update_replay_not_processed_twice(self):
        self.assertTrue(self.db.claim_update('legal', 15))
        self.assertFalse(self.db.claim_update('legal', 15))
        self.assertTrue(self.db.claim_update('design', 15))
        self.assertEqual(self.db.offset('legal'), 16)

    def test_daily_budget_counts_failed_attempts_too(self):
        self.db.reserve_call(2, '2026-09-17')
        self.db.reserve_call(2, '2026-09-17')
        with self.assertRaises(ValueError):
            self.db.reserve_call(2, '2026-09-17')
        self.db.reserve_call(2, '2026-09-18')

    def test_telegram_split_preserves_unicode_content(self):
        text = '🌊Привет ' * 1500
        chunks = split_message(text)
        self.assertEqual(''.join(chunks), text)
        self.assertTrue(all(len(c.encode('utf-16-le')) // 2 <= 3500 for c in chunks))

    def test_owner_identification_uses_private_start_from_exact_username(self):
        updates=[{'message':{'from':{'id':7,'username':'Gorshkova_Svetlana'},'chat':{'type':'private'},'text':'/start'}},
                 {'message':{'from':{'id':8,'username':'Different'},'chat':{'type':'private'},'text':'/start'}}]
        self.assertEqual(identify_owner(updates,'@Gorshkova_Svetlana'),7)
        updates[0]['message']['chat']['type']='group'
        with self.assertRaises(ValueError): identify_owner(updates,'Gorshkova_Svetlana')


if __name__ == '__main__':
    unittest.main()
