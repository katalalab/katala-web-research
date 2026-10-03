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
fn run(cli: Cli, out: &mut impl Write) -> Result<()> {
    match cli.command {
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
