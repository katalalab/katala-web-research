use clap::{Args, Parser, Subcommand};
use kwr::{Result, archive::Archive, planner, registry::Registry};
use serde_json::{Value, json};
use std::{
    io::{self, Write},
    path::PathBuf,
};

#[derive(Parser)]
#[command(
    name = "kwr",
    version = "0.1.0",
    about = "Native Rust migration; see docs/migration/parity.md for remaining commands"
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}
#[derive(Args)]
struct Local {
    #[arg(long, default_value = ".katala-web-research/archive.sqlite")]
    archive: PathBuf,
    #[arg(long)]
    json: bool,
}
#[derive(Args)]
#[group(skip)]
struct Query {
    terms: String,
    #[command(flatten)]
    local: Local,
    #[arg(short = 'n', long, default_value_t = 10, allow_hyphen_values = true)]
    limit: i64,
}
#[derive(Subcommand)]
enum Command {
    Search {
        query: String,
        #[command(flatten)]
        local: Local,
        #[arg(long,default_value="ddg",value_parser=["brave","ddg","feed","github","github_code","jina","meta","openalex","searxng"])]
        provider: String,
        #[arg(short = 'n', long, default_value_t = 10, allow_hyphen_values = true)]
        limit: i64,
        #[arg(long, default_value_t = 2.0, allow_hyphen_values = true)]
        candidate_multiplier: f64,
        #[arg(long,value_parser=["github","research","pdf"])]
        category: Vec<String>,
        #[arg(long)]
        include_domain: Vec<String>,
        #[arg(long)]
        exclude_domain: Vec<String>,
        #[arg(long, default_value_t = 0, allow_hyphen_values = true)]
        enrich_top: i64,
        #[arg(long, default_value_t = 0, allow_hyphen_values = true)]
        highlight_top: i64,
        #[arg(long,default_value="auto",value_parser=["auto","jina","direct"])]
        reader: String,
    },
    Plan {
        query: String,
        #[arg(long, default_value_t = 4, allow_hyphen_values = true)]
        max_subqueries: i64,
        #[arg(long, allow_hyphen_values = true)]
        year: Option<i64>,
        #[arg(long)]
        json: bool,
    },
    Sources {
        #[command(subcommand)]
        command: Sources,
    },
    Query(Query),
    Repos {
        #[command(subcommand)]
        command: Repos,
    },
    Feeds {
        #[command(subcommand)]
        command: Feeds,
    },
    Issues {
        #[command(subcommand)]
        command: Issues,
    },
    Engines {
        #[command(flatten)]
        local: Local,
        #[arg(long, default_value_t = 50, allow_hyphen_values = true)]
        window: i64,
    },
    Read {
        url: String,
        #[command(flatten)]
        local: Local,
        #[arg(long)]
        cache: bool,
        #[arg(long)]
        refresh: bool,
        #[arg(long,default_value="auto",value_parser=["auto","direct","jina"])]
        reader: String,
    },
    Migrate {
        #[arg(long)]
        source: PathBuf,
        #[arg(long)]
        destination: PathBuf,
        #[arg(long)]
        dry_run: bool,
    },
}
#[derive(Subcommand)]
enum Sources {
    List {
        #[arg(long)]
        domain: Option<String>,
        #[arg(long)]
        query_type: Option<String>,
        #[arg(short = 'n', long, default_value_t = 20, allow_hyphen_values = true)]
        limit: i64,
        #[arg(long)]
        json: bool,
    },
    Match {
        url: String,
        #[arg(long)]
        json: bool,
    },
}
#[derive(Subcommand)]
enum Repos {
    Query {
        #[command(flatten)]
        query: Query,
        #[arg(long, default_value = "")]
        repo: String,
        #[arg(long, default_value = "")]
        path: String,
    },
}
#[derive(Subcommand)]
enum Feeds {
    Refresh {
        #[arg(long)]
        source: Option<String>,
        #[command(flatten)]
        local: Local,
    },
    Add {
        url: String,
        #[arg(long, default_value = "")]
        title: String,
        #[command(flatten)]
        local: Local,
    },
    Query(Query),
}
#[derive(Subcommand)]
enum Issues {
    Query(Query),
}
fn emit(value: &impl serde::Serialize, out: &mut impl Write) -> Result<()> {
    writeln!(out, "{}", serde_json::to_string_pretty(value)?)?;
    Ok(())
}
fn field<'a>(row: &'a Value, key: &str) -> &'a str {
    row[key].as_str().unwrap_or("")
}
fn query(kind: &str, q: Query, repo: &str, path: &str, out: &mut impl Write) -> Result<()> {
    let hits = Archive::open(&q.local.archive)?.query(kind, &q.terms, q.limit, repo, path)?;
    if q.local.json {
        return emit(&hits, out);
    }
    for (i, h) in hits.iter().enumerate() {
        match kind {
            "repos" => writeln!(
                out,
                "{}. {}/{}\n   {}\n   {}\n   {}",
                i + 1,
                field(h, "repo_name"),
                field(h, "rel_path"),
                field(h, "title"),
                field(h, "snippet"),
                field(h, "repo_path")
            )?,
            "feeds" => writeln!(
                out,
                "{}. {}\n   {}\n   feed: {}\n   {}",
                i + 1,
                field(h, "title"),
                field(h, "url"),
                if field(h, "source_title").is_empty() {
                    field(h, "source_url")
                } else {
                    field(h, "source_title")
                },
                field(h, "snippet")
            )?,
            "issues" => {
                writeln!(
                    out,
                    "{}. {}#{} {}\n   {}\n   kind={} priority={} updated_at={}",
                    i + 1,
                    field(h, "repository"),
                    h["number"],
                    field(h, "title"),
                    field(h, "url"),
                    field(h, "kind"),
                    field(h, "priority"),
                    field(h, "updated_at")
                )?;
                if let Some(labels) = h["labels"].as_array()
                    && !labels.is_empty()
                {
                    writeln!(
                        out,
                        "   labels={}",
                        labels
                            .iter()
                            .filter_map(Value::as_str)
                            .collect::<Vec<_>>()
                            .join(", ")
                    )?;
                }
            }
            _ => writeln!(
                out,
                "{}. {}\n   {}\n   {}",
                i + 1,
                field(h, "title"),
                field(h, "url"),
                field(h, "snippet")
            )?,
        }
    }
    Ok(())
}
fn load_registry() -> Result<Registry> {
    let overlay = std::env::var_os("KWR_SOURCE_REGISTRY_OVERLAY")
        .filter(|s| !s.is_empty())
        .map(PathBuf::from);
    Registry::load(overlay.as_deref())
}
fn local_feed_path(value: &str) -> Result<PathBuf> {
    let url = url::Url::parse(value)?;
    if url.scheme() != "file" || url.host_str().is_some_and(|h| h != "localhost") {
        return Err("local file feed URL requires no host or localhost".into());
    }
    url.to_file_path()
        .map_err(|_| "invalid local file URL".into())
}
fn validate_feed_source(value: &str) -> Result<()> {
    let url = url::Url::parse(value)?;
    match url.scheme() {
        "file" => {
            local_feed_path(value)?;
        }
        "http" | "https" => {}
        scheme => return Err(format!("feed scheme {scheme} not migrated yet").into()),
    }
    Ok(())
}
fn fetch_feed_text(value: &str) -> Result<String> {
    if ["http", "https"].contains(&url::Url::parse(value)?.scheme()) {
        let settings = kwr::http::Settings::from_env()?;
        return Ok(
            kwr::http::fetch_url(value, &[("Accept", kwr::http::FEED_ACCEPT)], &settings)?.text(),
        );
    }
    Ok(String::from_utf8_lossy(&std::fs::read(local_feed_path(value)?)?).into_owned())
}
fn run(cli: Cli, out: &mut impl Write) -> Result<()> {
    match cli.command {
        Command::Feeds {
            command: Feeds::Refresh { source, local },
        } => {
            let archive = Archive::open(&local.archive)?;
            let source = source.filter(|s| !s.is_empty());
            let sources = if let Some(url) = source.as_ref() {
                validate_feed_source(url)?;
                let s = kwr::feeds::FeedSource::pending(url.clone());
                archive.upsert_feed_source(&s)?;
                vec![s]
            } else {
                archive.feed_sources()?
            };
            // Reject unsupported source schemes before changing any source health.
            for source in &sources {
                validate_feed_source(&source.url)?;
            }
            let mut refreshed = Vec::new();
            for source in sources {
                let fetched_at = kwr::now();
                let parsed = fetch_feed_text(&source.url)
                    .and_then(|text| kwr::feeds::parse(&text, &source.url, &fetched_at));
                let row = match parsed {
                    Ok(parsed) => {
                        archive.upsert_feed_source(&parsed.source)?;
                        let count = archive.upsert_feed_items(&parsed.items)?;
                        let mut row = serde_json::to_value(parsed.source)?;
                        row["indexed_items"] = json!(count);
                        row
                    }
                    Err(e) => {
                        let kind = if let Some(e) = e.downcast_ref::<kwr::http::HttpError>() {
                            e.kind
                        } else if e.downcast_ref::<std::io::Error>().is_some() {
                            "FetchError"
                        } else {
                            "ValueError"
                        };
                        let mut s = kwr::feeds::FeedSource::pending(source.url);
                        s.title = source.title;
                        s.kind = source.kind;
                        s.last_fetched_at = fetched_at;
                        s.status = "error".into();
                        s.error_kind = kind.into();
                        archive.upsert_feed_source(&s)?;
                        let mut row = serde_json::to_value(s)?;
                        row["indexed_items"] = json!(0);
                        row
                    }
                };
                refreshed.push(row);
            }
            let indexed: i64 = refreshed
                .iter()
                .filter_map(|r| r["indexed_items"].as_i64())
                .sum();
            if local.json {
                emit(
                    &json!({"archive":local.archive,"source_count":refreshed.len(),"indexed_items":indexed,"refreshed":refreshed}),
                    out,
                )?;
            } else {
                writeln!(
                    out,
                    "archive: {}\nsources: {}\nindexed_items: {indexed}",
                    local.archive.display(),
                    refreshed.len()
                )?;
                for r in refreshed {
                    writeln!(
                        out,
                        "{}: {} items={}",
                        field(&r, "url"),
                        field(&r, "status"),
                        r["indexed_items"]
                    )?;
                }
            }
        }
        Command::Search {
            query,
            local,
            provider,
            limit,
            candidate_multiplier,
            category,
            include_domain,
            exclude_domain,
            enrich_top,
            highlight_top,
            reader: _,
        } => {
            if !["feed", "ddg", "searxng", "brave", "jina"].contains(&provider.as_str()) {
                return Err(format!("provider {provider} not migrated yet").into());
            }
            if enrich_top > 0 {
                return Err("network enrichment not migrated yet".into());
            }
            if !candidate_multiplier.is_finite() {
                return Err("candidate multiplier must be finite".into());
            }
            let registry = load_registry()?;
            let built =
                kwr::search::build_query(&query, &category, &include_domain, &exclude_domain);
            let candidates =
                limit.max((limit.max(1) as f64 * candidate_multiplier.max(1.0) + 0.9999) as i64);
            let results = if provider == "feed" {
                kwr::search::feed(&built.query, &local.archive, candidates, &registry)?
            } else {
                use chrono::Datelike;
                use kwr::providers::SearchProvider;
                let mut transport = kwr::providers::EnvTransport::default();
                let context = kwr::providers::Context {
                    registry: &registry,
                    year: chrono::Local::now().year(),
                };
                if provider == "ddg" {
                    kwr::providers::DuckDuckGo.search(
                        &built.query,
                        candidates,
                        &mut transport,
                        &context,
                    )?
                } else {
                    let kind = kwr::providers::json::Kind::named(&provider).unwrap();
                    kwr::providers::json::JsonSearch {
                        kind,
                        config: kwr::providers::json::Config::from_env(kind)?,
                    }
                    .search(
                        &built.query,
                        candidates,
                        &mut transport,
                        &context,
                    )?
                }
            };
            let mut results = kwr::search::slice(results, limit);
            for r in &mut results {
                if let Some(category) = kwr::search::category(&r.url, &built) {
                    r.metadata.insert("query_category".into(), json!(category));
                }
            }
            if highlight_top > 0 && !results.is_empty() {
                let archive = Archive::open(&local.archive)?;
                for r in results.iter_mut().take(highlight_top as usize) {
                    let page = archive.cached_page(&r.url)?;
                    let status = if let Some(page) = page {
                        let snippet = kwr::search::highlight(&query, field(&page, "content"));
                        if snippet.is_empty() {
                            "empty"
                        } else {
                            r.snippet = snippet;
                            r.metadata
                                .insert("highlight_source".into(), page["source"].clone());
                            r.metadata
                                .insert("highlight_fetched_at".into(), page["fetched_at"].clone());
                            "ok"
                        }
                    } else {
                        "miss"
                    };
                    r.metadata.insert("highlight_status".into(), json!(status));
                }
                use chrono::Datelike;
                results =
                    kwr::search::rank(&query, results, &registry, chrono::Local::now().year());
            }
            let results = kwr::search::slice(results, limit);
            if local.json {
                emit(&serde_json::to_value(results)?, out)?;
            } else {
                for r in results {
                    writeln!(out, "{}. {}\n   {}", r.rank, r.title, r.url)?;
                    if !r.snippet.is_empty() {
                        writeln!(out, "   {}", r.snippet)?;
                    }
                    writeln!(
                        out,
                        "   source={} score={}",
                        r.source,
                        serde_json::to_string(&r.score)?
                    )?;
                }
            }
        }
        Command::Plan {
            query,
            max_subqueries,
            year,
            json,
        } => {
            let steps = planner::plan(&query, max_subqueries, year);
            if json {
                emit(&steps, out)?;
            } else {
                for (i, s) in steps.iter().enumerate() {
                    writeln!(out, "{}. {}: {}", i + 1, s.intent, s.query)?;
                }
            }
        }
        Command::Sources { command } => {
            let overlay = std::env::var_os("KWR_SOURCE_REGISTRY_OVERLAY")
                .filter(|s| !s.is_empty())
                .map(PathBuf::from);
            let registry = Registry::load(overlay.as_deref())?;
            match command {
                Sources::List {
                    domain,
                    query_type,
                    limit,
                    json,
                } => {
                    let entries =
                        registry.recommend(domain.as_deref(), query_type.as_deref(), limit);
                    if json {
                        emit(
                            &json!({"count":entries.len(),"domain":domain,"query_type":query_type,"sources":entries}),
                            out,
                        )?;
                    } else {
                        writeln!(out, "count: {}", entries.len())?;
                        for s in entries {
                            writeln!(
                                out,
                                "- {}/{}: {}\n  url: {}",
                                s.domain, s.source_type, s.name, s.url
                            )?;
                            if !s.bias_caveat.is_empty() {
                                writeln!(out, "  caveat: {}", s.bias_caveat)?;
                            }
                        }
                    }
                }
                Sources::Match { url, json } => {
                    let source = registry.match_url(&url);
                    if json {
                        emit(
                            &json!({"url":url,"matched":source.is_some(),"source":source}),
                            out,
                        )?;
                    } else if let Some(s) = source {
                        writeln!(
                            out,
                            "matched: true\nsource: {}\ndomain: {}\nsource_type: {}\ntrust_score: {}",
                            s.name, s.domain, s.source_type, s.trust_score
                        )?;
                        if !s.bias_caveat.is_empty() {
                            writeln!(out, "bias_caveat: {}", s.bias_caveat)?;
                        }
                    } else {
                        writeln!(out, "matched: false")?;
                    }
                }
            }
        }
        Command::Query(q) => query("pages", q, "", "", out)?,
        Command::Repos {
            command:
                Repos::Query {
                    query: q,
                    repo,
                    path,
                },
        } => query("repos", q, &repo, &path, out)?,
        Command::Feeds {
            command: Feeds::Query(q),
        } => query("feeds", q, "", "", out)?,
        Command::Issues {
            command: Issues::Query(q),
        } => query("issues", q, "", "", out)?,
        Command::Feeds {
            command: Feeds::Add { url, title, local },
        } => {
            let count = Archive::open(&local.archive)?.add_feed(&url, &title)?;
            if local.json {
                emit(
                    &json!({"archive":local.archive,"source_count":count,"source":{"url":url,"title":title,"kind":"","added_at":"","last_fetched_at":"","status":"pending","health_score":0.0,"error_kind":"","last_item_count":0}}),
                    out,
                )?;
            } else {
                writeln!(
                    out,
                    "archive: {}\nsource: {url}\nsource_count: {count}",
                    local.archive.display()
                )?;
            }
        }
        Command::Engines { local, window } => {
            let stats = Archive::open(&local.archive)?.engines(window)?;
            if local.json {
                emit(&stats, out)?;
            } else if stats.is_empty() {
                writeln!(out, "no engine runs recorded yet")?;
            } else {
                for s in stats {
                    writeln!(
                        out,
                        "{}: health={} runs={} failures={} useful_rate={} p95_latency_ms={}{}",
                        field(&s, "provider"),
                        s["health_score"],
                        s["runs"],
                        s["failures"],
                        s["useful_rate"],
                        s["p95_latency_ms"],
                        if s["routed_around"] == true {
                            " ROUTED-AROUND"
                        } else {
                            ""
                        }
                    )?;
                }
            }
        }
        Command::Read {
            url,
            local,
            cache,
            refresh,
            reader: _,
        } => {
            if !cache || refresh {
                return Err(
                    "network reader not migrated yet; only existing --cache hits are supported"
                        .into(),
                );
            }
            let Some(mut page) = Archive::open(&local.archive)?.cached_page(&url)? else {
                return Err("cache miss; network reader not migrated yet".into());
            };
            if local.json {
                page["cached"] = json!(true);
                emit(&page, out)?;
            } else {
                eprintln!("cache: hit");
                writeln!(out, "{}", field(&page, "content"))?;
            }
        }
        Command::Migrate {
            source,
            destination,
            dry_run,
        } => emit(
            &kwr::migration::migrate(&source, &destination, dry_run)?,
            out,
        )?,
    }
    Ok(())
}
fn main() {
    let cli = Cli::parse();
    let result = run(cli, &mut io::stdout().lock());
    if let Err(error) = result {
        if error
            .downcast_ref::<io::Error>()
            .is_some_and(|e| e.kind() == io::ErrorKind::BrokenPipe)
        {
            std::process::exit(1);
        }
        eprintln!("kwr: error: {error}");
        std::process::exit(1);
    }
}
