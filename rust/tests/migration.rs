use kwr::{
    archive::{Archive, SCHEMA},
    migration::{inspect, legacy_schema, migrate},
};
use rusqlite::{Connection, params};
use std::{fs, path::Path};

fn seed(path: &Path, legacy: bool) {
    let c = Connection::open(path).unwrap();
    let schema = if legacy {
        legacy_schema()
    } else {
        SCHEMA.to_string()
    };
    c.execute_batch(&schema).unwrap();
    c.execute("INSERT INTO pages(url,title,content,source,fetched_at) VALUES ('https://example.test','日本語 evidence','atomic rollback evidence','fixture','2026-01-01T00:00:00+00:00')",[]).unwrap();
    c.execute("INSERT INTO repo_documents(repo_path,repo_name,rel_path,title,content,kind,indexed_at) VALUES ('/synthetic','sample','docs/README.md','evidence','atomic evidence','docs','fixed')",[]).unwrap();
}
#[test]
fn current_copy_dry_run_and_idempotence() {
    let t = tempfile::tempdir().unwrap();
    let source = t.path().join("original.sqlite");
    let dest = t.path().join("copy.sqlite");
    seed(&source, false);
    let bytes = fs::read(&source).unwrap();
    let report = migrate(&source, &dest, true).unwrap();
    assert!(report.dry_run && report.source_unchanged);
    assert!(!dest.exists());
    assert_eq!(bytes, fs::read(&source).unwrap());
    let report = migrate(&source, &dest, false).unwrap();
    assert_eq!(report.after.user_version, 1);
    assert_eq!(bytes, fs::read(&source).unwrap());
    let copy = Archive::open(&dest).unwrap();
    assert_eq!(
        copy.query("pages", "rollback", 10, "", "").unwrap().len(),
        1
    );
    drop(copy);
    assert!(migrate(&source, &dest, false).is_err());
    let second = t.path().join("second.sqlite");
    let report = migrate(&dest, &second, false).unwrap();
    assert!(report.already_migrated);
    let a = Connection::open(&dest).unwrap();
    let b = Connection::open(&second).unwrap();
    assert_eq!(
        inspect(&a).unwrap().schema_sha256,
        inspect(&b).unwrap().schema_sha256
    );
}
#[test]
fn recognized_legacy_copy_preserves_content_and_upgrades_index() {
    let t = tempfile::tempdir().unwrap();
    let source = t.path().join("old.sqlite");
    let dest = t.path().join("new.sqlite");
    seed(&source, true);
    let bytes = fs::read(&source).unwrap();
    assert!(Archive::open(&source).is_err());
    let report = migrate(&source, &dest, false).unwrap();
    assert!(report.before.legacy);
    assert!(!report.after.legacy);
    assert_eq!(bytes, fs::read(&source).unwrap());
    let archive = Archive::open(&dest).unwrap();
    assert_eq!(
        archive.query("repos", "evidence", 10, "", "").unwrap()[0]["document_url"],
        "repo://sample/docs/README.md"
    );
    archive
        .conn
        .execute("UPDATE repo_documents SET context='new contextualterm'", [])
        .unwrap();
    assert_eq!(
        archive
            .query("repos", "contextualterm", 10, "", "")
            .unwrap()
            .len(),
        1
    );
}
#[test]
fn unknown_version_schema_and_destination_are_refused() {
    let t = tempfile::tempdir().unwrap();
    let source = t.path().join("original.sqlite");
    let dest = t.path().join("copy.sqlite");
    seed(&source, false);
    let c = Connection::open(&source).unwrap();
    c.pragma_update(None, "user_version", 99).unwrap();
    assert!(
        migrate(&source, &dest, false)
            .unwrap_err()
            .to_string()
            .contains("unsupported")
    );
    assert!(!dest.exists());
    c.pragma_update(None, "user_version", 0).unwrap();
    c.execute_batch("CREATE TABLE unknown(payload TEXT)")
        .unwrap();
    assert!(migrate(&source, &dest, false).is_err());
    assert!(!dest.exists());
    assert!(migrate(&source, &source, false).is_err());
}
#[test]
fn validation_failure_leaves_source_and_destination_untouched_then_retry_succeeds() {
    let t = tempfile::tempdir().unwrap();
    let source = t.path().join("original.sqlite");
    let dest = t.path().join("copy.sqlite");
    seed(&source, false);
    let c = Connection::open(&source).unwrap();
    c.execute("INSERT INTO pages_fts(pages_fts) VALUES('delete-all')", [])
        .unwrap();
    drop(c);
    let bytes = fs::read(&source).unwrap();
    assert!(migrate(&source, &dest, false).is_err());
    assert!(!dest.exists());
    assert_eq!(bytes, fs::read(&source).unwrap());
    let c = Connection::open(&source).unwrap();
    c.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')", [])
        .unwrap();
    drop(c);
    assert!(migrate(&source, &dest, false).is_ok());
}
#[test]
fn committed_wal_is_included_in_read_only_backup() {
    let t = tempfile::tempdir().unwrap();
    let source = t.path().join("wal.sqlite");
    let dest = t.path().join("copy.sqlite");
    seed(&source, false);
    let c = Connection::open(&source).unwrap();
    c.execute_batch("PRAGMA journal_mode=WAL; PRAGMA wal_autocheckpoint=0")
        .unwrap();
    c.execute(
        "INSERT INTO pages(url,title,content,source,fetched_at) VALUES (?,?,?,?,?)",
        params![
            "https://wal.test",
            "committed",
            "wal evidence",
            "fixture",
            "fixed"
        ],
    )
    .unwrap();
    let db_bytes = fs::read(&source).unwrap();
    let wal_path = source.with_extension("sqlite-wal");
    let wal_bytes = fs::read(&wal_path).unwrap();
    let report = migrate(&source, &dest, false).unwrap();
    assert_eq!(report.row_counts["pages"], 2);
    assert_eq!(db_bytes, fs::read(&source).unwrap());
    assert_eq!(wal_bytes, fs::read(&wal_path).unwrap());
    let copy = Archive::open(&dest).unwrap();
    assert!(copy.cached_page("https://wal.test").unwrap().is_some());
}
#[test]
fn schema_transaction_rolls_back_on_interruption() {
    let t = tempfile::tempdir().unwrap();
    let source = t.path().join("original.sqlite");
    seed(&source, false);
    let before = fs::read(&source).unwrap();
    {
        let c = Connection::open(&source).unwrap();
        c.execute_batch("BEGIN IMMEDIATE; ALTER TABLE pages ADD COLUMN interrupted TEXT")
            .unwrap();
        // Dropping the connection models a normal abort before transaction commit.
    }
    assert_eq!(before, fs::read(&source).unwrap());
    assert!(!inspect(&Connection::open(&source).unwrap()).unwrap().legacy);
}

