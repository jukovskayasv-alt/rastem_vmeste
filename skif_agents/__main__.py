from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from .adapters import APIError, Model, Telegram
from .core import Settings, Store, load_env_file, identify_owner
from .health import check_heartbeat, validate_telegrams, write_heartbeat


async def serve(settings):
    from .service import TeamService
    store=Store(settings.root/'runtime/team.sqlite')
    store.recover()
    telegrams={r:Telegram(t) for r,t in settings.tokens.items()}
    await validate_telegrams(telegrams)
    service=TeamService(settings,store,Model(settings,store),telegrams)

    async def heartbeat():
        while True:
            write_heartbeat(settings.root/'runtime/health.json',os.environ.get('SKIF_RELEASE',''),telegrams)
            await asyncio.sleep(20)

    async def poll(role,telegram):
        failures=0
        while True:
            try:
                updates=await asyncio.to_thread(telegram.call,'getUpdates',{'offset':store.offset(role),'timeout':25,'allowed_updates':['message']})
                for update in updates:
                    await asyncio.to_thread(service.handle_update,role,update)
                failures=0
            except APIError as error:
                if error.status in (401,403,409):
                    raise ValueError(f'{role}: проверьте доступ Telegram и отсутствие другого запущенного процесса') from None
                failures+=1
                print(f'{role}: временная ошибка соединения, повтор получения сообщений',flush=True)
                await asyncio.sleep(min(30,2**min(failures,4)))
    print('СКИФ: четыре обработчика запущены. Доступ только разрешённым владельцам.',flush=True)
    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(heartbeat())
            for role,telegram in telegrams.items(): group.create_task(poll(role,telegram))
    finally: store.close()


def demo(root):
    from .finance import build_schedule, export_schedule
    from .contracts import create_contract
    from .presentations import generate_deck
    # Keep bundled examples and previous runs intact.
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]
    output=root/'demo'/('run-'+run_id); output.mkdir(parents=True)
    schedule=build_schedule('600000','200000',12,'2026-10-01')
    paths=export_schedule(schedule,output)
    (output/'schedule.json').write_text(json.dumps(schedule,ensure_ascii=False,indent=2),encoding='utf-8')
    deal=json.loads((root/'data/deal.example.json').read_text(encoding='utf-8'))
    for kind in ('preliminary','main'):
        paths.append(create_contract(kind,deal,output/f'{kind}_DEMO.docx'))
    result=generate_deck('Краткая инвестиционная презентация СКИФ',json.loads((root/'data/project.json').read_text(encoding='utf-8')),root/'assets',output/'presentation',model=None)
    print(json.dumps({'mode':'offline_demo','files':[str(x) for x in paths],'presentation':result},ensure_ascii=False,indent=2))


def main():
    parser=argparse.ArgumentParser(description='СКИФ: команда Telegram-ботов')
    parser.add_argument('command',choices=['check','demo','health','identify','probe','run'])
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    try:
        if args.command=='demo': return demo(args.root)
        if args.command=='health':
            if check_heartbeat(args.root/'runtime/health.json',os.environ.get('SKIF_RELEASE','')):
                print('Работает')
                return
            parser.exit(1,'Нет свежего heartbeat для текущего релиза\n')
        load_env_file(args.root/'.env')
        settings=Settings.from_env(root=args.root)
        if args.command=='identify':
            token=settings.tokens.get('finance')
            if not token: raise ValueError('Сначала внесите TELEGRAM_FINANCE_TOKEN в .env')
            telegram=Telegram(token)
            hook=telegram.call('getWebhookInfo')
            if hook.get('url'): raise ValueError('На боте действует webhook; проверка ID через polling недоступна.')
            project=json.loads((args.root/'data/project.json').read_text(encoding='utf-8'))
            username=project.get('telegram_owner',{}).get('username','')
            if not username: raise ValueError('В project.json не указан username владельца')
            user_id=identify_owner(telegram.call('getUpdates',{'timeout':0,'allowed_updates':['message']}),username)
            print(f'Входящее /start от @{username}; Telegram ID: {user_id}. Внесите этот ID в SKIF_OWNER_IDS на сервере.')
            return
        missing=settings.missing()
        if args.command=='check':
            if missing: raise ValueError('Требуются настройки: '+', '.join(missing))
            print('Готово к подключению')
            return
        if missing: raise ValueError('Не настроены: '+', '.join(missing))
        if len(set(settings.tokens.values()))!=4: raise ValueError('Четыре роли требуют четыре разных токена')
        if args.command=='probe':
            asyncio.run(validate_telegrams({r:Telegram(t) for r,t in settings.tokens.items()}))
            print('Telegram готов')
            return
        asyncio.run(serve(settings))
    except (ValueError,APIError) as error:
        parser.exit(2,str(error)+'\n')
    except KeyboardInterrupt:
        print('Команда остановлена.')
    except Exception:
        parser.exit(2,'Работа остановлена. Проверьте конфигурацию и доступ к внешним сервисам. Секреты в журнал не выведены.\n')


if __name__=='__main__': main()
