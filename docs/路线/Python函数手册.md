# CareerPilot v3 Python 函数手册

> 面向「C 写得多、Python 写得少」的速查表。
> **只给签名和语义，不给业务逻辑**——业务逻辑是你自己要写的部分（见 `CareerPilot-v3-主线提纲.md`）。
>
> 索引：
> §1 C 程序员最容易踩的语言差异 · §2 类型标注 · §3 字符串 · §4 容器 · §5 文件与路径
> §6 JSON · §7 正则 · §8 类与 dataclass · §9 异常 · §10 并发 · §11 numpy
> §12 embedding · §13 统计 · §14 DeepSeek（OpenAI SDK）· §15 杂项 · §16 项目组织

---

## §1 C 程序员最容易踩的六个差异

**① 变量是名字绑定，不是内存槽位**

```python
a = [1, 2]
b = a          # b 和 a 指向同一个 list，不是拷贝
b.append(3)    # a 现在也是 [1, 2, 3]

c = a[:]       # 浅拷贝
import copy
d = copy.deepcopy(a)   # 深拷贝
```

赋值 `=` 永远不复制对象。函数传参同理——传的是引用，函数内 `lst.append(x)` 调用方能看到，但 `lst = [...]` 只是重新绑定局部名字，调用方看不到。

**② 可变默认参数是共享的（最经典的 Python 坑）**

```python
def bad(items=[]):      # ❌ 这个 [] 只在定义时创建一次，所有调用共享
    items.append(1)
    return items
bad()  # [1]
bad()  # [1, 1]   ← 不是 [1]

def good(items=None):   # ✅ 标准写法
    if items is None:
        items = []
```

**③ 真值判断很宽**

```python
if not lst:      # 空 list / 空 str / 空 dict / 0 / None / False 都是假
if x is None:    # 判 None 用 is，不用 ==
```
注意 `if not lst` 和 `if lst is None` 不等价：空列表和 None 都过前者，只有 None 过后者。要区分「没有」和「空的」时必须用 `is None`。

**④ 整除、取模、除法**

```python
7 / 2    # 3.5   ← 永远是 float，和 C 不同
7 // 2   # 3     整除
-7 // 2  # -4    向下取整，不是向零取整（C 是 -3）
-7 % 2   # 1     结果符号跟除数，不是被除数（C 是 -1）
```

**⑤ 没有块作用域，但有函数作用域**

```python
for i in range(3):
    pass
print(i)         # 2 —— i 泄漏到循环外，合法

def f():
    x = 1        # 局部
def g():
    global_x += 1   # ❌ UnboundLocalError：赋值让它变成局部变量
```
闭包里想修改外层变量要 `nonlocal`，想改模块级变量要 `global`。只**读**不需要声明。

**⑥ 没有 switch（3.10+ 有 match，但这个项目用 if/elif 就够）**

```python
finish = resp.choices[0].finish_reason
if finish == "stop":
    ...
elif finish == "tool_calls":
    ...
else:
    raise RuntimeError(f"未预期的 finish_reason: {finish}")
```
**最后那个 else 一定要 raise，不要 pass。**（提纲 L5 说的就是这条。）

---

## §2 类型标注

标注**不影响运行**，纯粹是给人和 IDE 看的。写了对你有好处：你从 C 来，习惯知道类型。

```python
def f(x: int, name: str = "") -> bool: ...
def g(items: list[str]) -> dict[str, int]: ...
def h(x: int | None) -> tuple[dict, dict]: ...     # | 是 union，None 表示可空
def noret() -> None: ...                            # 无返回值
```

`list[str]` 这种下标写法需要 Python 3.9+；`X | None` 需要 3.10+。想在更老版本用，或者想在类内部引用类自身：

```python
from __future__ import annotations   # 放文件第一行，让所有标注变成延迟求值
```

---

## §3 字符串

Python 的 `str` 是**不可变的 Unicode 序列**，`len()` 返回字符数（不是字节数）。要字节用 `s.encode("utf-8")` 得到 `bytes`。

**f-string（格式化，替代 printf）**

