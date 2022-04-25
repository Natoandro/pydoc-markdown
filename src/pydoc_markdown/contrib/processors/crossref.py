# -*- coding: utf8 -*-
# Copyright (c) 2019 Niklas Rosenstein
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

import dataclasses
import logging
import re
import typing as t

import docspec

from pydoc_markdown.interfaces import Processor, Resolver, ResolverV2
from pydoc_markdown.util.docspec import ApiSuite

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class CrossrefProcessor(Processor):
    """
    Finds references to other objects in Markdown docstrings and produces links to other
    pages. The links are provided by the current #Renderer via the #Resolver interface.

    > __Note__: This processor is a work in progress, and most of the time it just converts
    > references into inline-code.

    The syntax for cross references is as follows:

    ```
    This is a ref to another class: #PydocmdProcessor
    You can rename a ref like #this~PydocmdProcessor
    And you can append to the ref name like this: #PydocmdProcessor#s
    ```

    Renders as

    > This is a ref to another class: #PydocmdProcessor
    > You can rename a ref like #this~PydocmdProcessor
    > And you can append to the ref name like this: #PydocmdProcessor#s

    Example configuration:

    ```yaml
    processors:
      - type: crossref
    ```
    """

    #: If specified, it will be used instead of the resolver passed to #process() and the generated Markdown
    #: code for the reference uses Novella `{@link}` syntax.
    resolver_v2: t.Optional[ResolverV2] = None

    def process(self, modules: t.List[docspec.Module], resolver: t.Optional[Resolver]) -> None:
        unresolved: t.Dict[str, t.List[str]] = {}
        docspec.visit(
            modules, lambda x: self._preprocess_refs(x, t.cast(Resolver, resolver), ApiSuite(modules), unresolved)
        )

        if unresolved:
            summary = []
            for uid, refs in unresolved.items():
                summary.append("  {}: {}".format(uid, ", ".join(refs)))

            logger.warning(
                "%s cross-reference(s) could not be resolved:\n%s",
                sum(map(len, unresolved.values())),
                "\n".join(summary),
            )

    def _preprocess_refs(
        self,
        node: docspec.ApiObject,
        resolver: t.Optional[Resolver],
        suite: ApiSuite,
        unresolved: t.Dict[str, t.List[str]],
    ) -> None:
        if not node.docstring:
            return

        def handler(match: re.Match) -> str:
            ref = match.group("ref")
            parens = match.group("parens") or ""
            trailing = (match.group("trailing") or "").lstrip("#")
            # Remove the dot from the ref if its trailing (it is probably just
            # the end of the sentence).
            has_trailing_dot = False
            if trailing and trailing.endswith("."):
                trailing = trailing[:-1]
                has_trailing_dot = True
            elif not parens and ref.endswith("."):
                ref = ref[:-1]
                has_trailing_dot = True

            text = ref + parens + trailing
            result: t.Optional[str] = None

            if self.resolver_v2:
                target = self.resolver_v2.resolve_reference(suite, node, ref)
                if target:
                    import tomli_w

                    opt = tomli_w.dumps({"text": text})
                    result = f'{{@link pydoc:{".".join(x.name for x in target.path)} :with {opt}}}'

            elif resolver:
                href = resolver.resolve_ref(node, ref)
                if href:
                    result = "[`{}`]({})".format(text, href)

            if result is None:
                uid = ".".join(x.name for x in node.path)
                unresolved.setdefault(uid, []).append(ref)
                result = "`{}`".format(ref + parens + trailing)

            # Add back the dot.
            if has_trailing_dot:
                result += "."

            return result

        node.docstring.content = re.sub(
            r"\B#(?P<ref>[\w\d\._]+)(?P<parens>\(\))?(?P<trailing>#[\w\d\._]+)?", handler, node.docstring.content
        )
