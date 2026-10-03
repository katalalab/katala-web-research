//! Owned synthetic process executable; never invokes a real gh/op or provider.
use std::{
    io::{Read, Write, stderr, stdout},
    process::{Command, Stdio},
    time::Duration,
};
fn main() {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    match args.first().map(String::as_str).unwrap_or("") {
        "probe" => {
            use kwr::process::{NativeRunner, ProcessRequest, ProcessRunner};
            let mut input = String::new();
            std::io::stdin().read_to_string(&mut input).unwrap();
            let input: serde_json::Value = serde_json::from_str(&input).unwrap();
            let request = ProcessRequest {
                program: if input["missing"] == true {
                    std::env::current_exe()
                        .unwrap()
                        .with_file_name("missing-owned-fixture-executable")
                        .to_string_lossy()
                        .into_owned()
                } else {
                    std::env::current_exe()
                        .unwrap()
                        .to_string_lossy()
                        .into_owned()
                },
                args: serde_json::from_value(input["args"].clone()).unwrap(),
                timeout_ms: input["timeout_ms"].as_u64().unwrap(),
                output_limit: input["output_limit"].as_u64().unwrap() as usize,
            };
            let output = match NativeRunner.run(&request) {
                Ok(output) => {
                    serde_json::json!({"return_code":output.return_code,"stdout":output.stdout,"stderr":output.stderr})
                }
                Err(error) => {
                    serde_json::json!({"error_kind":error.kind,"message":error.to_string()})
                }
            };
            println!("{output}");
        }
        "echo" => {
            print!("{}", args[1..].join("|"));
        }
        "both" => {
            print!("alpha 日本語\r\n");
            eprint!("synthetic stderr\r\n");
        }
        "flood" => {
            let block = [b'x'; 8192];
            loop {
                if stdout().write_all(&block).is_err() {
                    break;
                }
            }
        }
        "stderr-flood" => {
            let block = [b'x'; 8192];
            loop {
                if stderr().write_all(&block).is_err() {
                    break;
                }
            }
        }
        "invalid" => {
            stdout().write_all(&[255]).unwrap();
        }
        "sleep" => std::thread::sleep(Duration::from_secs(10)),
        "heartbeat" => {
            let mut f = std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(&args[1])
                .unwrap();
            loop {
                f.write_all(b"x").unwrap();
                f.flush().unwrap();
                std::thread::sleep(Duration::from_millis(5));
            }
        }
        "descendant" => {
            let mut child = Command::new(std::env::current_exe().unwrap())
                .args(["heartbeat", &args[1]])
                .stdin(Stdio::null())
                .spawn()
                .unwrap();
            let _ = child.wait();
        }
        "search" => {
            assert_eq!(args[1], "repos");
            assert_eq!(args[3], "--limit");
            assert_eq!(args[5], "--json");
            assert_eq!(
                args[6],
                "fullName,description,url,stargazersCount,updatedAt,isFork"
            );
            match args[2].as_str() {
                "fixture-gh-empty" => println!("[]"),
                "fixture-gh-nonzero" => std::process::exit(7),
                "fixture-gh-malformed" => println!("public-fixture-key malformed"),
                "fixture-gh-invalid" => stdout().write_all(&[255]).unwrap(),
                "fixture-gh-stderr-invalid" => stderr().write_all(&[255]).unwrap(),
                "fixture-gh-retracted" => println!(
                    "[{{\"fullName\":\"alpha retracted\",\"url\":\"https://github.com/fixture/repo\",\"description\":\"retracted=true\"}}]"
                ),
                _ => println!(
                    "[{{\"fullName\":\"fixture/alpha日本語\",\"url\":\"https://github.com/fixture/repo\",\"description\":\"alpha 日本語 implementation\",\"updatedAt\":\"2026-01-02\",\"stargazersCount\":3,\"isFork\":false}}]"
                ),
            }
        }
        _ => std::process::exit(2),
    }
}