```python
f"{name} 得分 {score}"
f"{ratio:.4f}"            # 保留 4 位小数
f"{n:>8}"                 # 右对齐宽度 8
f"{d!r}"                  # 用 repr() 而不是 str()
f"{val=}"                 # 输出 "val=3"，调试很方便
f"多行\n用 {x} 也行"
```
f-string 里不能有反斜杠转义（3.12 前）；想嵌引号用不同的引号种类。

**常用方法**（都返回新字符串，原串不变）

| 调用 | 作用 |
|---|---|
| `s.strip()` / `.lstrip()` / `.rstrip()` | 去首尾空白（可传参指定去哪些字符） |
| `s.lower()` / `.upper()` | 大小写 |
| `s.replace(old, new)` | 全部替换 |
| `s.split(sep)` | 切成 list；不传参按任意空白切并丢弃空项 |
| `s.splitlines()` | 按行切，自动处理 `\n` / `\r\n` |
| `sep.join(list_of_str)` | 拼接。**注意是 sep 调用，不是 list** |
| `s.startswith(p)` / `.endswith(p)` | 前后缀判断 |
| `sub in s` | 子串判断，返回 bool ← 溯源率就靠这个 |
| `s.find(sub)` | 返回下标，找不到 -1（`s.index` 找不到会抛异常） |
| `s[a:b]` | 切片，越界不报错自动截断 |
| `ch.isspace()` / `.isdigit()` / `.isalpha()` | 字符类判断 |

**多行字符串**

```python
SYSTEM_PROMPT = """第一行
第二行"""                  # 三引号，保留换行

s = (                      # 括号内相邻字面量自动拼接，无需 +
    "第一段。"
    "第二段。"
)
```

---

## §4 容器

### list

```python
lst = [1, 2, 3]
lst.append(x)              # 尾部加一个
lst.extend(other)          # 尾部加多个（lst += other 等价）
lst.pop()                  # 弹出并返回尾部；pop(0) 弹头部（O(n)）
lst[-1]                    # 最后一个元素；lst[-2] 倒数第二
lst[a:b]                   # 切片，返回新 list
lst[:n] + [x]              # 拼接产生新 list
len(lst)
sorted(lst, key=..., reverse=True)   # 返回新的；lst.sort(...) 原地
lst.clear()
```

**列表推导式**（替代 for + append，这个项目里到处要用）

```python
[f(x) for x in items]                     # map
[x for x in items if cond(x)]             # filter
[f(x) for x in items if cond(x)]          # 两者一起
[y for x in nested for y in x]            # 展平：for 的顺序和嵌套 for 循环一致
{x.name for x in items}                   # 集合推导
{k: v for k, v in pairs}                  # 字典推导
sum(1 for x in items if cond(x))          # 计数（生成器表达式，不建列表）
```

### dict

```python
d = {"a": 1}
d["a"]                     # 不存在抛 KeyError
d.get("b")                 # 不存在返回 None
d.get("b", 0)              # 带默认值
d["b"] = 2                 # 插入或更新
"b" in d                   # 键存在判断
d.keys() / d.values() / d.items()
for k, v in d.items(): ...
d.setdefault(k, [])        # 不存在则设为默认值并返回
{**d1, **d2}               # 合并（d2 覆盖 d1）
{**base, **extra}          # 常用于往 dict 里塞额外字段
```

Python 3.7+ 的 dict **保持插入顺序**。这一点在 L10 缓存那里很关键：工具定义序列化成 JSON 时，dict 顺序稳定 → 字节稳定 → 缓存前缀才能匹配上。

### set（gaps 的 precision/recall 靠它）

```python
s = {"a", "b"}
s = set(iterable)
a & b                      # 交集
a | b                      # 并集
a - b                      # 差集
len(a & b) / len(a)        # precision 的形状
```

### 遍历辅助

```python
for i, x in enumerate(items): ...
for i, x in enumerate(items, 1): ...      # 从 1 开始计数
for a, b in zip(xs, ys): ...              # 并行遍历，按短的截断
for x in reversed(lst): ...
for k in sorted(d): ...
next(x for x in items if cond(x))         # 取第一个满足的；没有会抛 StopIteration
next((x for x in items if cond(x)), None) # 带默认值版本
any(cond(x) for x in items)
all(cond(x) for x in items)
```

