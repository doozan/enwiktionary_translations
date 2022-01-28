import pytest
import re
from ..t9nparser import TranslationTable as TT

def test_parse_lang_line():
    assert TT.parse_lang_line("* Spanish: {{tt|es|foo}} bar") == ('*', 'Spanish', '{{tt|es|foo}} bar')
    assert TT.parse_lang_line("* Spanish: {{tt|es|foo}}, {{tt|es|bar}}") == ('*', 'Spanish', '{{tt|es|foo}}, {{tt|es|bar}}')
    assert TT.parse_lang_line("  * Spanish: {{tt|es|foo}} bar") == ('*', 'Spanish', '{{tt|es|foo}} bar')
    assert TT.parse_lang_line("* Spanish {{tt|es|foo}} bar") == ('*', 'Spanish', '{{tt|es|foo}} bar')
    assert TT.parse_lang_line("*: Spanish: {{tt|es|foo}} bar") == ('*:', 'Spanish', '{{tt|es|foo}} bar')
    assert TT.parse_lang_line(" Spanish: {{tt|es|foo}} bar") == ('', 'Spanish', '{{tt|es|foo}} bar')
    assert TT.parse_lang_line("Spanish {{tt|es|foo}} bar") == ('', 'Spanish', '{{tt|es|foo}} bar')
    assert TT.parse_lang_line("Spanish: bar") == ('', 'Spanish', 'bar')
    assert TT.parse_lang_line("Spanish bar") == None
    assert TT.parse_lang_line("* Spanish bar") == None
    assert TT.parse_lang_line("{{tt|es|foo}}") == None
    assert TT.parse_lang_line("") == None
    assert TT.parse_lang_line("* Spanish:") == ('*', 'Spanish', '')

def test_parse_template_line():
    assert TT.parse_template_line("{{test}}") == ('', 'test', '', '')
    assert TT.parse_template_line("{{ test }}") == ('', 'test', '', '')
    assert TT.parse_template_line("{{ test | bar }}") == ('', 'test', ' bar ', '')
    assert TT.parse_template_line("pre {{test}} post") == ('pre ', 'test', '', ' post')
    assert TT.parse_template_line("pre {{test|foo|bar=baz|}} post") == ('pre ', 'test', 'foo|bar=baz|', ' post')
    assert TT.parse_template_line("{{foo|bar}} {{baz}}") == ('', 'foo', 'bar', ' {{baz}}')
    assert TT.parse_template_line("unclosed|end}} {{foo|bar}} {{baz|foo}}") == ('unclosed|end}} ', 'foo', 'bar', ' {{baz|foo}}')

    assert TT.parse_template_line("test") == None
    assert TT.parse_template_line("{test}") == None
    assert TT.parse_template_line("{test}}") == None

    # matches single } closing brace, known bug, okay to squash
    assert TT.parse_template_line("{{test|blah}") == ('', 'test', 'blah', '')
    assert TT.parse_template_line("{{test}") == ('', 'test', '', '')

