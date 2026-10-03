#!/usr/bin/env python3
"""Freeze the existing Python Unicode isalpha facts for language validation."""
import sys
import unicodedata
from pathlib import Path
assert sys.version_info[:2]==(3,13) and unicodedata.unidata_version=='15.1.0'
ROOT=Path(__file__).resolve().parents[2];ranges=[];start=None
for n in range(0x110001):
    yes=n<0x110000 and chr(n).isalpha()
    if yes and start is None:start=n
    elif not yes and start is not None:ranges.append((start,n-1));start=None
text='//! Frozen Python 3.13 / Unicode 15.1 isalpha facts; no Python runtime.\nconst LETTERS: &[(u32,u32)] = &[\n'+''.join(f'    (0x{start:x},0x{end:x}),\n' for start,end in ranges)+'];\npub fn is_alpha(c: char) -> bool {\n    let value=c as u32;\n    let index=LETTERS.partition_point(|(_,end)|*end<value);\n    LETTERS.get(index).is_some_and(|(start,_)|*start<=value)\n}\n'
(ROOT/'rust/src/python_alpha.rs').write_text(text);print('Frozen alphabetic ranges',len(ranges))
