use std::error::Error;
use std::fmt;
use std::io;

/// Custom error types for the parse_table library
#[derive(Debug)]
pub enum ParseError {
    /// Error when reading or writing files
    Io(io::Error),
    /// Error when parsing HTML content
    Html(String),
    /// Error when no table was found in the HTML
    NoTable,
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ParseError::Io(err) => write!(f, "IO error: {}", err),
            ParseError::Html(msg) => write!(f, "HTML parsing error: {}", msg),
            ParseError::NoTable => write!(f, "No table found with class 'org-data-table'"),
        }
    }
}

impl Error for ParseError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            ParseError::Io(err) => Some(err),
            _ => None,
        }
    }
}

impl From<io::Error> for ParseError {
    fn from(err: io::Error) -> Self {
        ParseError::Io(err)
    }
}

impl From<csv::Error> for ParseError {
    fn from(err: csv::Error) -> Self {
        ParseError::Io(io::Error::new(io::ErrorKind::Other, err))
    }
}