use regex::Regex;
use std::sync::LazyLock;

// HTML text-context decoding, including the reference's legacy names and C1 map.
pub fn unescape(value: &str) -> String {
    static ENTITY: LazyLock<Regex> = LazyLock::new(|| {
        Regex::new(r"&(#(?:[0-9]+|[xX][0-9a-fA-F]+);?|[^\t\n\x0c <&#;]{1,32};?)").unwrap()
    });
    const LEGACY: &str = "Aacute aacute Acirc acirc acute AElig aelig Agrave agrave AMP amp Aring aring Atilde atilde Auml auml brvbar Ccedil ccedil cedil cent COPY copy curren deg divide Eacute eacute Ecirc ecirc Egrave egrave ETH eth Euml euml frac12 frac14 frac34 GT gt Iacute iacute Icirc icirc iexcl Igrave igrave iquest Iuml iuml laquo LT lt macr micro middot nbsp not Ntilde ntilde Oacute oacute Ocirc ocirc Ograve ograve ordf ordm Oslash oslash Otilde otilde Ouml ouml para plusmn pound QUOT quot raquo REG reg sect shy sup1 sup2 sup3 szlig THORN thorn times Uacute uacute Ucirc ucirc Ugrave ugrave uml Uuml uuml Yacute yacute yen yuml";
    ENTITY
        .replace_all(value, |caps: &regex::Captures<'_>| {
            let name = &caps[1];
            if let Some(number) = name.strip_prefix('#') {
                let number = number.trim_end_matches(';');
                let n = if number.starts_with(['x', 'X']) {
                    u32::from_str_radix(&number[1..], 16)
                } else {
                    number.parse::<u32>()
                };
                let mut n = n.unwrap_or(0x110000);
                n = match n {
                    0 => 0xfffd,
                    0x80 => 0x20ac,
                    0x82 => 0x201a,
                    0x83 => 0x192,
                    0x84 => 0x201e,
                    0x85 => 0x2026,
                    0x86 => 0x2020,
                    0x87 => 0x2021,
                    0x88 => 0x2c6,
                    0x89 => 0x2030,
                    0x8a => 0x160,
                    0x8b => 0x2039,
                    0x8c => 0x152,
                    0x8e => 0x17d,
                    0x91 => 0x2018,
                    0x92 => 0x2019,
                    0x93 => 0x201c,
                    0x94 => 0x201d,
                    0x95 => 0x2022,
                    0x96 => 0x2013,
                    0x97 => 0x2014,
                    0x98 => 0x2dc,
                    0x99 => 0x2122,
                    0x9a => 0x161,
                    0x9b => 0x203a,
                    0x9c => 0x153,
                    0x9e => 0x17e,
                    0x9f => 0x178,
                    _ => n,
                };
                if (0xd800..=0xdfff).contains(&n) || n > 0x10ffff {
                    return "�".to_string();
                }
                if (1..=8).contains(&n)
                    || matches!(n, 11 | 14..=31 | 127)
                    || (0xfdd0..=0xfdef).contains(&n)
                    || n & 0xffff >= 0xfffe
                {
                    return String::new();
                }
                return char::from_u32(n).unwrap().to_string();
            }
            let lookup = |name: &str| {
                html_escape::NAMED_ENTITIES
                    .binary_search_by(|(key, _)| key.cmp(&name.as_bytes()))
                    .ok()
                    .map(|i| {
                        let value = html_escape::NAMED_ENTITIES[i].1;
                        if value.chars().count() == 1 {
                            format!("{value}{}", entity_suffix(name))
                        } else {
                            value.to_string()
                        }
                    })
            };
            if let Some(full) = name.strip_suffix(';').and_then(lookup) {
                return full.to_string();
            }
            if let Some(prefix) = LEGACY
                .split_whitespace()
                .filter(|p| name.starts_with(p))
                .max_by_key(|p| p.len())
            {
                return format!("{}{}", lookup(prefix).unwrap(), &name[prefix.len()..]);
            }
            caps[0].to_string()
        })
        .into_owned()
}

// The locked entity table stores only the first scalar for these HTML names.
// Supplement their standard second scalars; the full name table is golden-tested.
fn entity_suffix(name: &str) -> &'static str {
    for (names, suffix) in [
        ("acE", "\u{333}"),
        ("bne bnequiv nparsl", "\u{20e5}"),
        (
            "caps cups gesl gvertneqq gvnE lates lesg lvertneqq lvnE smtes sqcaps sqcups varsubsetneq varsubsetneqq varsupsetneq varsupsetneqq vsubnE vsubne vsupnE vsupne",
            "\u{fe00}",
        ),
        ("fjlig", "j"),
        (
            "nang nGt nLt NotSubset NotSuperset nsubset nsupset nvap nvge nvgt nvle nvlt nvltrie nvrtrie nvsim vnsub vnsup",
            "\u{20d2}",
        ),
        (
            "napE napid nbump nbumpe ncongdot nedot nesim ngE ngeqq ngeqslant nges nGg nGtv nlE nleqq nleqslant nles nLl nLtv NotEqualTilde NotGreaterFullEqual NotGreaterGreater NotGreaterSlantEqual NotHumpDownHump NotHumpEqual notindot notinE NotLeftTriangleBar NotLessLess NotLessSlantEqual NotNestedGreaterGreater NotNestedLessLess NotPrecedesEqual NotRightTriangleBar NotSquareSubset NotSquareSuperset NotSucceedsEqual NotSucceedsTilde npart npre npreceq nrarrc nrarrw nsce nsubE nsubseteqq nsucceq nsupE nsupseteqq",
            "\u{338}",
        ),
        ("race", "\u{331}"),
        ("ThickSpace", "\u{200a}"),
    ] {
        if names.split_whitespace().any(|n| n == name) {
            return suffix;
        }
    }
    ""
}