#[test]
fn defaults_with_different_literal_whitespace_are_not_accepted() {
    let t = tempfile::tempdir().unwrap();
    let source = t.path().join("altered.sqlite");
    let c = Connection::open(&source).unwrap();
    c.execute_batch(&SCHEMA.replace("DEFAULT 'github'", "DEFAULT 'git hub'"))
        .unwrap();
    assert!(inspect(&c).is_err());
}
#[test]
fn copied_archive_remains_compatible_with_python_schema_contract() {
    let t = tempfile::tempdir().unwrap();
    let source = t.path().join("source.sqlite");
    let dest = t.path().join("copy.sqlite");
    seed(&source, false);
    migrate(&source, &dest, false).unwrap();
    let c = Connection::open(&dest).unwrap();
    c.execute_batch(SCHEMA).unwrap();
    c.execute("DELETE FROM pages WHERE url='https://example.test'", [])
        .unwrap();
    c.execute(
        "INSERT INTO pages_fts(pages_fts, rank) VALUES('integrity-check',1)",
        [],
    )
    .unwrap();
    assert_eq!(
        c.query_row("SELECT COUNT(*) FROM pages", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        0
    );
}

#[test]
fn stale_destination_wal_and_shm_are_rejected_without_replay_or_removal() {
    let dir = tempfile::tempdir().unwrap();
    let source = dir.path().join("source.sqlite");
    let dest = dir.path().join("copy.sqlite");
    seed(&source, false);
    let c = Connection::open(&source).unwrap();
    c.execute("UPDATE pages SET title='SOURCE'", []).unwrap();
    drop(c);
    seed(&dest, false);
    let stale = Connection::open(&dest).unwrap();
    stale
        .execute_batch("PRAGMA journal_mode=WAL; PRAGMA wal_autocheckpoint=0")
        .unwrap();
    stale
        .execute("UPDATE pages SET title='STALE WAL'", [])
        .unwrap();
    let wal = dir.path().join("copy.sqlite-wal");
    let shm = dir.path().join("copy.sqlite-shm");
    let wal_before = fs::read(&wal).unwrap();
    let shm_before = fs::read(&shm).unwrap();
    let source_before = fs::read(&source).unwrap();
    fs::rename(&dest, dir.path().join("parked.sqlite")).unwrap();
    for dry in [true, false] {
        assert!(migrate(&source, &dest, dry).is_err());
        assert!(!dest.exists());
        assert_eq!(wal_before, fs::read(&wal).unwrap());
        assert_eq!(shm_before, fs::read(&shm).unwrap());
        assert_eq!(source_before, fs::read(&source).unwrap());
    }
    assert_eq!(
        Connection::open(&source)
            .unwrap()
            .query_row("SELECT title FROM pages", [], |r| r.get::<_, String>(0))
            .unwrap(),
        "SOURCE"
    );
}
#[test]
fn destination_rollback_journal_is_rejected_and_preserved() {
    let dir = tempfile::tempdir().unwrap();
    let source = dir.path().join("source.sqlite");
    let dest = dir.path().join("copy.sqlite");
    seed(&source, false);
    seed(&dest, false);
    let c = Connection::open(&dest).unwrap();
    c.execute_batch("PRAGMA journal_mode=DELETE; PRAGMA cache_size=1; BEGIN IMMEDIATE")
        .unwrap();
    c.execute(
        "UPDATE pages SET content=?",
        ["synthetic hot journal evidence ".repeat(5000)],
    )
    .unwrap();
    let journal = dir.path().join("copy.sqlite-journal");
    let before = fs::read(&journal).unwrap();
    assert!(!before.is_empty());
    fs::rename(&dest, dir.path().join("parked.sqlite")).unwrap();
    assert!(migrate(&source, &dest, false).is_err());
    assert!(!dest.exists());
    assert_eq!(before, fs::read(&journal).unwrap());
}
#[cfg(unix)]
#[test]
fn dangling_destination_symlinks_are_rejected_for_body_and_each_sidecar() {
    use std::os::unix::fs::symlink;
    for suffix in ["", "-wal", "-shm", "-journal"] {
        let dir = tempfile::tempdir().unwrap();
        let source = dir.path().join("source.sqlite");
        let dest = dir.path().join("copy.sqlite");
        seed(&source, false);
        let entry = dir.path().join(format!("copy.sqlite{suffix}"));
        let missing = dir.path().join("missing");
        symlink(&missing, &entry).unwrap();
        let original = fs::read(&source).unwrap();
        assert!(migrate(&source, &dest, false).is_err());
        assert_eq!(fs::read_link(&entry).unwrap(), missing);
        assert_eq!(fs::read(&source).unwrap(), original);
    }
}

#[test]
fn each_standalone_sidecar_is_refused_before_copy_and_preserved() {
    for suffix in ["-wal", "-shm", "-journal"] {
        let dir = tempfile::tempdir().unwrap();
        let source = dir.path().join("source.sqlite");
        let dest = dir.path().join("copy.sqlite");
        seed(&source, false);
        let sidecar = dir.path().join(format!("copy.sqlite{suffix}"));
        fs::write(&sidecar, b"synthetic preexisting sidecar").unwrap();
        let original = fs::read(&source).unwrap();
        for dry in [true, false] {
            assert!(migrate(&source, &dest, dry).is_err());
            assert!(!dest.exists());
            assert_eq!(
                fs::read(&sidecar).unwrap(),
                b"synthetic preexisting sidecar"
            );
            assert_eq!(fs::read(&source).unwrap(), original);
            assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 2);
        }
    }
}
