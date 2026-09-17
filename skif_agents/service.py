from __future__ import annotations

import json
from pathlib import Path

from .adapters import APIError
from .core import ROLES

LEGAL_DOMAINS = ['pravo.gov.ru','rosreestr.gov.ru','notariat.ru','minjust.gov.ru','gosuslugi.ru','government.ru','rk.gov.ru']

HELP = '''Команда СКИФ — внутренний рабочий режим.
/project — действующие исходные данные
/tasks — мои последние задачи
/show ID — результат задачи
/files ID — повторно получить файлы
/handoff ID legal|design|finance|strategy поручение — передать специалисту
/revise ID правки — новая версия материала
/lead Имя | контакт | участок | следующий шаг
/leads — карточки клиентов

Юрист: задайте вопрос текстом; /ask вопрос
Дизайнер: /deck задание и параметры
Расчётчик: /calc цена первый_взнос месяцев дата_взноса
Пример: /calc 600000 200000 12 2026-10-01
Проект договора: /contract preliminary|main JSON
Демонстрация договора: /contract preliminary example
Аналитик: /research тема
Блог: /blog тема или /draft точный_текст
/approve ID — показать текст для утверждения
/publish ID контрольный_код — отправить точный текст в настроенный канал

Файлы клиентов и паспортные документы через этот прототип не загружайте.
Договоры — проекты для юридической проверки; отправки на регистрацию нет.'''


