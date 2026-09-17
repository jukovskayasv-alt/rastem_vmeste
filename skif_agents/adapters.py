from __future__ import annotations

import base64
import json
import mimetypes
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from .core import split_message


class APIError(RuntimeError):
    """Sanitized error: never includes URL/token or server response body."""
    def __init__(self, message='Ошибка внешнего сервиса', status=None):
        super().__init__(message); self.status = status


def http_post(url, *, payload=None, headers=None, body=None, timeout=120):
    headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=body, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read(8_000_001)
            if len(raw) > 8_000_000: raise APIError('Ответ сервиса слишком большой')
            return json.loads(raw)
    except urllib.error.HTTPError as error:
        raise APIError(f'Сервис вернул HTTP {error.code}', error.code) from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise APIError('Не удалось подтвердить ответ сервиса') from None


def extract_response(raw):
    if raw.get('status') != 'completed':
        raise APIError('ИИ не завершил ответ. Результат не принят.')
    texts, citations = [], []
    for item in raw.get('output', []):
        for content in item.get('content', []):
            if content.get('type') == 'refusal': raise APIError('ИИ не выполнил запрос')
            if content.get('type') == 'output_text':
                texts.append(content.get('text',''))
                for c in content.get('annotations', []):
                    if c.get('type') == 'url_citation' and c.get('url', '').startswith('https://'):
                        citations.append({'url':c['url'], 'title':c.get('title',c['url'])})
    if not texts: raise APIError('ИИ вернул пустой ответ')
    return '\n'.join(texts), list({c['url']:c for c in citations}.values())


def response_payload(model, system, prompt, schema=None, images=None, web=False, domains=None):
    contents = [{'type':'input_text','text':prompt}]
    for path in images or []:
        path = Path(path)
        if path.stat().st_size > 3_000_000: raise ValueError('Изображение для проверки больше 3 МБ')
        mime = mimetypes.guess_type(path.name)[0] or 'image/png'
        contents.append({'type':'input_image','image_url':f'data:{mime};base64,'+base64.b64encode(path.read_bytes()).decode(),'detail':'high'})
    payload = {'model':model,'instructions':system,'input':[{'role':'user','content':contents}],
               'store':False,'max_output_tokens':4500}
    if schema:
        payload['text'] = {'format':{'type':'json_schema','name':'skif_result','strict':True,'schema':schema}}
    if web:
        tool = {'type':'web_search'}
        if domains: tool['filters'] = {'allowed_domains':domains}
        payload['tools'] = [tool]
        payload['tool_choice'] = 'required'
    return payload


class Model:
    def __init__(self, settings, store): self.settings, self.store = settings, store

    def _run(self, system, prompt, schema=None, images=None, web=False, domains=None):
        if not self.settings.api_key or not self.settings.model:
            raise ValueError('ИИ не подключён: нужны OPENAI_API_KEY и OPENAI_MODEL')
        self.store.reserve_call(self.settings.daily_calls)
        payload = response_payload(self.settings.model, system, prompt, schema, images, web, domains)
        raw = http_post('https://api.openai.com/v1/responses', payload=payload,
                        headers={'Authorization':'Bearer '+self.settings.api_key})
        return extract_response(raw)

    def text(self, system, prompt, *, web=False, domains=None):
        text, citations = self._run(system,prompt,web=web,domains=domains)
        if web and not citations:
            raise APIError('Нет подтверждённых ссылок из поиска. Аналитика не принята как проверенная.')
        if citations:
            text += '\n\nИсточники:\n' + '\n'.join(c['title']+' — '+c['url'] for c in citations)
        return text

    def json(self, system, prompt, schema, images=None, web=False):
        text, _ = self._run(system,prompt,schema,images,web)
        try: return json.loads(text)
        except json.JSONDecodeError: raise APIError('ИИ вернул некорректный JSON') from None


class Telegram:
    def __init__(self, token):
        if not token or any(c.isspace() for c in token): raise ValueError('Не задан токен Telegram')
        self._base = 'https://api.telegram.org/bot' + token + '/'

    def call(self, method, payload=None, *, timeout=45):
        raw = http_post(self._base+method,payload=payload or {},timeout=timeout)
        if not raw.get('ok'): raise APIError('Telegram не подтвердил операцию', raw.get('error_code'))
        return raw['result']

    def send_text(self, chat, text):
        results = []
        for chunk in split_message(text):
            results.append(self.call('sendMessage',{'chat_id':chat,'text':chunk,'link_preview_options':{'is_disabled':True}}))
        return results

    def send_document(self, chat, path):
        path = Path(path)
        if path.stat().st_size > 20_000_000: raise ValueError('Файл превышает лимит прототипа 20 МБ')
        boundary = 'skif-'+uuid.uuid4().hex
        safe_name = path.name.replace('"','').replace('\r','').replace('\n','')
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat}\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{safe_name}"\r\n'
                'Content-Type: application/octet-stream\r\n\r\n').encode() + path.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
        raw = http_post(self._base+'sendDocument',body=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary})
        if not raw.get('ok'): raise APIError('Telegram не подтвердил получение файла')
        return raw['result']
