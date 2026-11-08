"""构造发消息的请求(messages.PutMessageRequest,用完整版 proto,带 atUserIdList)。

支持四种消息:
- 文字:可以带 @,正文里写到的「@名字」就地变成真正的 @,没写到的放在最前面。
- markdown:转成飞书富文本(post)。支持围栏代码块、标题、引用、有序和无序列表、段落,
  行内的 **加粗**、*斜体*、`代码`(只保留文字)、[文字](链接) 和裸链接。也可以带 @。
- 图片、文件:先上传(见 media.py)拿到 key 再发。

富文本的结构是按飞书网页版实际发出的数据确定的:
- 根是 DOCS(22),下面挂块级元素:段落 P(3)、列表 UL(26) / OL(27) / LI(28)、引用 QUOTE(29)、代码块 CODE_BLOCK(31)。
- 加粗、斜体是带样式(fontWeight / fontStyle)的 TEXT(1),样式同时登记进 elements.styles 和 styleRefs。
- 链接 A(6) 用 AnchorProperty。容器元素也要带 property(空字节),innerText 必须设置,否则服务端返回 400。
- 行内代码服务端会剔除,所以只保留文字;标题服务端会降级成段落,这里发成加粗的段落。
"""
import re

from .gateway import _lark_all
from .ids import generate_request_cid

TYPE_POST, TYPE_FILE, TYPE_TEXT, TYPE_IMAGE = 2, 3, 4, 5
TEXT, PARA, AT, LINK, DOCS, UL, OL, LI, QUOTE, CODE_BLOCK = 1, 3, 5, 6, 22, 26, 27, 28, 29, 31
BOLD = ('fontWeight', 'bold')
ITALIC = ('fontStyle', 'italic')
ANCHOR_CUSTOM = 3   # AnchorProperty.Scene.CUSTOM_EDIT:自定义文字的链接

# CodeBlockProperty.Language(V1 枚举);不认识的语言按 SHELL
CODE_LANGS = {'js': 0, 'javascript': 0, 'bash': 2, 'sh': 2, 'zsh': 2, 'cs': 3, 'csharp': 3, 'cpp': 4, 'c++': 4, 'c': 4,
              'html': 6, 'xml': 7, 'http': 8, 'json': 9, 'java': 10, 'makefile': 11, 'markdown': 12, 'md': 12, 'nginx': 13,
              'objc': 14, 'php': 15, 'perl': 16, 'py': 17, 'python': 17, 'ruby': 18, 'rb': 18, 'sql': 19, 'shell': 20,
              'go': 21, 'golang': 21, 'scss': 22, 'lua': 23, 'kotlin': 25, 'kt': 25}
DEFAULT_LANG = 20

FENCE = re.compile(r'^```\s*([\w+#.-]*)\s*$')
HEADING = re.compile(r'^#{1,6}\s+(.*)$')
QUOTE_LINE = re.compile(r'^>\s?(.*)$')
UL_ITEM = re.compile(r'^\s*[-*+]\s+(.*)$')
OL_ITEM = re.compile(r'^\s*(\d{1,9})[.)]\s+(.*)$')
RULE = re.compile(r'^\s*([-*_])(\s*\1){2,}\s*$')
# 行内标记:`代码`、**加粗**、*斜体*、[文字](链接)、裸链接。* 两侧不能紧挨空白,「2 * 3 * 4」不算斜体
INLINE = re.compile(
    r'(`[^`\n]+`'
    r'|\*\*(?=\S)[^\n]+?(?<=\S)\*\*'
    r'|(?<!\*)\*(?=[^\s*])[^*\n]+?(?<=[^\s*])\*(?!\*)'
    r'|\[[^\]\n]+\]\(https?://[^\s)]+\)'
    r'|https?://[^\s<>"\'　-〿＀-￯一-鿿]+)')
MD_LINK = re.compile(r'^\[([^\]\n]+)\]\((.+)\)$')
URL_TAIL = '.,;:!?\'"'


def _trim_url(url: str) -> str:
    """裸链接结尾的句读不算进链接,多出来的右括号也不算(成对的保留)。"""
    while url:
        c = url[-1]
        if c in URL_TAIL or (c in ')]' and url.count(c) > url.count('(' if c == ')' else '[')):
            url = url[:-1]
        else:
            break
    return url


def inline_tokens(text: str, styles=()):
    """把一行文字切成 (kind, 文字, 链接, 样式):kind 是 text / link / url。加粗、斜体的内部再递归解析一遍。"""
    for i, part in enumerate(INLINE.split(text or '')):
        if not part:
            continue
        if i % 2 == 0:
            yield 'text', part, '', styles
        elif part.startswith('`'):
            yield 'text', part[1:-1], '', styles
        elif part.startswith('**'):
            yield from inline_tokens(part[2:-2], styles + (BOLD,))
        elif part.startswith('*'):
            yield from inline_tokens(part[1:-1], styles + (ITALIC,))
        elif part.startswith('['):
            m = MD_LINK.match(part)
            yield ('link', m.group(1), m.group(2), styles) if m else ('text', part, '', styles)
        else:
            url = _trim_url(part)
            yield 'url', url, url, styles
            if len(part) > len(url):
                yield 'text', part[len(url):], '', styles


