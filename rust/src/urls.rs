//! Literal URI components for reference parity, without port/path canonicalization.
#[derive(Debug, Default)]
pub struct Parts {
    pub scheme: String,
    pub authority: String,
    pub path: String,
    pub query: String,
    pub fragment: String,
}
pub fn parse(value: &str) -> Parts {
    let value = value
        .trim_start_matches(|c: char| c as u32 <= 0x20)
        .replace(['\r', '\n', '\t'], "");
    let (before, fragment) = value.split_once('#').unwrap_or((&value, ""));
    let (before, query) = before.split_once('?').unwrap_or((before, ""));
    let scheme = before.split_once(':').filter(|(s, _)| {
        !s.is_empty()
            && s.chars().next().is_some_and(|c| c.is_ascii_alphabetic())
            && s.chars()
                .all(|c| c.is_ascii_alphanumeric() || "+-.".contains(c))
    });
    let (scheme, rest) = scheme.map_or((String::new(), before), |(s, r)| (s.to_lowercase(), r));
    let (authority, path) = if let Some(rest) = rest.strip_prefix("//") {
        let end = rest.find('/').unwrap_or(rest.len());
        (&rest[..end], &rest[end..])
    } else {
        ("", rest)
    };
    Parts {
        scheme,
        authority: authority.into(),
        path: path.into(),
        query: query.into(),
        fragment: fragment.into(),
    }
}
impl Parts {
    pub fn path_without_params(&self) -> &str {
        if [
            "", "ftp", "hdl", "prospero", "http", "imap", "https", "shttp", "rtsp", "rtsps",
            "rtspu", "sip", "sips", "mms", "sftp", "tel",
        ]
        .contains(&self.scheme.as_str())
        {
            let start = self.path.rfind('/').map_or(0, |i| i + 1);
            if let Some(offset) = self.path[start..].find(';') {
                return &self.path[..start + offset];
            }
        }
        &self.path
    }
    fn serialize(&self) -> String {
        let prefix = if self.scheme.is_empty() {
            String::new()
        } else {
            format!("{}:", self.scheme)
        };
        let authority = if !self.authority.is_empty()
            || ["file", "http", "https", "ftp"].contains(&self.scheme.as_str())
        {
            format!("//{}", self.authority)
        } else {
            String::new()
        };
        let path =
            if !self.authority.is_empty() && !self.path.is_empty() && !self.path.starts_with('/') {
                format!("/{}", self.path)
            } else {
                self.path.clone()
            };
        format!(
            "{prefix}{authority}{path}{}{}",
            if self.query.is_empty() {
                String::new()
            } else {
                format!("?{}", self.query)
            },
            if self.fragment.is_empty() {
                String::new()
            } else {
                format!("#{}", self.fragment)
            }
        )
    }
}
pub fn join(base: &str, reference: &str) -> String {
    let base = parse(base);
    let mut r = parse(reference);
    if !r.scheme.is_empty() && r.scheme != base.scheme {
        return reference.into();
    }
    if !base.scheme.is_empty()
        && ![
            "file", "http", "https", "ftp", "gopher", "nntp", "imap", "wais", "rtsp", "rtspu",
            "sftp", "mms", "hdl", "prospero", "shttp",
        ]
        .contains(&base.scheme.as_str())
    {
        return reference.into();
    }
    r.scheme = base.scheme;
    if !r.authority.is_empty() {
        return r.serialize();
    }
    r.authority = base.authority;
    if r.path.is_empty() {
        r.path = base.path;
        if r.query.is_empty() {
            r.query = base.query;
        }
        return r.serialize();
    }
    let mut segments: Vec<&str>;
    if r.path.starts_with('/') {
        segments = r.path.split('/').collect();
    } else {
        let mut base_segments: Vec<_> = base.path.split('/').collect();
        if base_segments.last().is_some_and(|s| !s.is_empty()) {
            base_segments.pop();
        }
        segments = base_segments;
        segments.extend(r.path.split('/'));
        if segments.len() > 2 {
            let last = segments.len() - 1;
            segments = segments
                .into_iter()
                .enumerate()
                .filter(|(i, s)| *i == 0 || *i == last || !s.is_empty())
                .map(|(_, s)| s)
                .collect();
        }
    }
    let trailing = segments.last().is_some_and(|s| [".", ".."].contains(s));
    let mut resolved = Vec::new();
    for segment in segments {
        match segment {
            ".." => {
                resolved.pop();
            }
            "." => {}
            _ => resolved.push(segment),
        }
    }
    if trailing {
        resolved.push("");
    }
    r.path = resolved.join("/");
    if r.path.is_empty() {
        r.path = "/".into();
    }
    r.serialize()
}