class TeamService:
    def __init__(self, settings, store, model, telegrams):
        self.settings, self.store, self.model, self.telegrams = settings, store, model, telegrams
        self.out = settings.root/'runtime'/'artifacts'
        self.out.mkdir(parents=True,exist_ok=True)

    def project(self):
        return json.loads((self.settings.root/'data/project.json').read_text(encoding='utf-8'))

    def handle_update(self, role, update):
        message = update.get('message', {})
        user = message.get('from', {}).get('id')
        chat = message.get('chat', {})
        if not chat.get('id') or message.get('from', {}).get('is_bot'):
            return
        if not self.store.claim_update(role, update['update_id']): return
        telegram = self.telegrams[role]
        if not self.settings.authorized(user, chat.get('type')):
            if chat.get('type') == 'private':
                telegram.send_text(chat['id'],f'Доступ не настроен. Ваш Telegram ID: {user}. Передайте его владельцу системы.')
            return
        if 'text' not in message:
            telegram.send_text(chat['id'],'В этой версии принимаются текстовые задания. Документы сделки хранятся в защищённом хранилище владельца.')
            return
        try:
            self.dispatch(role,user,chat['id'],message['text'])
        except (ValueError, PermissionError, APIError) as error:
            telegram.send_text(chat['id'],str(error))
        except Exception:
            # Never return raw exceptions: they can contain names, documents or URLs with tokens.
            telegram.send_text(chat['id'],'Не удалось завершить задание. Автоматическая отправка или оплата не выполнялась. Проверьте состояние задачи.')

    def _send_files(self, telegram, chat, paths):
        for raw in paths:
            path = Path(raw).resolve()
            if not path.is_relative_to(self.out.resolve()): raise ValueError('Файл вне каталога результатов')
            if path.is_file(): telegram.send_document(chat,path)

    def dispatch(self, role, user, chat, text):
        telegram = self.telegrams[role]
        head, _, tail = text.strip().partition(' ')
        command = head.split('@',1)[0].lower()
        if command in ('/start','/help'):
            return telegram.send_text(chat,HELP)
        if command == '/project':
            return telegram.send_text(chat,json.dumps(self.project(),ensure_ascii=False,indent=2))
        if command == '/tasks':
            rows=self.store.list_tasks(user)
            return telegram.send_text(chat,'\n'.join(f"{x['id']} · {x['role']} · {x['kind']} · {x['status']}" for x in rows) or 'Задач пока нет.')
        if command in ('/show','/files'):
            task=self.store.get_task(tail.strip(),user)
            if command=='/files': return self._send_files(telegram,chat,task['files'])
            return telegram.send_text(chat,f"Задача {task['id']} · {task['status']}\n\n{task['result']}")
        if command == '/lead':
            parts=[x.strip() for x in tail.split('|')]
            if len(parts)!=4: raise ValueError('Формат: /lead Имя | контакт | участок | следующий шаг')
            ident=self.store.add_lead(user,*parts)
            return telegram.send_text(chat,'Карточка клиента сохранена: '+ident)
        if command == '/leads':
            return telegram.send_text(chat,'\n\n'.join(f"{x['id']} · {x['name']} · {x['contact']}\nУчасток: {x['plot']}\nДалее: {x['next_step']}" for x in self.store.leads(user)) or 'Карточек пока нет.')
        if command == '/approve':
            task=self.store.get_task(tail.strip(),user)
            digest=self.store.publication_digest(task['id'],user)
            return telegram.send_text(chat,task['result']+f"\n\nКанал: {self.settings.channel or 'не настроен'}\nДля отправки именно этого текста: /publish {task['id']} {digest}")
        if command == '/publish':
            if not self.settings.channel: raise ValueError('Канал блога не настроен. Черновик сохранён.')
            parts=tail.split()
            if len(parts)!=2: raise ValueError('Сначала /approve ID, затем /publish ID контрольный_код')
            ident,digest=parts
            post=self.store.claim_publication(ident,user,digest)
            try:
                responses=self.telegrams['strategy'].send_text(self.settings.channel,post)
                self.store.publication_result(ident,'published',responses[-1]['message_id'])
            except Exception:
                self.store.publication_result(ident,'unknown','')
                raise ValueError('Результат отправки не подтверждён. Проверьте канал вручную; автоматический повтор заблокирован.') from None
            return telegram.send_text(chat,'Текст опубликован в настроенном канале.')
        if command in ('/handoff','/revise'):
            parts=tail.split(' ',2 if command=='/handoff' else 1)
            if len(parts)!=(3 if command=='/handoff' else 2): raise ValueError('Укажите ID задачи, роль для передачи и поручение.')
            old=self.store.get_task(parts[0],user)
            target=parts[1] if command=='/handoff' else old['role']
            if target not in ROLES: raise ValueError('Роли: legal, design, finance, strategy')
            instruction=parts[2] if command=='/handoff' else parts[1]
            brief=f"Исходное задание:\n{old['brief'][:6000]}\nПредыдущий результат:\n{old['result'][:6000]}\nНовое поручение:\n{instruction}"
            kind='deck' if target=='design' else ('blog' if old['kind']=='blog' and target=='strategy' else 'ask')
            return self._job(role,target,user,chat,kind,brief)
        if command=='/calc':
            return self._job(role,'finance',user,chat,'calc',tail)
        if command=='/contract':
            return self._job(role,'finance',user,chat,'contract',tail)
        modes={'/deck':('design','deck'),'/research':('strategy','research'),'/blog':('strategy','blog'),'/draft':('strategy','draft'),'/ask':(role,'ask')}
        if command in modes:
            target,kind=modes[command]
            if not tail.strip(): raise ValueError('Добавьте задание после команды.')
            return self._job(role,target,user,chat,kind,tail)
        if command.startswith('/'):
            raise ValueError('Неизвестная команда. Список: /help')
        return self._job(role,role,user,chat,'deck' if role=='design' else 'ask',text)

    def _job(self, reply_role, target, user, chat, kind, brief):
        from .roles import COMMON_PROMPT, ROLE_PROMPTS
        telegram=self.telegrams[reply_role]
        actual_kind='blog' if kind=='draft' else kind
        ident=self.store.create_task(user,target,actual_kind,brief)
        directory=self.out/ident
        directory.mkdir()
        telegram.send_text(chat,f'Задача {ident}: {target}. Начинаю.')
        try:
            files=[]; status='needs_owner_review'
            if kind=='calc':
                from .finance import build_schedule, export_schedule
                values=brief.split()
                if len(values)!=4: raise ValueError('Формат: /calc 600000 200000 12 2026-10-01')
                plan=build_schedule(values[0],values[1],int(values[2]),values[3])
                files=export_schedule(plan,directory)
                result=f"Цена: {plan['price']} ₽. Первый взнос: {plan['down_payment']} ₽. Рассрочка: {plan['months']} мес., без процентов.\nCSV и календарь ICS приложены. Дата первого взноса: {plan['start_date']}. Последующие платежи — со следующего месяца."
                status='calculated'
            elif kind=='contract':
                from .contracts import create_contract
                contract_kind,sep,raw=brief.partition(' ')
                if not sep: raise ValueError('Нужны preliminary|main и JSON либо example')
                data=json.loads((self.settings.root/'data/deal.example.json').read_text()) if raw.strip()=='example' else json.loads(raw)
                output=directory/f'contract_{contract_kind}_DRAFT.docx'
                files=[create_contract(contract_kind,data,output)]
                result='Подготовлен проект договора DOCX. Он требует проверки документов, условий расчётов и заключения юриста перед подписанием. В демонстрации используются вымышленные данные.' if data.get('demo') else 'Подготовлен проект договора DOCX. Перед подписанием нужны проверка актуальной ЕГРН, продавца, формы сделки и согласованных условий расчётов.'
            elif kind=='deck':
                from .presentations import generate_deck
                deck=generate_deck(brief,self.project(),self.settings.root/'assets',directory,self.model,self.settings.max_attempts)
                files=[p for p in (deck.get('pdf'),deck.get('report')) if p]
                status=deck['status']
                result=f"Презентация: {status}. Попыток: {deck['attempts']}.\nPDF и отчёт проверки приложены. Перед отправкой инвесторам подтвердите итоговую версию."
            elif kind=='draft':
                result=brief
            else:
                if target=='finance':
                    result='Точные расчёты выполняются командой /calc цена первый_взнос месяцев дата_взноса. Проекты договоров: /contract preliminary|main JSON. Посмотреть пример полей можно в инструкции пакета.'
                else:
                    project=self.project()
                    # Send the current facts needed for this role; never the entire chat history.
                    selected={'location','construction','permitted_use','land_category','applications','approvals','electricity','water','beach_access','city_access','concept','planned_facilities'}
                    context=json.dumps({
                        'project':project.get('project'),'as_of':project.get('as_of'),
                        'priorities':project.get('priorities',[]),'offer':project.get('offer'),
                        'contact':project.get('contact'),
                        'facts':[{k:v for k,v in x.items() if k in ('id','value','status','as_of')} for x in project.get('facts',[]) if x.get('id') in selected],
                        'evidence_note':'ЕГРН в базе архивная, 14.04.2025; необходима свежая выписка по выбранному участку.'
                    },ensure_ascii=False)
                    system=COMMON_PROMPT+'\n'+ROLE_PROMPTS[target]
                    prompt='Проверяемая база проекта:\n'+context+'\n\nЗадание владельца:\n'+brief
                    if kind=='blog': prompt+='\nВыдай только текст поста до 2800 символов, без новых рыночных цифр и без служебных комментариев. Это черновик.'
                    use_web=target=='legal' or kind=='research' or (target=='strategy' and kind=='ask')
                    result=self.model.text(system,prompt,web=use_web,domains=LEGAL_DOMAINS if target=='legal' else None)
            text_file=directory/'result.txt'; text_file.write_text(result,encoding='utf-8')
            self.store.finish(ident,status,result,files)
        except Exception:
            self.store.finish(ident,'failed','Работа не завершена; результат не отправлен на публикацию.',[])
            raise
        telegram.send_text(chat,f'Задача {ident}\n\n'+result)
        self._send_files(telegram,chat,files)