`next(...)` 那两行在 loop.py 里会用到——从 content block 列表里取出第一个 text block。用哪个版本取决于「没有 text block」是不是一个应该报错的状态（想清楚再选）。

---

## §5 文件与路径（用 pathlib，别用 os.path）

```python
from pathlib import Path

p = Path(__file__).parent                 # 当前文件所在目录
p = Path(__file__).parent / "docs"        # / 是拼接运算符
p.exists() / p.is_file() / p.is_dir()
p.mkdir(parents=True, exist_ok=True)
p.name                                    # "index.py"
p.stem                                    # "index"
p.suffix                                  # ".py"

# 读写：小文件一行搞定，Windows 上 encoding 必须显式写，否则默认 GBK
text = p.read_text(encoding="utf-8")
p.write_text(text, encoding="utf-8")

# 追加或流式，用 with
with p.open("a", encoding="utf-8") as f:  # "r" 读 "w" 覆盖 "a" 追加
    f.write("...")
    for line in f: ...                    # 读模式下逐行迭代，不占内存

# glob
for f in sorted(p.glob("**/*.md")): ...   # ** 递归；sorted 保证顺序稳定
```

`with` 是 RAII：块结束自动关闭，异常也会关。**不要手写 `f = open(...)` / `f.close()`。**

`sorted()` 那个不是强迫症——文件遍历顺序影响 chunk 顺序，影响索引，影响可复现性。

---

## §6 JSON

```python
import json

d = json.loads(s)                                     # str → dict
s = json.dumps(d, ensure_ascii=False)                 # dict → str，中文不转义
s = json.dumps(d, ensure_ascii=False, indent=2)       # 人类可读
```

**`ensure_ascii=False` 一定要写**，否则中文变成 `中文`，日志和落盘文件都没法看。

**JSONL（每行一个 JSON，dataset.jsonl 的格式）**

```python
rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
```
`if l.strip()` 是为了跳过空行——手工编辑过的文件末尾经常多一个换行。

`json.loads` 失败抛 `json.JSONDecodeError`（是 `ValueError` 的子类）。L2 第一步会见到它。

---

## §7 正则（切块要用）

```python
import re

m = re.match(pattern, s)        # 只从开头匹配，不匹配返回 None
m = re.search(pattern, s)       # 任意位置
if m:
    m.group(0)                  # 整个匹配
    m.group(1)                  # 第一个捕获组（从 1 开始，不是 0）

re.sub(pattern, repl, s)        # 替换
re.findall(pattern, s)          # 所有匹配的列表
re.split(pattern, s)
```

**pattern 一律用 raw string `r"..."`**，否则 `\s` `\d` 这类要写成 `\\s`。

markdown 标题匹配的形状：`r"^(#{1,6})\s+(.*)"` —— 两个捕获组分别是井号串（长度即层级）和标题文字。剩下的逻辑你自己写。

---

## §8 类与 dataclass

`@dataclass` 就是 C 的 struct，自动生成构造函数、`__repr__`、`__eq__`。

```python
from dataclasses import dataclass, field

@dataclass
class Chunk:
    text: str                              # 位置参数
    source: str
    score: float = 0.0                     # 有默认值的必须排在后面
    tags: list[str] = field(default_factory=list)   # 可变默认值必须用这个（见 §1②）

c = Chunk("正文", "resume.md")
c = Chunk(text="正文", source="resume.md") # 关键字参数
c.text                                     # 直接访问，没有 getter
print(c)                                   # 自动有可读的 repr
```

**普通类**

```python
class KnowledgeBase:
    def __init__(self, name: str = "..."):
        self.name = name                   # self 必须显式写，相当于 C++ 的 this
        self._model = None                 # 单下划线 = 约定的"内部"，无强制力

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        return ...

    @property
    def model(self):                       # 调用时写 kb.model，不写括号
        if self._model is None:            # 懒加载的标准形状
            self._model = load_expensive()
        return self._model

    @staticmethod
    def helper(x): ...                     # 无 self
```

