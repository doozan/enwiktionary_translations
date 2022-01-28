import re

from collections import defaultdict

from enwiktionary_parser.utils import nest_aware_split, wiki_search
from enwiktionary_parser.languages.all_ids import languages as lang_ids
ALL_LANGS = {v:k for k,v in lang_ids.items()}

from .language_aliases import language_aliases as LANG_ALIASES, language_parents as ALLOWED_PARENTS

UNKNOWN_LANGS = defaultdict(lambda: defaultdict(int))
LANG_PARENTS = defaultdict(int)
LANG_STATS = defaultdict(int)

class TranslationTable():

    TOP_TEMPLATES = ("trans-top", "trans-top-see", "trans-top-also", "checktrans-top", "ttbc-top")
    BOTTOM_TEMPLATES = ("checktrans-bottom", "trans-bottom", "ttbc-bottom")
    RE_TOP_TEMPLATES = "|".join(TOP_TEMPLATES)
    RE_BOTTOM_TEMPLATES = "|".join(BOTTOM_TEMPLATES)

    # Lines than can appear in the table without generating an error
    ALLOWED_LINES = ["{{trans-mid}}", "{{trans-bottom}}", r"{{multitrans\|data=", "}}"]
    RE_ALLOWED_LINES = re.compile(r"\s*(" + "|".join(ALLOWED_LINES) + r")+\s*$")

    def __init__(self, page, pos, lines, log_function=lambda *x: None):
        self._orig_header = lines[0]
        self._orig = lines[1:]
        self.template = None
        self.params = {} # head template paramaters
        self.page = page
        self.pos = pos
        self.gloss = None
        self._log = log_function

        self.parse_header(self._orig_header)
        self.items = self.parse_table(self._orig)
        self.check_footer(lines[-1])

    def log(self, error, line="", highlight="", language=""):
        self._log(error, self.page, self.pos, self.gloss, language, line, highlight)
    error = log

    _RE_TEMPLATE_LINE = re.compile(fr"^(.*?){{{{\s*([^|}}]+?)\s*[|}}]([^}}]*)}}*(.*)$")
    @classmethod
    def parse_template_line(cls, line):
        res = re.match(cls._RE_TEMPLATE_LINE, line)
        if not res:
            return
        return res.groups()

    def parse_header(self, line):
        res = self.parse_template_line(line)
        if res:
            pretext, template, params, posttext = res

        if not res or template not in self.TOP_TEMPLATES:
            raise ValueError("cannot parse header")
            self.error("unparsable_header", line)
            return

        if pretext and pretext.strip():
            self.error("header_has_pretext", pretext)

        self.template = template.strip()
        self.params = params.strip()
        self.gloss = self.params_to_gloss(self.params)

        if posttext and posttext.strip():
            self.error("header_has_posttext", posttext)

    def check_footer(self, line):
        res = self.parse_template_line(line)
        if not res:
            return

        pretext, template, params, posttext = res

        if pretext and pretext.strip():
            self.error("footer_has_pretext", pretext)

        if posttext and posttext.strip():
            self.error("footer_has_posttext", posttext)

    @staticmethod
    def parse_lang_line(line):

        """
        Parses lines in the following formats:

        * Spanish: {{tt|es|blah}}   (preferred)
        * Spanish {{tt|es|blah}}    (missing :)
        * Spanish: {{tt|es|blah}}   (extra depth)
        * Spanish: blah             (translation not in template)
        Spanish: {{tt|es|blah}}     (missing depth)
        Spanish {{tt|es|blah}}      (missing depth, missing :)
        """

        match_pattern = r"""
            \s*
            ([#:*]*)        # wiki formatting
            \s*
            ([^:{]+?):?          # the language name, possibly : delimited
            \s*
            ((:|{{t).*)     # first template or : delimiter
                            # Checking for : in two places matches 'Spanish: blah' and 'Spanish {{test' but not 'Spanish blah'
        """

        res = re.search(match_pattern, line, re.VERBOSE)
        if not res:
            return
        depth = res.group(1).strip(" \u200c") #len(res.group(1)) if res.group(1) else 0
        lang = res.group(2).strip(": \u200c")  # \u200c is a non-width whitespace character
        data = res.group(3).strip(": ")
        return depth, lang, data

    def params_to_gloss(self, param_text):
        params = Translation.parse_params(param_text)
        return params.get(1, "")

    def parse_table(self, lines):
        items = []
        fixed_formatting = False

        parent_langs = []
        for line in lines:
            if not line:
                items.append(line)
                continue

            res = self.parse_lang_line(line)
            if res:
                depth, lang, data = res

                while max(len(depth)-1, 0) < len(parent_langs):
                    parent_langs.pop()
                parent_langs.append(lang)

                full_lang = ":".join(parent_langs) if len(parent_langs) > 1 else lang

                lang_id = ALL_LANGS.get(LANG_ALIASES.get(full_lang, full_lang))

                if lang_id:
                    item = TranslationLine(depth, full_lang, lang_id, data, line, self)
                    items.append(item)
                    continue

                elif full_lang:
                    # If the language doesn't resolve, get the language code from the first
                    # template and count it in UNKNOWN_LANGS (used to build LANG_ALIASES)
                    match = re.search(r"{{(?:t|t\+|tt|tt\+)\|([^|}]*)", data)
                    if match:
                        maybe_lang_id = match.group(1)
                        UNKNOWN_LANGS[full_lang][maybe_lang_id] += 1

                    elif not data:
                        if full_lang in ALLOWED_PARENTS:
                            items.append(line)
                            continue

                        # If the unknown language doesn't contain any data, count it in
                        # LANG_PARENTS (used to build ALLOWED_PARENTS)
                        LANG_PARENTS[full_lang] += 1

                    items.append(line)
                    self.error("unexpected_language", line, lang)
                    continue

            res = re.search("(<!--.*?(-->|$))", line)
            if res:
                self.error("table_html_comment", res.group(1))
                items.append(line)
                continue

            if re.match(self.RE_ALLOWED_LINES, line):
                items.append(line)
                continue

            items.append(line)
            self.error("unexpected_data", line)

