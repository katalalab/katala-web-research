use crate::{Result, now};
use rusqlite::{Connection, params, types::ValueRef};
use serde_json::{Value, json};
use std::{fs, path::Path};

pub const SCHEMA: &str = include_str!("schema.sql");
pub const TABLES: [&str; 8] = [
    "runs",
    "search_results",
    "pages",
    "repo_documents",
    "feed_sources",
    "feed_items",
    "project_items",
    "engine_runs",
];
pub const FTS_TABLES: [&str; 4] = [
    "pages_fts",
    "repo_documents_fts",
    "feed_items_fts",
    "project_items_fts",
];

pub struct Archive {
    pub conn: Connection,
}
impl Archive {
    pub fn open(path: &Path) -> Result<Self> {
        let existed = path.exists();
        if let Some(parent) = path.parent()
            && !parent.as_os_str().is_empty()
        {
            fs::create_dir_all(parent)?;
        }
        let conn = Connection::open(path)?;
        conn.busy_timeout(std::time::Duration::from_secs(5))?;
        if existed {
            let status = crate::migration::inspect(&conn)?;
            if status.legacy {
                return Err(
                    "legacy archive needs copy migration; use migrate --source … --destination …"
                        .into(),
                );
            }
        } else {
            conn.execute_batch(SCHEMA)?;
            conn.pragma_update(None, "user_version", 1)?;
        }
        conn.pragma_update(None, "journal_mode", "WAL")?;
        Ok(Self { conn })
    }
    pub fn query(
        &self,
        kind: &str,
        terms: &str,
        limit: i64,
        repo: &str,
        path: &str,
    ) -> Result<Vec<Value>> {
        let mut words = Vec::new();
        let (mut inline_repo, mut inline_path) = ("", "");
        for token in crate::words(terms) {
            if kind == "repos" && token.starts_with("repo:") && token.len() > 5 {
                if inline_repo.is_empty() {
                    inline_repo = &token[5..];
                }
            } else if kind == "repos" && token.starts_with("path:") && token.len() > 5 {
                if inline_path.is_empty() {
                    inline_path = &token[5..];
                }
            } else {
                words.push(token.replace('"', ""));
            }
        }
        let fts = if words.is_empty() {
            "\"\"".to_string()
        } else {
            words
                .iter()
                .map(|w| format!("\"{w}\""))
                .collect::<Vec<_>>()
                .join(" ")
        };
        let sql = match kind {
            "pages" => "SELECT p.url,p.title,snippet(pages_fts,1,'[',']','...',18) AS snippet,bm25(pages_fts) AS rank,p.fetched_at FROM pages_fts JOIN pages p ON p.id=pages_fts.rowid WHERE pages_fts MATCH ? ORDER BY rank LIMIT ?".to_string(),
            "feeds" => "SELECT i.url,i.title,snippet(feed_items_fts,1,'[',']','...',18) AS snippet,bm25(feed_items_fts) AS rank,i.source_url,i.source_title,i.published_at,i.fetched_at FROM feed_items_fts JOIN feed_items i ON i.id=feed_items_fts.rowid WHERE feed_items_fts MATCH ? ORDER BY rank LIMIT ?".to_string(),
            "issues" => "SELECT i.kind,i.repository,i.number,i.title,i.url,i.state,i.updated_at,i.labels_json,i.priority,i.status,i.source,bm25(project_items_fts) AS rank,snippet(project_items_fts,1,'[',']','...',18) AS snippet FROM project_items_fts JOIN project_items i ON i.id=project_items_fts.rowid WHERE project_items_fts MATCH ? ORDER BY rank LIMIT ?".to_string(),
            "repos" => {
                let repo = if repo.is_empty() { inline_repo } else { repo };
                let path = if path.is_empty() { inline_path } else { path };
                let mut sql = "SELECT d.repo_path,d.repo_name,d.rel_path,d.title,snippet(repo_documents_fts,4,'[',']','...',18) AS snippet,d.kind,bm25(repo_documents_fts,2.0,1.6,2.4,1.8,1.0) AS rank,d.indexed_at FROM repo_documents_fts JOIN repo_documents d ON d.id=repo_documents_fts.rowid WHERE repo_documents_fts MATCH ?".to_string();
                let mut values = vec![Value::String(fts)];
                if !repo.is_empty() { sql.push_str(" AND d.repo_name = ?"); values.push(json!(repo)); }
                if !path.is_empty() { sql.push_str(" AND d.rel_path LIKE ? ESCAPE '\\'"); values.push(json!(format!("%{}%", path.replace('\\',"\\\\").replace('%',"\\%").replace('_',"\\_")))); }
                sql.push_str(" ORDER BY rank LIMIT ?"); values.push(json!(limit));
                let mut rows = query_json(&self.conn, &sql, &values)?;
                for row in &mut rows { row["document_url"] = json!(format!("repo://{}/{}", row["repo_name"].as_str().unwrap_or(""),row["rel_path"].as_str().unwrap_or(""))); }
                return Ok(rows);
            }
            _ => return Err("unknown archive query kind".into()),
        };
        let mut rows = query_json(&self.conn, &sql, &[json!(fts), json!(limit)])?;
        if kind == "issues" {
            for row in &mut rows {
                let labels = row.as_object_mut().unwrap().remove("labels_json").unwrap();
                row["labels"] = serde_json::from_str(labels.as_str().unwrap_or("[]"))?;
                row["item_key"] = json!(format!(
                    "{}#{}:{}",
                    row["repository"].as_str().unwrap_or(""),
                    row["number"],
                    row["kind"].as_str().unwrap_or("")
                ));
            }
        }
        Ok(rows)
    }
    pub fn cached_page(&self, url: &str) -> Result<Option<Value>> {
        Ok(query_json(&self.conn,"SELECT url,title,content,source,fetched_at,status_code,content_type FROM pages WHERE url=?", &[json!(url)])?.into_iter().next())
    }
    pub fn add_feed(&self, url: &str, title: &str) -> Result<i64> {
        self.conn.execute("INSERT INTO feed_sources(url,title,kind,added_at) VALUES (?,?,'',?) ON CONFLICT(url) DO UPDATE SET title=CASE WHEN excluded.title!='' THEN excluded.title ELSE feed_sources.title END", params![url,title,now()])?;
        Ok(self
            .conn
            .query_row("SELECT COUNT(*) FROM feed_sources", [], |r| r.get(0))?)
    }
    pub fn engines(&self, window: i64) -> Result<Vec<Value>> {
        let rows = query_json(
            &self.conn,
            "SELECT provider,status,latency_ms,result_count,error_kind,recorded_at FROM (SELECT *,ROW_NUMBER() OVER (PARTITION BY provider ORDER BY id DESC) AS position FROM engine_runs) WHERE position<=?",
            &[json!(window)],
        )?;
        let mut grouped = std::collections::BTreeMap::<String, Vec<Value>>::new();
        for row in rows {
            grouped
                .entry(row["provider"].as_str().unwrap().to_string())
                .or_default()
                .push(row);
        }
        // Decimal formatting rounds the original IEEE value. Multiplying first
        // can manufacture an exact tie and differs from Python round(x, 4).
        let round = |x: f64| format!("{x:.4}").parse::<f64>().unwrap();
        let mut stats = Vec::new();
        for (provider, rows) in grouped {
            let n = rows.len();
            let failures = rows.iter().filter(|r| r["status"] == "error").count();
            let useful = rows
                .iter()
                .filter(|r| r["result_count"].as_i64().unwrap_or(0) > 0)
                .count();
            let mut latencies: Vec<_> = rows
                .iter()
                .map(|r| r["latency_ms"].as_i64().unwrap_or(0))
                .collect();
            latencies.sort();
            let p95 = latencies[((n as f64 * 0.95).ceil() as usize).max(1) - 1];
            let fr = failures as f64 / n as f64;
            let ur = useful as f64 / n as f64;
            let factor = if p95 < 1000 {
                1.0
            } else if p95 < 2000 {
                0.6
            } else if p95 < 5000 {
                0.3
            } else {
                0.0
            };
            let error = rows
                .iter()
                .rev()
                .find_map(|r| r["error_kind"].as_str().filter(|s| !s.is_empty()))
                .unwrap_or("");
            stats.push(json!({"provider":provider,"runs":n,"failures":failures,"failure_rate":round(fr),"useful_rate":round(ur),"p95_latency_ms":p95,"health_score":round((1.0-fr)*0.5+ur*0.35+factor*0.15),"last_error_kind":error,"routed_around":n>=5 && (round(fr)>0.5 || p95>5000 || round(ur)<0.2)}));
        }
        stats.sort_by(|a, b| {
            b["health_score"]
                .as_f64()
                .unwrap()
                .total_cmp(&a["health_score"].as_f64().unwrap())
                .then(a["provider"].as_str().cmp(&b["provider"].as_str()))
        });
        Ok(stats)
    }
}

