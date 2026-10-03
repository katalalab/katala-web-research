#!/usr/bin/env python3
"""Freeze Python oracle digit facts; never used at native runtime."""
import unicodedata
from pathlib import Path
assert unicodedata.unidata_version == '15.1.0', 'regenerate only with the recorded Python 3.13 oracle'
zeros=[];ranges=[];first=last=None
for value in range(0x110000):
    char=chr(value)
    if unicodedata.decimal(char,None)==0:zeros.append(value)
    if char.isdigit():
        if last is None:first=last=value
        elif value==last+1:last=value
        else:ranges.append((first,last));first=last=value
if last is not None:ranges.append((first,last))
text='''//! Digit facts generated from the Python 3.13 / Unicode 15.1 oracle.
//! Includes isdigit-only characters which int() rejects (e.g. superscripts).
const ZEROS: &[u32] = &[\n'''+''.join(f'    0x{n:x},\n' for n in zeros)+'];\nconst DIGITS: &[(u32, u32)] = &[\n'+''.join(f'    (0x{a:x}, 0x{b:x}),\n' for a,b in ranges)+'''];
pub fn is_digit(c: char) -> bool {
    DIGITS.iter().any(|(a,b)| (*a..=*b).contains(&(c as u32)))
}
pub fn decimal(c: char) -> Option<u32> {
    let n = c as u32;
    ZEROS.iter().find_map(|zero| n.checked_sub(*zero).filter(|v| *v < 10))
}
pub fn decimal_int(value: &str) -> Option<u32> {
    if value.is_empty() { return None; }
    value.chars().try_fold(0u32, |n,c| n.checked_mul(10)?.checked_add(decimal(c)?))
}
'''
(Path(__file__).resolve().parents[2]/'rust/src/python_digits.rs').write_text(text)
