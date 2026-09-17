import json
import tempfile
import unittest
from pathlib import Path
from skif_agents.core import Settings, Store
from skif_agents.service import TeamService


class FakeModel:
    def __init__(self): self.calls = []
    def text(self, system, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return 'Черновик для проверки владельцем.'


class FakeTelegram:
    def __init__(self): self.messages, self.files = [], []
    def send_text(self, chat, text):
        self.messages.append((chat, text)); return [{'message_id':len(self.messages)}]
    def send_document(self, chat, path): self.files.append(str(path))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root/'data').mkdir()
        (root/'data/project.json').write_text(json.dumps({'project':'СКИФ','facts':[]}),encoding='utf-8')
        self.cfg = Settings.from_env({'SKIF_OWNER_IDS':'7','SKIF_BLOG_CHANNEL':'@configured_channel'},root)
        self.db = Store(root/'test.sqlite')
        self.model = FakeModel()
        self.tg = {r:FakeTelegram() for r in ['legal','finance','design','strategy']}
        self.service = TeamService(self.cfg,self.db,self.model,self.tg)

    def tearDown(self): self.db.close(); self.tmp.cleanup()

    def send(self, role, text, user=7, ident=1):
        self.service.handle_update(role,{'update_id':ident,'message':{'from':{'id':user},'chat':{'id':user,'type':'private'},'text':text}})

    def test_unauthorized_never_gets_project_or_triggers_model(self):
        self.send('legal','Расскажи про участок',user=8)
        self.assertFalse(self.model.calls)
        self.assertFalse(self.db.list_tasks(8))
        self.assertNotIn('600',self.tg['legal'].messages[-1][1])

    def test_calculator_delivers_calendar_without_llm(self):
        self.send('finance','/calc 600000 200000 12 2026-01-31')
        self.assertFalse(self.model.calls)
        self.assertEqual(len(self.tg['finance'].files),2)
        self.assertTrue(any(p.endswith('.ics') for p in self.tg['finance'].files))

    def test_replayed_update_cannot_create_second_draft(self):
        self.send('strategy','/blog День у моря')
        self.send('strategy','/blog День у моря')
        self.assertEqual(len(self.model.calls),1)
        self.assertEqual(len(self.db.list_tasks(7)),1)

    def test_handoff_uses_target_role_and_shared_owner(self):
        self.send('strategy','/blog День у моря')
        task=self.db.list_tasks(7)[0]['id']
        self.send('strategy',f'/handoff {task} legal Проверь формулировки',ident=2)
        self.assertEqual(self.db.list_tasks(7)[0]['role'],'legal')
        self.assertTrue(self.model.calls[-1][1]['web'])

    def test_publish_requires_exact_confirmation_then_only_once(self):
        self.send('strategy','/blog День у моря')
        task=self.db.list_tasks(7)[0]['id']
        digest=self.db.publication_digest(task,7)
        self.send('strategy',f'/publish {task} {digest}',ident=2)
        self.send('strategy',f'/publish {task} {digest}',ident=3)
        published=[m for m in self.tg['strategy'].messages if m[0]=='@configured_channel']
        self.assertEqual(len(published),1)


if __name__ == '__main__': unittest.main()
