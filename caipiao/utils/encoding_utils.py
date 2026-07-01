#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
编码检测工具 - 自动检测文件编码并读取文本，防止乱码。
"""

import os

try:
    import chardet
except ImportError:  # pragma: no cover
    chardet = None


def _detect_encoding_from_bytes(raw):
    """
    从字节内容检测编码。

    检测顺序：
    1. BOM 标记（UTF-8-SIG, UTF-16-LE, UTF-16-BE）
    2. UTF-8
    3. chardet 库自动检测（如已安装）
    4. 常见中文编码（GB18030, GBK, Big5 等）
    5. Latin-1（保底，不会抛异常）

    Args:
        raw: 文件原始字节内容

    Returns:
        str: 检测到的编码名称
    """
    if not raw:
        return "utf-8"

    # BOM 检测
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if raw.startswith(b"\xfe\xff"):
        return "utf-16-be"

    # 尝试 UTF-8
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # 尝试 chardet
    if chardet is not None:
        result = chardet.detect(raw)
        encoding = result.get("encoding")
        confidence = result.get("confidence", 0)
        if encoding and confidence and confidence > 0.5:
            encoding = encoding.lower()
            # 标准化编码名
            if encoding == "gb2312":
                encoding = "gb18030"
            elif encoding == "ascii":
                encoding = "utf-8"
            try:
                raw.decode(encoding)
                return encoding
            except (UnicodeDecodeError, LookupError):
                pass

    # 尝试常见中文及东亚编码
    for enc in ("gb18030", "gbk", "big5", "shift_jis", "euc-kr"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            pass

    # 最终保底：latin-1 永远不会抛异常
    return "latin-1"


def detect_file_encoding(filepath):
    """
    检测文件编码。

    Args:
        filepath: 文件路径

    Returns:
        str: 检测到的编码名称
    """
    with open(filepath, "rb") as f:
        raw = f.read()
    return _detect_encoding_from_bytes(raw)


def read_text_file_with_info(filepath):
    """
    自动检测编码和换行符，并读取文本文件。

    Args:
        filepath: 文件路径

    Returns:
        tuple: (文件内容文本, 编码名称, 换行符类型)
            换行符类型为 "CRLF"、"LF" 或 "CR"。

    Raises:
        OSError: 文件读取失败
    """
    with open(filepath, "rb") as f:
        raw = f.read()

    encoding = _detect_encoding_from_bytes(raw)
    if encoding == "latin-1":
        print(f"[EncodingUtils] Warning: Could not detect encoding for {filepath}, "
              f"falling back to latin-1. Content may be garbled.")

    # 检测换行符
    if b"\r\n" in raw:
        line_ending = "CRLF"
    elif b"\n" in raw:
        line_ending = "LF"
    elif b"\r" in raw:
        line_ending = "CR"
    else:
        line_ending = "LF"

    text = raw.decode(encoding)
    return text, encoding.upper(), line_ending


def read_text_file(filepath):
    """
    自动检测编码并读取文本文件。

    Args:
        filepath: 文件路径

    Returns:
        str: 文件内容文本

    Raises:
        OSError: 文件读取失败
    """
    text, _, _ = read_text_file_with_info(filepath)
    return text
