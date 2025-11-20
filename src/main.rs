use parse_table::{self, Config};
use std::process;

fn main() {
    if let Err(e) = try_main() {
        eprintln!("Error: {}", e);
        process::exit(1);
    }
}

fn try_main() -> Result<(), parse_table::error::ParseError> {
    let args: Vec<String> = std::env::args().collect();
    let config = Config::new(&args)
        .map_err(|e| parse_table::error::ParseError::Html(e.to_string()))?;

    parse_table::run(&config)
}
