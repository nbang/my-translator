//! A library for parsing HTML tables containing organizational structure data
//! and converting them to CSV and Markdown formats.
//! 
//! # Example
//! ```no_run
//! use parse_table::Config;
//! let args: Vec<String> = std::env::args().collect();
//! let config = Config::new(&args).unwrap();
//! parse_table::run(&config).unwrap();
//! ```

pub mod error;
pub use error::ParseError;

use scraper::{Html, Selector};
use serde::Serialize;
use std::fs::{File, read_to_string};
use std::io::{Write, BufWriter};
use std::path::PathBuf;

/// The root organization name used for parent department calculations
const ROOT_ORG: &str = "FSOFT";

#[derive(Debug)]
/// Configuration for the table parser
/// 
/// # Fields
/// 
/// * `input_file` - Path to the input HTML file
/// * `output_csv` - Path where the CSV output will be written
/// * `output_md` - Path where the Markdown output will be written
pub struct Config {
    pub input_file: PathBuf,
    pub output_csv: PathBuf,
    pub output_md: PathBuf,
}

impl Config {
    /// Generates a default output filename based on the input filename
    /// 
    /// # Arguments
    /// 
    /// * `input_path` - The input file path to base the output name on
    /// * `ext` - The desired file extension (without dot)
    /// 
    /// # Examples
    /// 
    /// ```
    /// # use std::path::PathBuf;
    /// # use parse_table::Config;
    /// let input = PathBuf::from("bod.html");
    /// let csv_output = Config::default_output_name(&input, "csv"); // Creates "data/input.csv"
    /// ```
    fn default_output_name(input_path: &PathBuf, ext: &str) -> PathBuf {
        input_path
            .file_stem()
            .map(|stem| PathBuf::from(stem).with_extension(ext))
            .unwrap_or_else(|| PathBuf::from(format!("output.{}", ext)))
    }

    pub fn new(args: &[String]) -> Result<Config, &'static str> {
        let input_file = if args.len() > 1 {
            PathBuf::from(&args[1])
        } else {
            return Err("Input file path is required");
        };

        let output_csv = if args.len() > 2 {
            PathBuf::from(&args[2])
        } else {
            Self::default_output_name(&input_file, "csv")
        };

        let output_md = if args.len() > 3 {
            PathBuf::from(&args[3])
        } else {
            Self::default_output_name(&input_file, "md")
        };

        Ok(Config {
            input_file,
            output_csv,
            output_md,
        })
    }
}

#[derive(Debug, Serialize)]
/// Represents a row in the organizational structure
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub struct OrgRow {
    /// Depth level in the organizational hierarchy (0 for root)
    #[serde(rename = "LEVEL")]
    level: usize,
    /// Parent department name
    #[serde(rename = "PARENT DEP")]
    parent_dep: String,
    /// Department name/abbreviation
    #[serde(rename = "DEP")]
    dep: String,
    /// Number of employees
    #[serde(rename = "EMP")]
    emp: String,
    /// Manager identifier
    #[serde(rename = "MANAGER")]
    manager: String,
    /// Department name in Vietnamese
    #[serde(rename = "VIETNAMESE NAME")]
    vietnamese_name: String,
    /// Department name in English
    #[serde(rename = "ENGLISH NAME")]
    english_name: String,
}

fn parent_from_abbr(abbr: &str) -> String {
    let abbr = abbr.trim();
    let parts: Vec<&str> = abbr.split_whitespace().collect();
    if parts.len() <= 1 {
        if abbr.to_uppercase() == ROOT_ORG {
            return "".to_string();
        }
        return ROOT_ORG.to_string();
    }
    parts[..parts.len()-1].join(" ")
}

fn compute_level(dep: &str) -> usize {
    let dep = dep.trim();
    if dep.to_uppercase() == ROOT_ORG {
        return 0;
    }
    dep.split_whitespace().count()
}