def plain_markdown(markdown: str) -> str:
    """markdown 去掉标记后的纯文字,存进本地消息库用。"""
    out, in_code = [], False
    for raw in (markdown or '').split('\n'):
        if FENCE.match(raw.strip()):
            in_code = not in_code
            continue
        if in_code:
            out.append(raw)
            continue
        line = raw.strip()
        for pattern in (HEADING, QUOTE_LINE):
            m = pattern.match(line)
            if m:
                line = m.group(1)
        m = UL_ITEM.match(raw)
        if m:
            line = '- ' + m.group(1)
        m = OL_ITEM.match(raw)
        if m:
            line = f'{m.group(1)}. {m.group(2)}'
        out.append(''.join(f'{s}({url})' if kind == 'link' else s for kind, s, url, _ in inline_tokens(line)))
    return '\n'.join(out).strip()


def _split_mentions(text: str, mentions: list):
    """把文字里的「@名字」切出来:返回 [(kind, 文字或 user_id)],kind 是 text 或 at。长名字先匹配。"""
    names = sorted({m['name'] for m in mentions if m.get('name')}, key=len, reverse=True)
    if not names:
        return [('text', text)]
    pattern = re.compile('(' + '|'.join('@' + re.escape(n) for n in names) + ')')
    by_name = {m['name']: m['user_id'] for m in mentions}
    out = []
    for i, part in enumerate(pattern.split(text)):
        if not part:
            continue
        out.append(('at', by_name[part[1:]]) if i % 2 else ('text', part))
    return out


class _RichText:
    """往一个空的 RichText 里加元素。富文本(post)的元素 id 按文档顺序从 1 编号(和飞书客户端一样);
    文字消息的元素 id 用随机串(和原来的发送方式一致)。"""

    def __init__(self, rich, mentions, sequential=True):
        self.rich = rich
        self.E = _lark_all().entities.RichTextElement
        self.mentions = [m for m in mentions or [] if str(m.get('user_id', '')).isdigit()]
        self.names = {m['user_id']: m.get('name') or m['user_id'] for m in self.mentions}
        self.sequential = sequential
        self.n = 0
        self.inner = []
        self.style_index = {}

    def node(self, tag, prop=b'', children=(), styles=()):
        self.n += 1
        eid = str(self.n) if self.sequential else generate_request_cid()
        el = self.rich.elements.dictionary[eid]
        el.tag = tag
        el.property = prop
        el.childIds.extend(children)
        els = self.rich.elements
        for name, value in styles:
            el.style[name] = value
            if (name, value) not in self.style_index:
                self.style_index[(name, value)] = len(els.styles)
                els.styles.add(name=name, value=value)
            els.styleRefs[name].styleIds.append(self.style_index[(name, value)])
        return eid

    def text(self, s, styles=()):
        self.inner.append(s)
        return self.node(TEXT, self.E.TextProperty(content=s).SerializeToString(), styles=styles)

    def at(self, user_id):
        name = self.names.get(user_id, user_id)
        self.inner.append('@' + name)
        eid = self.node(AT, self.E.AtProperty(userId=str(user_id), content='@' + name).SerializeToString())
        self.rich.atIds.append(eid)
        return eid

    def inline(self, line, base_styles=()):
        """一行文字的行内元素 id 列表。"""
        ids = []
        for kind, s, url, styles in inline_tokens(line, tuple(base_styles)):
            if kind == 'url':
                ids.append(self.node(LINK, self.E.AnchorProperty(href=url, content=url, textContent=url).SerializeToString(), styles=styles))
                self.inner.append(url)
            elif kind == 'link':
                prop = self.E.AnchorProperty(href=url, content=s, isCustom=True, scene=ANCHOR_CUSTOM)
                ids.append(self.node(LINK, prop.SerializeToString(), styles=styles))
                self.inner.append(s)
            else:
                for k, v in _split_mentions(s, self.mentions):
                    ids.append(self.at(v) if k == 'at' else self.text(v, styles))
        return ids

    def lead_mentions(self, written: str):
        """正文里没写到的 @ 放在最前面:返回这些 @ 的元素 id(每个后面跟一个空格)。"""
        ids = []
        for m in self.mentions:
            if '@' + (m.get('name') or m['user_id']) not in written:
                ids += [self.at(m['user_id']), self.text(' ')]
        return ids

    def end_block(self):
        if self.inner and not self.inner[-1].endswith('\n'):
            self.inner.append('\n')


def _outside_code(markdown: str) -> str:
    """markdown 里代码块以外的文字(代码块里的「@名字」不会变成 @)。"""
    out, in_code = [], False
    for line in (markdown or '').split('\n'):
        if FENCE.match(line.strip()):
            in_code = not in_code
        elif not in_code:
            out.append(line)
    return '\n'.join(out)


