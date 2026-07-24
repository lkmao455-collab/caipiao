# Coding Style

## Python Version
- Python 3.12+
- 始终使用 `from __future__ import annotations`

## Naming

| Element | Convention | Example |
|---------|-----------|---------|
| Package/Module | snake_case | `data.fetcher` |
| Class | PascalCase | `DrawAnalyzer` |
| Function/Method | snake_case | `fetch_all()` |
| Variable | snake_case | `red_balls` |
| Constant | UPPER_SNAKE | `FC3D_FILTER_SAFETY` |
| Private | leading underscore | `_records` |
| Protected | leading underscore | `_validate()` |

## Type Annotations

```python
# 函数签名必须有类型注解
def fetch_all(self) -> List[DrawRecord]: ...

# 使用 Optional 表示可选
def get_latest(self) -> Optional[DrawRecord]: ...

# 使用 Union 表示多类型
profile: Union[LotteryProfile, str, None] = None

# Python 3.12+ 可用 X | Y 语法
def get(self, key: str) -> LotteryProfile | None: ...
```

## Imports

```python
# 标准库
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

# 第三方库
import numpy as np
from PySide6.QtCore import Qt

# 项目内部（相对导入）
from ..core.profile import SSQ, LotteryProfile
from .models import DrawRecord
```

## Docstrings

- 公共类和方法必须有 docstring
- 使用 Google 风格
- 简洁明了，不写废话

```python
def frequency(self, group_key: str, last_n: Optional[int] = None) -> Dict[int, int]:
    """返回指定号码组的出现频率."""
```

## Formatting

- 4 空格缩进
- 行宽 100 字符（建议，非强制）
- 函数间空 2 行
- 类内方法间空 1 行