/// Run the table parser with the given configuration
/// 
/// # Errors
/// 
/// Returns `ParseError` if:
/// - The input file cannot be read
/// - The HTML content cannot be parsed
/// - No table is found with the expected class
/// - Output files cannot be written
pub fn run(config: &Config) -> Result<(), error::ParseError> {
    println!("Reading from: {}", config.input_file.display());
    
    // Create output directories if they don't exist
    if let Some(parent) = config.output_csv.parent() {
        std::fs::create_dir_all(parent)?;
    }
    if let Some(parent) = config.output_md.parent() {
        std::fs::create_dir_all(parent)?;
    }

    let html_content = read_to_string(&config.input_file)?;

    let document = Html::parse_document(&html_content);
    let table_selector = Selector::parse("table.org-data-table")
        .map_err(|_| ParseError::Html("Invalid table selector".to_string()))?;
    let row_selector = Selector::parse("tr")
        .map_err(|_| ParseError::Html("Invalid row selector".to_string()))?;
    let cell_selector = Selector::parse("td")
        .map_err(|_| ParseError::Html("Invalid cell selector".to_string()))?;

    let table = document.select(&table_selector)
        .next()
        .ok_or(ParseError::NoTable)?;

    let mut data: Vec<OrgRow> = Vec::new();
    let rows: Vec<_> = table.select(&row_selector).collect();

    for row in rows.iter().skip(1) {
        let cells: Vec<_> = row.select(&cell_selector).collect();
        if cells.is_empty() { continue; }

        let clean_text = |cell: &scraper::element_ref::ElementRef| -> String {
            cell.text().collect::<Vec<_>>().join("")
                .split_whitespace()
                .collect::<Vec<&str>>()
                .join(" ")
                .trim()
                .to_string()
        };

        let mut emp = cells.get(cells.len().wrapping_sub(4))
            .map(|c| clean_text(c).replace(",", ""))
            .unwrap_or_default();
        let dep = cells.get(cells.len().wrapping_sub(5))
            .map(|c| clean_text(c))
            .unwrap_or_default();
        let manager = cells.get(cells.len().wrapping_sub(3))
            .map(|c| clean_text(c))
            .unwrap_or_default();
        let vietnamese_name = cells.get(cells.len().wrapping_sub(2))
            .map(|c| clean_text(c))
            .unwrap_or_default();
        let english_name = cells.get(cells.len().wrapping_sub(1))
            .map(|c| clean_text(c))
            .unwrap_or_default();

        // Fallback: find any numeric cell for EMP
        if emp.is_empty() || emp.chars().any(|c| !c.is_digit(10)) {
            for cell in &cells {
                let txt = cell.text().collect::<String>()
                    .split_whitespace()
                    .collect::<Vec<&str>>()
                    .join("")
                    .replace(",", "");
                if !txt.is_empty() && txt.chars().all(|c| c.is_digit(10)) {
                    emp = txt;
                    break;
                }
            }
        }

        if [dep.as_str(), emp.as_str(), manager.as_str(), vietnamese_name.as_str(), english_name.as_str()]
            .iter().any(|v| !v.is_empty()) {
            let parent_dep = parent_from_abbr(&dep);
            let level = compute_level(&dep);
            data.push(OrgRow {
                level,
                parent_dep,
                dep,
                emp,
                manager,
                vietnamese_name,
                english_name,
            });
        }
    }

    // Write CSV
    let mut wtr = csv::Writer::from_path(&config.output_csv)?;
    for row in &data {
        wtr.serialize(row)?;
    }
    wtr.flush()?;
    println!("Data exported to CSV: {}", config.output_csv.display());

    // Write Markdown
    let mut md = BufWriter::new(File::create(&config.output_md)?);
    writeln!(md, "# Organization Structure\n")?;
    writeln!(md, "| LEVEL | PARENT DEP | DEP | EMP | MANAGER | VIETNAMESE NAME | ENGLISH NAME |")?;
    writeln!(md, "|---|---|---|---|---|---|---|")?;
    for row in &data {
        writeln!(
            md,
            "| {} | {} | {} | {} | {} | {} | {} |",
            row.level,
            row.parent_dep.replace("|", "/"),
            row.dep.replace("|", "/"),
            row.emp.replace("|", "/"),
            row.manager.replace("|", "/"),
            row.vietnamese_name.replace("|", "/"),
            row.english_name.replace("|", "/")
        )?;
    }
    println!("Data exported to Markdown: {}", config.output_md.display());

    // Print summary
    println!("\nSummary:");
    println!("Total departments: {}", data.len());
    let total_emp: usize = data.iter()
        .map(|r| r.emp.parse::<usize>().unwrap_or(0))
        .sum();
    println!("Total employees: {}", total_emp);

    Ok(())
}