**模块级单例**：文件底部写 `KB = KnowledgeBase()`，别处 `from kb.index import KB`。模块只会被导入执行一次，天然单例。

**关键字参数展开**：`f(**d)` 把 dict 展开成关键字参数。这个在执行工具时用得上——工具入参本来就是个 dict。

---

## §9 异常

```python
try:
    risky()
except ValueError as e:
    ...
except (KeyError, TypeError) as e:
    ...
except Exception as e:                     # 捕获一切"正常"异常
    print(f"{type(e).__name__}: {e}")      # ← 这个组合把类名和消息都记下来
finally:
    cleanup()

raise RuntimeError(f"消息 {x}")
raise RuntimeError("外层消息") from e       # 保留原始异常链
```

不要写裸 `except:`（会连 `KeyboardInterrupt` 一起吃掉，Ctrl-C 都停不下来）。

`type(e).__name__` + `str(e)` 这个组合在 L6 会用到——工具失败时你要把这两样都告诉模型，光有消息模型判断不出是网络问题还是参数问题。

---

## §10 并发（一轮多个 tool_call 时用）

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=8) as pool:
    results = list(pool.map(func, items))   # 保序：results[i] 对应 items[i]
```

`pool.map` **保持输入顺序**，这正是你要的——`role:"tool"` 结果要能和 `tool_call` 对上。（虽然真正对上靠的是 `tool_call_id`，但顺序一致更不容易出错。）

`with` 块退出时会等所有任务完成。

`pool.map` 的坑：如果 `func` 抛异常，异常在**迭代结果时**才抛出，不是提交时。这意味着 `list(...)` 那一行会炸。所以 L6 的 try/except 必须在 `func` **内部**，不能包在外面。

关于 GIL：Python 的线程受全局锁限制，纯计算并行不了。但你这里主要是 API 调用和 IO 等待，线程完全够用；numpy 的向量运算也会释放 GIL。**不需要 multiprocessing。**

---

## §11 numpy（检索的全部数学）

```python
import numpy as np

a = np.asarray(lst, dtype=np.float32)     # list → array（能不拷贝就不拷贝）
a.shape                                   # (n, dim)  元组
a.dtype

# 矩阵乘：(n, dim) @ (dim,) → (n,)  一次算出 query 对所有 chunk 的相似度
scores = mat @ vec

# 排序：argsort 返回的是下标，不是值
idx = np.argsort(-scores)[:k]              # 负号 = 降序，取前 k
float(scores[i])                           # numpy 标量 → Python float（json 不认 np 类型）

# 归一化后点积 == 余弦相似度，所以不需要每次算分母
```

**存盘**（避免每次启动重新 embedding）

```python
np.savez_compressed(path, vecs=arr, meta=np.array(list_of_str, dtype=object))
d = np.load(path, allow_pickle=True)      # 存了 object 数组就必须 allow_pickle
arr = d["vecs"]
```
`dtype=object` 用来存变长字符串数组。`allow_pickle=True` 只对自己生成的文件用——它能执行任意代码，别拿去读来源不明的 npz。

`scores` 是 `np.float32`，`json.dumps` 会抛 `TypeError: Object of type float32 is not JSON serializable`。落盘前记得 `float()`。

---

## §12 embedding

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-small-zh-v1.5")   # 首次会下载模型

vecs = model.encode(
    list_of_str,
    normalize_embeddings=True,      # 归一化，之后点积即余弦
    batch_size=32,
    show_progress_bar=True,
)                                   # → np.ndarray, shape (n, dim)
```

选型理由（面试会问）：本地推理、中文效果好、不依赖 API key、离线可跑。

**bge 系列有一个非对称约定**：query 侧要加指令前缀，文档侧不加。前缀漏了，相似度会系统性偏低。具体前缀文本查模型卡（中文 bge 是「为这个句子生成表示用于检索相关文章：」这一类）。这不是玄学，是模型训练时的构造方式决定的。

