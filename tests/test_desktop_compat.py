import copy
import unittest

from desktop_compat import SDK_BANNER, strip_sdk_banner


class DesktopCompatTests(unittest.TestCase):
    def test_desktop_tools_and_task_instructions_survive(self):
        request = {'model': 'claude-opus-4-6-thinking', 'max_tokens': 64000,
                   'thinking': {'type': 'adaptive'}, 'output_config': {'effort': 'medium'},
                   'metadata': {'user_id': 'session'}, 'stream': True,
                   'system': [
                       {'type': 'text', 'text': 'x-anthropic-billing-header: cc_version=test;'},
                       {'type': 'text', 'text': SDK_BANNER, 'cache_control': {'type': 'ephemeral'}},
                       {'type': 'text', 'text': 'Use the tools to answer the user.', 'cache_control': {'type': 'ephemeral'}}],
                   'messages': [{'role': 'user', 'content': SDK_BANNER}],
                   'tools': [{'name': 'Read', 'input_schema': {'type': 'object'}}]}
        expected = copy.deepcopy(request)
        expected['system'].pop(1)
        self.assertTrue(strip_sdk_banner(request))
        self.assertEqual(request, expected)
        self.assertFalse(strip_sdk_banner(request))

    def test_combined_system_keeps_actual_instructions_and_cache(self):
        for separator in ('\n', '\r\n'):
            block = {'type': 'text', 'text': SDK_BANNER + separator + 'Keep all instructions.',
                     'cache_control': {'type': 'ephemeral'}}
            request = {'system': [block]}
            self.assertTrue(strip_sdk_banner(request))
            self.assertEqual(request['system'][0], dict(block, text='Keep all instructions.'))
            self.assertTrue(block['text'].startswith(SDK_BANNER))

    def test_empty_system_is_omitted(self):
        for system in (SDK_BANNER, [{'type': 'text', 'text': SDK_BANNER}]):
            request = {'system': system}
            self.assertTrue(strip_sdk_banner(request))
            self.assertNotIn('system', request)

    def test_system_string_keeps_task(self):
        request = {'system': SDK_BANNER + '\nBe concise.'}
        self.assertTrue(strip_sdk_banner(request))
        self.assertEqual(request['system'], 'Be concise.')

    def test_quotes_unknown_blocks_and_malformed_fields_are_untouched(self):
        for system in (None, {}, [{'type': 'text', 'text': None}],
                       [{'type': 'image', 'text': SDK_BANNER}],
                       'Quote: ' + SDK_BANNER,
                       'Explain this sentence:\n' + SDK_BANNER,
                       SDK_BANNER + ' Keep this quotation.'):
            request = {'system': system}
            expected = copy.deepcopy(request)
            self.assertFalse(strip_sdk_banner(request))
            self.assertEqual(request, expected)