#        if fixed_formatting:
#            self.log("botfix_formatting")

        return items


    TABLE_PATTERN = re.compile(f"""(?x)(?s)   # verbose regex, dotall
    {{{{                # {{ template opener (f-string escaped)
    (?:{RE_TOP_TEMPLATES})   # an opening template
    .*?
    (?:
      {{{{
        (?:{RE_BOTTOM_TEMPLATES})
        [^}}]*
      }}}}              # closing template (included in capture)
    |                   # OR
    (?=
      {{{{              # a new opening template (not captured)
        (?:{RE_TOP_TEMPLATES})
    )|$)
    """)

    @classmethod
    def find_tables(cls, text):
        yield from wiki_search(text,
                #fr"^.*{{{{\s*({cls.RE_TOP_TEMPLATES})",
                #fr"{{{{\s*({cls.RE_BOTTOM_TEMPLATES})\s*}}}}.*(?=(\n|$))",
                fr"{{{{\s*({cls.RE_TOP_TEMPLATES})",
                fr"{{{{\s*({cls.RE_BOTTOM_TEMPLATES})\s*}}}}",
                end_required=False,
                ignore_templates=True,
                ignore_nowiki=True
            )

        # re search isn't used because it can't handle html comments
        # re.findall(cls.TABLE_PATTERN, text)

    def __str__(self):
        return self._orig_header + "\n" + "\n".join(map(str,self.items))