pub fn collapse(value: &str) -> String {
    crate::words(&unescape(value)).collect::<Vec<_>>().join(" ")
}
#[derive(Debug, Default)]
pub struct HtmlText {
    pub title: String,
    pub content: String,
}
pub fn html_text(value: &str) -> HtmlText {
    let mut title = Vec::new();
    let mut body = String::new();
    let mut skipped = 0usize;
    let mut in_title = false;
    let mut offset = 0;
    let mut raw_mode: Option<&str> = None;
    let data =
        |s: &str, body: &mut String, title: &mut Vec<String>, skipped: usize, in_title: bool| {
            if skipped > 0 {
                return;
            }
            if in_title {
                title.push(unescape(s));
            } else {
                let text = collapse(s);
                if !text.is_empty() {
                    body.push_str(&text);
                    body.push(' ');
                }
            }
        };
    while offset < value.len() {
        if let Some(name) = raw_mode {
            let closing = format!("</{name}");
            let bytes = &value.as_bytes()[offset..];
            let found = bytes.windows(closing.len()).enumerate().find(|(i, w)| {
                w.eq_ignore_ascii_case(closing.as_bytes())
                    && bytes
                        .get(i + closing.len())
                        .is_some_and(|c| c.is_ascii_whitespace() || *c == b'>')
            });
            let Some((index, _)) = found else {
                break;
            };
            offset += index;
            raw_mode = None;
        }
        let rest = &value[offset..];
        let Some(open) = rest.find('<') else {
            data(rest, &mut body, &mut title, skipped, in_title);
            break;
        };
        data(&rest[..open], &mut body, &mut title, skipped, in_title);
        offset += open;
        if value[offset..].starts_with("<!--") {
            offset += value[offset..]
                .find("-->")
                .map_or(value.len() - offset, |n| n + 3);
            continue;
        }
        let tag_start = offset;
        let mut quoted = None;
        let mut close = None;
        for (i, c) in value[offset + 1..].char_indices() {
            if let Some(q) = quoted {
                if c == q {
                    quoted = None;
                }
            } else if c == '\'' || c == '"' {
                quoted = Some(c);
            } else if c == '>' {
                close = Some(offset + 1 + i);
                break;
            }
        }
        let Some(end) = close else {
            data(
                &value[tag_start..],
                &mut body,
                &mut title,
                skipped,
                in_title,
            );
            break;
        };
        let raw = value[offset + 1..end].trim();
        offset = end + 1;
        if raw.starts_with(['!', '?']) {
            continue;
        }
        let ending = raw.starts_with('/');
        let self_closing = raw.ends_with('/');
        let name = raw
            .trim_start_matches('/')
            .split(|c: char| c.is_whitespace() || c == '/')
            .next()
            .unwrap_or("")
            .to_lowercase();
        if name.is_empty() || !name.chars().next().is_some_and(|c| c.is_ascii_alphabetic()) {
            data(
                &value[tag_start..offset],
                &mut body,
                &mut title,
                skipped,
                in_title,
            );
            continue;
        }
        if ["script", "style", "noscript", "svg"].contains(&name.as_str()) {
            if ending {
                skipped = skipped.saturating_sub(1);
            } else if !self_closing {
                skipped += 1;
                if name == "script" {
                    raw_mode = Some("script");
                }
                if name == "style" {
                    raw_mode = Some("style");
                }
            }
        }
        if name == "title" {
            in_title = !ending && !self_closing;
        }
        let line = if ending {
            ["p", "li", "section", "article", "div"].contains(&name.as_str())
        } else {
            [
                "p", "br", "li", "section", "article", "div", "h1", "h2", "h3",
            ]
            .contains(&name.as_str())
        };
        if line {
            body.push('\n');
        }
    }
    HtmlText {
        title: collapse(&title.join(" ")),
        content: body
            .lines()
            .map(collapse)
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
            .join("\n"),
    }
}
pub fn clean(value: &str) -> String {
    if value.contains('<') && value.contains('>') {
        collapse(&html_text(value).content)
    } else {
        collapse(value)
    }
}
pub fn truncate(value: &str, chars: usize) -> String {
    value.chars().take(chars).collect()
}
pub fn normalize_url(value: &str) -> String {
    let parsed = crate::urls::parse(value);
    if parsed.authority.ends_with("duckduckgo.com")
        && parsed.path_without_params().starts_with("/l/")
        && let Some((_, target)) = url::form_urlencoded::parse(parsed.query.as_bytes())
            .find(|(k, v)| k == "uddg" && !v.is_empty())
    {
        return percent_decode(&target);
    }
    if value.starts_with("//") {
        format!("https:{value}")
    } else {
        value.to_string()
    }
}
fn percent_decode(value: &str) -> String {
    let bytes = value.as_bytes();
    let mut decoded = Vec::new();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%'
            && i + 2 < bytes.len()
            && let (Some(a), Some(b)) = (
                (bytes[i + 1] as char).to_digit(16),
                (bytes[i + 2] as char).to_digit(16),
            )
        {
            decoded.push((a * 16 + b) as u8);
            i += 3;
            continue;
        }
        decoded.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&decoded).into_owned()
}
pub fn tokens(value: &str) -> std::collections::BTreeSet<String> {
    static TOKEN: LazyLock<Regex> = LazyLock::new(|| {
        Regex::new(r"[A-Za-z0-9_+\-]{2,}|[\u{3040}-\u{30ff}\u{3400}-\u{9fff}\u{ac00}-\u{d7a3}]+")
            .unwrap()
    });
    TOKEN
        .find_iter(value)
        .map(|m| m.as_str().to_lowercase())
        .collect()
}