**模型加载很慢（几秒）**，所以要懒加载（§8 的 `@property` 形状）——评测脚本只做溯源字符串匹配时根本不需要加载模型。

---

## §13 统计

```python
from scipy.stats import spearmanr
rho, p = spearmanr(list_a, list_b)         # 秩相关系数, p 值
                                           # rho 和 p 都是 numpy 标量，落盘要 float()

import statistics
statistics.mean(iterable)                  # 平均
statistics.median(iterable)
round(x, 4)

# 百分位（30 条规模手算就行，不用引 numpy.percentile）
s = sorted(values)
p50 = s[len(s) // 2]
p95 = s[int(len(s) * 0.95) - 1]

from collections import Counter
c = Counter(iterable)
c.most_common(8)                           # → [(item, count), ...] 按频次降序
```

`Counter` 在 L9 分析「漏检最多的能力项」时用——它直接告诉你下一轮该优化哪里。

---

## §14 DeepSeek（OpenAI SDK）工具调用

> ⚠️ 参数名和可用特性**随 SDK / API 版本变化**。下面是形状和概念，写之前用 `pip show openai`
> 确认版本，并对照你那个版本的官方文档核对字段名。
> 手册的价值在于告诉你**该找什么**，不是替你记住字段名。

```python
import os
from openai import OpenAI
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
)

resp = client.chat.completions.create(
    model="deepseek-v4-flash",
    temperature=0,
    messages=messages,
    tools=TOOLS,                              # 工具定义列表
    response_format={"type": "json_object"},  # L2 的结构化输出，最终答案仍靠它
)
```

### 响应对象

```python
msg = resp.choices[0]        # 一个请求取第一个 choice
msg.finish_reason            # "stop" | "tool_calls" | "length" | ...
msg.message                  # ChatCompletionMessage 对象

m = msg.message
m.content                    # str | None（finish_reason == "tool_calls" 时是 None）
m.tool_calls                 # list[ChatCompletionMessageToolCall] | None
```

**tool_call 是对象不是 dict**，用 `.` 访问：

| 字段 | 说明 |
|---|---|
| `tc.id` | 工具调用 id，回结果时用它对齐 |
| `tc.type` | 固定 `"function"` |
| `tc.function.name` | 工具名 |
| `tc.function.arguments` | **JSON 字符串**，要 `json.loads` |

```python
[tc for tc in m.tool_calls]
```

### messages 的结构

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": jd_text},
]

resp = client.chat.completions.create(model="...", messages=messages, tools=TOOLS)
msg = resp.choices[0].message

messages.append(msg)                        # ← assistant 整条原样放回，不要只取 content

for tc in msg.tool_calls:                   # 每个 tool_call 一条 role:"tool" 消息
    args = json.loads(tc.function.arguments)   # arguments 是 JSON 字符串
    result = execute_tool(tc.function.name, args)
    messages.append({
        "role": "tool",
        "tool_call_id": tc.id,              # 用响应里带的 id，别自己生成
        "content": result,                  # 字符串；dict 要先 json.dumps
    })
```

四个协议约束（不是风格问题，违反了 API 会报错或行为退化）：
1. assistant 的 message **整条原样**追加回去。只追加 text 会丢掉 tool_calls，下一轮请求直接报错。
2. 每个 `tool_call` 必须有一条 `role:"tool"` 消息与之对应，`tool_call_id` 一致。
3. `role:"tool"` 的 `content` 是**字符串**，dict 要先 `json.dumps`。
4. 同一轮的所有 `role:"tool"` 结果放在**同一批**（紧跟 assistant 消息之后、下一条 user 消息之前）。

### 工具定义的形状

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "...",
            "description": "...",       # ← 这是代码不是注释：模型据此决定要不要调、参数怎么填
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "..."},
                    "top_k": {"type": "integer", "description": "默认 3，最多 8"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
]
```

`description` 里除了「这个工具做什么」，还要写「**什么时候不该调**」和「参数该长什么样（给正反例）」。L7 的全部工作量在这里。