class TranslationLine():
    """ parses a space or semicolon delimited list of translations for a single language """

    def __init__(self, depth, language, lang_id, entries, orig_line, parent):
        self.depth = depth
        self.language = language
        self.lang_id = lang_id
        self._entries = entries
        self._orig = orig_line
        self.parent = parent
        self.has_errors = False

        self.entries = self.parse_entries(entries)

    def log(self, error, highlight=""):
        if not self.parent:
            return
        self.parent.log(error, self._orig, highlight, language=lang_ids[self.lang_id])

    def error(self, error, highlight=""):
        self.has_errors = True
        self.log(error, highlight)


    @classmethod
    def parse_template(cls, template):
        """ Assumes input is exactly one template {{template|param|named=val|blah}}
            returns { "name": "template",
                      "params": {
                          1: "param",,
                          "named": "val",
                          2: "blah",
                      }
        """
        template = template.strip("{} ")
        name, _, params = "|".partition(template)

        res = {"name": name.strip(), "params": cls.parse_params(params)}

    def parse_entries(self, text):

        res = re.search("(<!--.*?(-->|$))", text)
        if res:
            self.error("item_html_comment", res.group(1))
            return []

        # TODO: {{l}} templates can be replaced with [[]] inside {{t}}
        res = re.search("{{[^}]*({{.*?}})", text)
        if res:
            self.error("nested_template", res.group(1))
            return []

        if self.has_errors:
            return []

        entries = []
        for item in self.split_entry_list(text):
            item = item.strip()
            if not item:
                continue

            entry = Translation(item, self)
            if entry.has_errors:
                self.has_errors = True
                return []
            entries.append(entry)

        if self.has_errors:
            return []

        return entries

    def split_entry_list(self, line):
        """ Splits a comma or semicolon delimited list of items that may include templates """

        # Split on delimiter unless it's inside a {{ }} or ( ) pair
        comma_delimited = list(nest_aware_split(",", line, [ ("{{", "}}"), ("(", ")"), ("<!--", "-->") ]))
        semicolon_delimited = list(nest_aware_split(";", line, [ ("{{", "}}"), ("(", ")"), ("<!--", "-->") ]))

        if len(comma_delimited) > 1 and len(semicolon_delimited) > 1:
            self.error("mixed_delimiters")
            return []

        if len(comma_delimited) > 1:
            return comma_delimited
        return semicolon_delimited

    def __str__(self):
        if self.has_errors:
            return self._orig

        depth = self.depth if self.depth else "*"
        # Convert nested names back to original
        lang_name = self.language.split(":")[-1]
        prefix = f"{self.depth} {lang_name}:"
        if self.entries:
            return prefix + " " + ', '.join(map(str, self.entries))
        return prefix

