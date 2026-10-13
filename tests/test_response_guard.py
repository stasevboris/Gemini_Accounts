import unittest
from response_guard import StreamProbe, usable_message


class ResponseGuardTests(unittest.TestCase):
    def test_fragmented_sse_and_thinking_only(self):
        probe = StreamProbe()
        data = b'data: {"type":"content_block_delta","delta":{"type":"thinking_delta","thinking":"Working"}}\r\n\r\ndata: {"type":"message_stop"}\r\n\r\n'
        for byte in data:
            probe.feed(bytes([byte]))
        self.assertFalse(probe.usable)
        self.assertTrue(probe.terminal)

    def test_whitespace_text_is_empty_but_tools_are_real_output(self):
        self.assertFalse(usable_message({'content':[{'type':'text','text':' \n'}]}))
        self.assertTrue(usable_message({'content':[{'type':'tool_use','name':'Read'}]}))

    def test_search_requires_provider_results_and_does_not_accept_plain_links(self):
        text = {'type': 'text', 'text': 'I know this link: https://docs.python.org/'}
        self.assertFalse(usable_message({'content': [text]}, require_search=True))
        probe = StreamProbe(require_search=True)
        probe.feed(b'data: {"type":"content_block_start","content_block":{"type":"text","text":"I cannot search"}}\n\n')
        probe.feed(b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"https://docs.python.org"}}\n\n')
        self.assertFalse(probe.usable)
        probe.feed(b'data: {"type":"content_block_start","content_block":{"type":"web_search_tool_result","content":[]}}\n\n')
        self.assertTrue(probe.usable)
        self.assertTrue(usable_message({'content': [{'type': 'web_search_tool_result', 'content': []}]}, require_search=True))