pub fn query_json(conn: &Connection, sql: &str, values: &[Value]) -> Result<Vec<Value>> {
    let params: Vec<rusqlite::types::Value> = values
        .iter()
        .map(|v| match v {
            Value::String(s) => rusqlite::types::Value::Text(s.clone()),
            Value::Number(n) if n.is_i64() => rusqlite::types::Value::Integer(n.as_i64().unwrap()),
            Value::Number(n) => rusqlite::types::Value::Real(n.as_f64().unwrap()),
            _ => rusqlite::types::Value::Null,
        })
        .collect();
    let mut stmt = conn.prepare(sql)?;
    let names: Vec<_> = stmt
        .column_names()
        .into_iter()
        .map(str::to_string)
        .collect();
    let rows = stmt.query_map(rusqlite::params_from_iter(params.iter()), |r| {
        let mut obj = serde_json::Map::new();
        for (i, name) in names.iter().enumerate() {
            let value = match r.get_ref(i)? {
                ValueRef::Null => Value::Null,
                ValueRef::Integer(n) => json!(n),
                ValueRef::Real(n) => json!(n),
                ValueRef::Text(t) => json!(String::from_utf8_lossy(t)),
                ValueRef::Blob(_) => {
                    return Err(rusqlite::Error::InvalidColumnType(
                        i,
                        name.clone(),
                        rusqlite::types::Type::Blob,
                    ));
                }
            };
            obj.insert(name.clone(), value);
        }
        Ok(Value::Object(obj))
    })?;
    Ok(rows.collect::<std::result::Result<Vec<_>, _>>()?)
}