class Translation():

    ALLOW_MISSING = {
        'not used',
        't-needed',
        't-simple',
    }

    IGNORE_TEMPLATES = {
        'attention',
        'attn',
        'cite-book',
        'cite-web',
        'trans-bottom',
        'trans-mid',
        'trans-see',
    }

    LABEL_TEMPLATES = {
        'lb'
        'lbl',
        'label',
    }

    Q_TEMPLATES = {
        'i',
        'q',
        'qf',
        'qual',
        'qualifier',
    }

    G_TEMPLATES = {
        'g',
    }

    T_TEMPLATES = {
        't',
        't+',
        'tt',
        'tt+',
        't-check',
        't+check',
        't-egy',
        'tt-egy',
        't-check-egy',
        'l',
    }

    ALLOWED_TEMPLATES = IGNORE_TEMPLATES | LABEL_TEMPLATES | Q_TEMPLATES | G_TEMPLATES | T_TEMPLATES

    def __init__(self, text, parent):

        self._orig = text
        self.parent = parent
        self.has_errors = False

        self.template, \
        self.params, \
        self.qualifier, \
        self.qualifier_before \
        = self.parse_entry(text)

    def log(self, error, highlight=""):
        if not self.parent:
            return
        if highlight:
            self.parent.log(error, highlight)
        else:
            self.parent.log(error, self._orig)

    def error(self, error, highlight=""):
        self.log(error, highlight)
        self.has_errors = True

    @staticmethod
    def get_templates(text):
        return re.findall(r"({{\s*([^|}]+)(?:\|)?([^}]*)}})", text)

    @staticmethod
    def parse_params(text):
        """ input is 'param1|named=val|param2|dup=first|dup=second|g=foo|g2=bar'
            return {
                      1: "param1",
                      "named": "val",
                      2: "param2",
                      "dup": "second",
                      "g": "foo",
                      "g2": "bar"
                   }
        """

        if not text:
            return {}

        res = {}
        p = 1
        for param in text.split("|"):
            name,_,val = param.partition("=")
            name = name.strip()
            if val:
                res[name] = val.strip()
            else:
                res[p] = param.strip()
                p += 1

        return res

    TEMPLATE_PARAMS = ["ts", "sc", "tr", "alt", "lit", "id"]
    def parse_entry(self, text):
        """ Parses a single translation entry containing {{t}} and optionally {{g}} and {{q}}
        returns template_name, params, qualifier, qualifier_before

        """

        template_name = None
        params = {}
        qualifier = None
        qualifier_before = None

        genders = []

        # If set to true, will not flag "missing_t" error if no template encountered
        allow_missing = False

        for template, name, tparams in self.get_templates(text):
            name = name.strip()

            if name in self.LABEL_TEMPLATES or name in self.Q_TEMPLATES:
                # TODO: if label_templates, verify language id in p1
                if qualifier:
                    self.error("multiple_qualifier_templates")
                qualifier = template
                if not template_name:
                    qualifier_before = True

            elif name in self.G_TEMPLATES:
                if params and params.get(3): 
                    self.error("multiple_genders_sources")

                for v in self.parse_params(tparams).values():
                    if v and v not in genders:
                        genders.append(v)

            elif name in self.T_TEMPLATES:
                if template_name:
                    self.error("multiple_t_templates")
                    continue

                if allow_missing:
                    self.error("allow_missing_has_template")

                template_name = name

                params = self.parse_params(tparams)

                if name in ["l", "lang"]:
                    self.log("t_is_l")
                    continue

            elif name in self.ALLOW_MISSING:
                allow_missing = True

            elif name in self.IGNORE_TEMPLATES:
                self.has_errors = True

            else:
                self.error("unexpected_template", template)


        if not template_name or not params:
            if not allow_missing:
                self.error("missing_t")
            return None, None, None, None

        lang_id = params.get(1)
        if not lang_id:
            self.error("t_missing_p1", f"{{{{{name}|")
        elif self.parent.lang_id and lang_id != self.parent.lang_id:
            # Egyptian doesn't need lang id in p2
            if not "-egy" in name:
                self.error("wrong_language_code", f"|{lang_id}|")

        # If the genders were in external {{g}} tags, append them to the parameters
        # NOTE: This logic breaks if there are genders in external tags and also in the
        # template, because it will already have a param 3 so they won't be appended
        # However, that's okay because that has already raised an error so it will
        # always use the original, unmodified line
        if genders and not "-egy" in name:
            if 3 in params:
                self.error("multiple_genders_sources")
            else:
                for k,v in enumerate(genders, 3):
                    params[k] = v
                self.log("merged_genders")

        stripped = self.strip_templates(text)
        stripped = stripped.strip(" ,;.:¿?¡!'()")
        if stripped:
            self.error("text_outside_template", stripped)

        if not self.has_errors and not params.get(2) and not "-egy" in name:
            self.error("missing_translation_target")



        return template_name, params, qualifier, qualifier_before

    @staticmethod
    def strip_templates(text):
        return re.sub("{{[^}]*}}", "", text)

    def __str__(self):

        if self.has_errors or not self.template or not self.params:
            return self._orig

        if not self.parent.lang_id:
            raise ValueError("parent has no language id")

        data = [self.template ]
        data += [ v if isinstance(k,int) else f"{k}={v}" for k,v in self.params.items() ]

        template = "{{" + "|".join(data) + "}}"

        if self.qualifier:
            if self.qualifier_before:
                return f"{self.qualifier} {template}"
            else:
                return f"{template} {self.qualifier}"
        else:
            return template