### Claude 缓存断点（L10 才用，先跳过）

```python
{"type": "text", "text": "...", "cache_control": {"type": "ephemeral"}}
```

放在**最后一个要被缓存的 block** 上，表示「从开头到这里为止缓存住」。

推理的唯一依据：**渲染顺序 `tools → system → messages`，前缀匹配。** 剩下的自己推（提纲 L10）。

验证：`cache_read_input_tokens` 第二次请求起应该 > 0。一直是 0 就是前缀里混了变动内容。

断点数量有上限；前缀回溯有窗口限制（大约 20 个 content block）。超窗口是**静默 miss**——不报错，只是账单变贵。

---

## §15 杂项

```python
import time
t0 = time.monotonic()                      # 单调时钟，测耗时用这个
elapsed = time.monotonic() - t0            # 不要用 time.time()（会被系统改时间影响）

from datetime import datetime, timezone
datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")

import hashlib
h = hashlib.sha256()
h.update(s.encode("utf-8"))                # 只吃 bytes，str 必须先 encode
h.hexdigest()[:12]                         # 指纹，写进评测报告用

import os
os.environ.get("ANTHROPIC_API_KEY")        # 不存在返回 None

import sys
sys.argv[1] if len(sys.argv) > 1 else "baseline"   # 简单的命令行参数
```

**知识库指纹**（`hashlib`）的用处：评测报告里写上它，就能回答「这组数字是在哪个版本的知识库上跑的」。没有它，你改了几篇文档之后就说不清前后两组数字还有没有可比性。

---

## §16 项目组织

**包结构**：每个目录放一个 `__init__.py`（空文件即可），这样 `from agent.tools import TOOLS` 才能工作。

**运行方式**：用 `python -m agent.tools` 而不是 `python agent/tools.py`。后者会让相对导入（`from .tools import ...`）失败。

**自测入口**：每个模块底部加

```python
if __name__ == "__main__":
    ...   # 只在直接运行时执行，被 import 时不执行
```

这让每个模块可以独立跑一遍验证自己——提纲 L3 的验收「`python -m kb.index` 能重建索引」就是这个。

**虚拟环境**：

```bash
python -m venv .venv
source .venv/Scripts/activate      # Git Bash on Windows
pip install -r requirements.txt
pip freeze > requirements.txt
```

**Windows 编码**：所有 `read_text` / `write_text` / `open` 都显式写 `encoding="utf-8"`。默认是 GBK，中文文档会直接抛 `UnicodeDecodeError`。这个坑你一定会踩一次。

**依赖**：

```
anthropic
sentence-transformers
numpy
scipy
fastapi
uvicorn
sqlmodel
streamlit
httpx
trafilatura           # HTML 正文提取，fetch_jd 用；不要自己写 HTML 清洗
```

**.gitignore**（第一天就建）：

```
.venv/
__pycache__/
*.npz
.env
```

`dataset.jsonl` 和 `report.md` **不要**加进 .gitignore——它们是要给面试官看的（提纲 L11）。

---

## 附：查文档比背签名有用

这份手册覆盖的是「你会反复用到、不查也该有印象」的部分。写代码时真正该查的：

| 要查什么 | 去哪 |
|---|---|
| SDK 参数名、结构化输出、缓存字段 | DeepSeek / OpenAI 官方文档（**版本要对上**） |
| bge 的 query 前缀原文 | HuggingFace 上该模型的 model card |
| 标准库函数的完整签名 | `help(func)` 或 `python -m pydoc xxx` |
| 某个对象有什么方法 | `dir(obj)`，或者交互式 `python` 里点一下 |

从 C 转过来最需要改的一个习惯：Python 的东西**在运行时都是可以问出来的**。卡住的时候开一个 `python` 交互解释器，把对象打印出来看，比读文档快。

```python
>>> print(type(resp.content[0]))
>>> print(dir(resp.usage))
>>> print(resp.model_dump_json(indent=2))   # SDK 对象转 JSON 看全貌
```

最后那一行在调 API 的时候特别有用——响应对象长什么样，直接 dump 出来看，不用猜。
