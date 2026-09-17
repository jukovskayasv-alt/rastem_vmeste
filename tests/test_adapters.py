import unittest
from skif_agents.adapters import extract_response, response_payload, APIError


class AdapterTests(unittest.TestCase):
    def test_response_preserves_verified_source_annotations(self):
        raw = {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'Ответ','annotations':[{'type':'url_citation','url':'https://rosreestr.gov.ru/a','title':'Росреестр'}]}]}]}
        text, urls = extract_response(raw)
        self.assertEqual(text, 'Ответ')
        self.assertEqual(urls[0]['url'], 'https://rosreestr.gov.ru/a')

    def test_incomplete_or_refused_result_not_success(self):
        with self.assertRaises(APIError):
            extract_response({'status':'incomplete','output':[]})
        with self.assertRaises(APIError):
            extract_response({'status':'completed','output':[{'content':[{'type':'refusal','refusal':'No'}]}]})

    def test_private_requests_not_stored_and_schema_is_strict(self):
        payload = response_payload('configured-model','system','brief',{'type':'object','properties':{},'required':[],'additionalProperties':False})
        self.assertFalse(payload['store'])
        self.assertTrue(payload['text']['format']['strict'])
        self.assertNotIn('tools', payload)


if __name__ == '__main__': unittest.main()
