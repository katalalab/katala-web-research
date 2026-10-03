//! Copy-only migration. No connection is ever opened read/write on the source.
use crate::{
    Result,
    archive::{FTS_TABLES, SCHEMA, TABLES},
};
use rusqlite::{Connection, OpenFlags, backup::Backup};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fs, path::Path, time::Duration};

#[derive(Debug, Serialize)]
pub struct Status {
    pub user_version: i64,
    pub legacy: bool,
    pub schema_sha256: String,
}
fn normalize(sql: &str) -> String {
    let mut result = String::new();
    let mut quote = None;
    let mut chars = sql.chars().peekable();
    while let Some(c) = chars.next() {
        if let Some(end) = quote {
            result.push(c);
            if c == end {
                if chars.peek() == Some(&end) {
                    result.push(chars.next().unwrap());
                } else {
                    quote = None;
                }
            }
        } else if ['\'', '"', '`', '['].contains(&c) {
            quote = Some(if c == '[' { ']' } else { c });
            result.push(c);
        } else if !c.is_whitespace() {
            result.extend(c.to_lowercase());
        }
    }
    for prefix in [
        "createtable",
        "createvirtualtable",
        "createindex",
        "createtrigger",
    ] {
        if result.starts_with(&format!("{prefix}ifnotexists")) {
            result = result.replacen(&format!("{prefix}ifnotexists"), prefix, 1);
            break;
        }
    }
    result
}
fn objects(conn: &Connection) -> Result<BTreeMap<String, String>> {
    let mut stmt =
        conn.prepare("SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name")?;
    let pairs = stmt.query_map([], |r| {
        Ok((r.get::<_, String>(0)?, normalize(&r.get::<_, String>(1)?)))
    })?;
    Ok(pairs.collect::<std::result::Result<_, _>>()?)
}
fn expected(schema: &str) -> Result<BTreeMap<String, String>> {
    let conn = Connection::open_in_memory()?;
    conn.execute_batch(schema)?;
    objects(&conn)
}
pub fn legacy_schema() -> String {
    SCHEMA
        .replace("context TEXT NOT NULL DEFAULT '',", "")
        .replace("file_size INTEGER NOT NULL DEFAULT 0,", "")
        .replace("file_mtime_ns INTEGER NOT NULL DEFAULT 0,", "")
        .replace("content_sha256 TEXT NOT NULL DEFAULT '',", "")
        .replace("title, context, content", "title, content")
        .replace(
            "new.title, new.context, new.content",
            "new.title, new.content",
        )
        .replace(
            "old.title, old.context, old.content",
            "old.title, old.content",
        )
}
fn upgraded_legacy_objects() -> Result<BTreeMap<String, String>> {
    let conn = Connection::open_in_memory()?;
    conn.execute_batch(&legacy_schema())?;
    upgrade_legacy(&conn)?;
    objects(&conn)
}
fn upgrade_legacy(conn: &Connection) -> Result<()> {
    for sql in [
        "ALTER TABLE repo_documents ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE repo_documents ADD COLUMN file_mtime_ns INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE repo_documents ADD COLUMN content_sha256 TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE repo_documents ADD COLUMN context TEXT NOT NULL DEFAULT ''",
    ] {
        conn.execute_batch(sql)?;
    }
    for trigger in [
        "repo_documents_ai",
        "repo_documents_ad",
        "repo_documents_au",
    ] {
        conn.execute_batch(&format!("DROP TRIGGER {trigger}"))?;
    }
    conn.execute_batch("DROP TABLE repo_documents_fts")?;
    conn.execute_batch(SCHEMA)?;
    conn.execute(
        "INSERT INTO repo_documents_fts(repo_documents_fts) VALUES('rebuild')",
        [],
    )?;
    Ok(())
}
pub fn inspect(conn: &Connection) -> Result<Status> {
    let version: i64 = conn.pragma_query_value(None, "user_version", |r| r.get(0))?;
    if !(0..=1).contains(&version) {
        return Err(format!("unsupported archive schema version {version}").into());
    }
    let actual = objects(conn)?;
    let current = expected(SCHEMA)?;
    let legacy = if actual == current || actual == upgraded_legacy_objects()? {
        false
    } else if version == 0 && actual == expected(&legacy_schema())? {
        true
    } else {
        return Err("unrecognized archive schema; refusing implicit modification".into());
    };
    let bytes = serde_json::to_vec(&actual)?;
    Ok(Status {
        user_version: version,
        legacy,
        schema_sha256: format!("{:x}", Sha256::digest(bytes)),
    })
}
fn fingerprint(conn: &Connection, repo_width: usize) -> Result<BTreeMap<String, String>> {
    let mut result = BTreeMap::new();
    for table in TABLES {
        let mut statement = conn.prepare(&format!("SELECT * FROM {table} ORDER BY id"))?;
        let width = if table == "repo_documents" {
            repo_width
        } else {
            statement.column_count()
        };
        let mut rows = statement.query([])?;
        let mut hash = Sha256::new();
        while let Some(row) = rows.next()? {
            for i in 0..width {
                let value = row.get_ref(i)?;
                // Typed, length-delimited encoding prevents ambiguous adjacent fields.
                let bytes = match value {
                    rusqlite::types::ValueRef::Null => vec![0],
                    rusqlite::types::ValueRef::Integer(n) => {
                        let mut b = vec![1];
                        b.extend(n.to_le_bytes());
                        b
                    }
                    rusqlite::types::ValueRef::Real(n) => {
                        let mut b = vec![2];
                        b.extend(n.to_bits().to_le_bytes());
                        b
                    }
                    rusqlite::types::ValueRef::Text(t) => {
                        let mut b = vec![3];
                        b.extend(t);
                        b
                    }
                    rusqlite::types::ValueRef::Blob(t) => {
                        let mut b = vec![4];
                        b.extend(t);
                        b
                    }
                };
                hash.update((bytes.len() as u64).to_le_bytes());
                hash.update(bytes);
            }
        }
        result.insert(table.to_string(), format!("{:x}", hash.finalize()));
    }
    Ok(result)
}
fn validate(conn: &Connection) -> Result<()> {
    let check: String = conn.query_row("PRAGMA integrity_check", [], |r| r.get(0))?;
    if check != "ok" {
        return Err("archive integrity check failed".into());
    }
    for table in FTS_TABLES {
        // rank=1 checks external-content values as well as internal index structures.
        conn.execute(
            &format!("INSERT INTO {table}({table},rank) VALUES('integrity-check',1)"),
            [],
        )?;
    }
    Ok(())
}
#[derive(Debug, Serialize)]
pub struct Report {
    pub source: String,
    pub destination: String,
    pub dry_run: bool,
    pub before: Status,
    pub after: Status,
    pub row_counts: BTreeMap<String, i64>,
    pub source_unchanged: bool,
    pub already_migrated: bool,
}
pub fn migrate(source: &Path, destination: &Path, dry_run: bool) -> Result<Report> {
    migrate_inner(source, destination, dry_run, || Ok(()))
}
fn migrate_inner(
    source: &Path,
    destination: &Path,
    dry_run: bool,
    mut before_commit: impl FnMut() -> Result<()>,
) -> Result<Report> {
    if !source.is_file() {
        return Err("migration source must be an existing SQLite file".into());
    }
    if destination.exists() {
        return Err(
            "destination exists; refusing to overwrite (rollback keeps the original source)".into(),
        );
    }
    let parent = destination
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    if !parent.is_dir() {
        return Err("destination parent must already exist".into());
    }
    let source_conn = Connection::open_with_flags(source, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    source_conn.busy_timeout(Duration::from_secs(5))?;
    source_conn.execute_batch("BEGIN")?; // coherent source snapshot, including committed WAL
    let before = inspect(&source_conn)?;
    let repo_width = source_conn
        .prepare("SELECT * FROM repo_documents")?
        .column_count();
    let hashes = fingerprint(&source_conn, repo_width)?;
    let mut row_counts = BTreeMap::new();
    for table in TABLES {
        row_counts.insert(
            table.to_string(),
            source_conn.query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |r| r.get(0))?,
        );
    }
    let temp = tempfile::NamedTempFile::new_in(parent)?;
    let mut copy = Connection::open(temp.path())?;
    Backup::new(&source_conn, &mut copy)?.run_to_completion(128, Duration::from_millis(5), None)?;
    if fingerprint(&copy, repo_width)? != hashes {
        return Err("copy verification failed".into());
    }
    copy.execute_batch("PRAGMA journal_mode=DELETE; BEGIN IMMEDIATE")?;
    if before.legacy {
        upgrade_legacy(&copy)?;
    }
    copy.pragma_update(None, "user_version", 1)?;
    validate(&copy)?;
    before_commit()?;
    copy.execute_batch("COMMIT")?;
    let after = inspect(&copy)?;
    if fingerprint(&copy, repo_width)? != hashes {
        return Err("migration changed existing content".into());
    }
    for (table, count) in &row_counts {
        let current: i64 =
            copy.query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |r| r.get(0))?;
        if current != *count {
            return Err("migration row count changed".into());
        }
    }
    let source_unchanged = hashes == fingerprint(&source_conn, repo_width)?;
    if !source_unchanged {
        return Err("source changed during migration snapshot".into());
    }
    source_conn.execute_batch("ROLLBACK")?;
    copy.close().map_err(|(_, e)| e)?;
    if !dry_run {
        temp.as_file().sync_all()?;
        temp.persist_noclobber(destination)?;
        // On Unix sync the directory entry after publishing. Windows File::open(directory) is unsupported.
        #[cfg(unix)]
        fs::File::open(parent)?.sync_all()?;
    }
    Ok(Report {
        source: source.to_string_lossy().into(),
        destination: destination.to_string_lossy().into(),
        dry_run,
        already_migrated: before.user_version == 1,
        before,
        after,
        row_counts,
        source_unchanged,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn aborted_migration_rolls_back_and_can_be_retried() {
        let dir = tempfile::tempdir().unwrap();
        let source = dir.path().join("legacy.sqlite");
        let destination = dir.path().join("copy.sqlite");
        let c = Connection::open(&source).unwrap();
        c.execute_batch(&legacy_schema()).unwrap();
        c.execute("INSERT INTO pages(url,title,content,source,fetched_at) VALUES('https://fixture.test','evidence','preserved evidence','fixture','fixed')", []).unwrap();
        drop(c);
        let bytes = fs::read(&source).unwrap();
        let failed = migrate_inner(&source, &destination, false, || {
            Err("synthetic interruption before commit".into())
        });
        assert!(failed.is_err());
        assert!(!destination.exists());
        assert_eq!(bytes, fs::read(&source).unwrap());
        assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
        assert!(migrate(&source, &destination, false).is_ok());
    }
}