def fill_markdown(rich, markdown: str, mentions=()):
    """把 markdown 填进空的 RichText,返回被 @ 到的 user_id 列表。"""
    t = _RichText(rich, mentions)
    blocks, lines, i = [], (markdown or '').split('\n'), 0
    lead = t.lead_mentions(_outside_code(markdown))
    if lead:
        blocks.append(t.node(PARA, children=lead))
        t.end_block()
    while i < len(lines):
        raw, line = lines[i], lines[i].strip()
        fence = FENCE.match(line)
        if fence:
            body, i = [], i + 1
            while i < len(lines) and not FENCE.match(lines[i].strip()):
                body.append(lines[i])
                i += 1
            i += 1
            code = '\n'.join(body)
            t.inner.append(code)
            prop = t.E.CodeBlockProperty(language=CODE_LANGS.get(fence.group(1).lower(), DEFAULT_LANG), content=code + '\n')
            blocks.append(t.node(CODE_BLOCK, prop.SerializeToString()))
            t.end_block()
            continue
        if not line or RULE.match(line):
            i += 1
            continue
        heading = HEADING.match(line)
        if heading:
            # 飞书不显示标题,服务端会降成段落;这里发成加粗的段落
            blocks.append(t.node(PARA, children=t.inline(heading.group(1), (BOLD,))))
            t.end_block()
            i += 1
            continue
        if QUOTE_LINE.match(line):
            paras = []
            while i < len(lines) and QUOTE_LINE.match(lines[i].strip()):
                content = QUOTE_LINE.match(lines[i].strip()).group(1)
                if content:
                    paras.append(t.node(PARA, children=t.inline(content)))
                    t.end_block()
                i += 1
            blocks.append(t.node(QUOTE, children=paras))
            continue
        ul, ol = UL_ITEM.match(raw), OL_ITEM.match(raw)
        if ul or ol:
            pattern, items, start = (OL_ITEM if ol else UL_ITEM), [], int(ol.group(1)) if ol else 1
            while i < len(lines) and pattern.match(lines[i]):
                m = pattern.match(lines[i])
                items.append(t.node(LI, children=t.inline(m.group(2) if ol else m.group(1))))
                t.end_block()
                i += 1
            prop = t.E.OLProperty(type=0, start=start) if ol else t.E.ULProperty(type=0)
            blocks.append(t.node(OL if ol else UL, prop.SerializeToString(), children=items))
            continue
        # 连续的普通行合成一个段落,行间换行
        children = t.inline(line)
        i += 1
        while i < len(lines):
            nxt = lines[i]
            s = nxt.strip()
            if not s or FENCE.match(s) or HEADING.match(s) or QUOTE_LINE.match(s) or UL_ITEM.match(nxt) or OL_ITEM.match(nxt) or RULE.match(s):
                break
            children.append(t.text('\n'))
            children += t.inline(s)
            i += 1
        blocks.append(t.node(PARA, children=children))
        t.end_block()
    rich.elementIds.append(t.node(DOCS, children=blocks))
    rich.innerText = ''.join(t.inner).strip() or ' '
    rich.version = 1
    return [m['user_id'] for m in t.mentions]


def fill_text(rich, text: str, mentions=()):
    """普通文字消息:一段一个元素,@ 是 AT 元素。返回被 @ 到的 user_id 列表。"""
    t = _RichText(rich, mentions, sequential=False)
    ids = t.lead_mentions(text or '')
    for kind, v in _split_mentions(text or '', t.mentions):
        ids.append(t.at(v) if kind == 'at' else t.text(v))
    if not ids:
        ids.append(t.text(''))
    rich.elementIds.extend(ids)
    rich.innerText = ''.join(t.inner)
    return [m['user_id'] for m in t.mentions]


def message_request(chat_id: str, *, text: str = None, markdown: str = None, mentions=(), image_key: str = None,
                    file: dict = None, root_id: str = None, thread_chat: bool = False, quote: bool = False):
    """生成 PutMessageRequest。回复:带 root_id。普通群里默认回进话题(isReplyInThread);quote 为真是主会话里的引用回复;
    话题群本来就在话题里,不能带 isReplyInThread(服务端会拒收)。"""
    L = _lark_all()
    req = L.messages.PutMessageRequest()
    req.chatId = str(chat_id)
    req.cid = generate_request_cid()
    req.isNotified = True
    req.version = 1
    if root_id:
        req.rootId = req.parentId = str(root_id)
        if not thread_chat and not quote:
            req.isReplyInThread = True
    if image_key:
        # 只填 imageKey 会被拒,上传得到的 key 要同时填进 cryptoToken
        req.type = TYPE_IMAGE
        req.content.imageKey = req.content.cryptoToken = str(image_key)
        return req
    if file:
        req.type = TYPE_FILE
        req.content.fileKey = str(file['key'])
        req.content.fileName = str(file.get('name') or 'file')
        req.content.fileSize = int(file.get('size') or 0)
        if file.get('mime'):
            req.content.fileMime = str(file['mime'])
        return req
    if markdown is not None:
        req.type = TYPE_POST
        at_ids = fill_markdown(req.content.richText, markdown, mentions)
    else:
        req.type = TYPE_TEXT
        at_ids = fill_text(req.content.richText, text or '', mentions)
    for uid in dict.fromkeys(at_ids):
        req.atUserIdList.append(int(uid))
    return req
